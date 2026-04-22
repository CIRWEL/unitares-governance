#!/usr/bin/env python3
"""Onboard helper for UNITARES client hooks.

Owns the flow:

1. Read existing ``.unitares/session.json`` cache (if any).
2. Call ``onboard`` — preferring ``continuity_token`` from cache, then
   ``client_session_id``.
3. If the server reports ``trajectory_required`` (identity exists but lacks
   a verifiable signal), return status=``trajectory_required`` with the
   server's recovery hint. We do NOT auto-retry with ``force_new=true``;
   that is an explicit operator decision, not an automatic one (see commit
   718ccd3 and the identity "never silently substitute" invariant).
4. ``force_new=true`` is set only when the caller passed ``--force-new``.
5. Only write the cache when onboard succeeded and produced a usable uuid.

Emits a JSON line on stdout with the resolved fields for the shell hook to
consume. Never raises — always returns a dict on stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_SERVER_URL = "http://localhost:8767"
DEFAULT_TIMEOUT = 10.0
CACHE_DIR = ".unitares"
CACHE_FILE = "session.json"


def _slot_filename(slot: str | None) -> str:
    """Return the cache filename, optionally namespaced by a slot key.

    Without a slot, returns the legacy shared "session.json". With a slot
    (typically the Claude Code session_id from the hook input JSON), returns
    "session-<safe-slot>.json". This lets N parallel ``claude`` processes in
    the SAME workspace each maintain their own identity rather than racing
    on a single cache file. See KG note 2026-04-14: "multiple claude agents
    sharing UUID" — that was per-workspace cache + multiple processes.
    """
    if not slot:
        return CACHE_FILE
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slot)
    safe = safe[:64]  # keep file names sane
    return f"session-{safe}.json"


def _scope_name_by_slot(agent_name: str, slot: str | None) -> str:
    """Append a short, stable slot fingerprint to the agent name.

    Why this exists: the server's onboard handler runs a name-claim lookup
    (``resolve_by_name_claim`` in src/mcp_handlers/identity/resolution.py)
    that matches an existing agent purely by label. Two parallel Claude
    processes in the same workspace would send the same ``name`` (the
    workspace basename) and both get bound to whichever agent already owns
    that label — even though each has its own slot-isolated cache.

    Scoping the name by slot defeats the name-claim at the client. Each
    conversation (slot) gets its own label, its own UUID, its own
    trajectory. Existing slot caches keep working: the UUID-direct resume
    path in ``run_onboard`` runs before this, so pinned slots keep their
    current identity regardless of name.

    Unslotted callers (Codex stdio, single-process flows) keep the legacy
    naming — this only scopes when a slot is actually provided.

    The architectural fix (remove name-claim, or seed trajectory at
    creation so the trajectory_required guard always fires) is tracked
    separately; see the project memory entry on name-claim ghosts.
    """
    if not slot:
        return agent_name
    # Hash the full slot so fingerprints collide only on a genuine hash
    # clash (~1 in 4 billion for 8 hex chars), not when two slots happen to
    # share a prefix. An earlier version used slot[:8] directly, which
    # broke for workloads where slots share a common prefix (e.g. tests
    # using "itest-slot-*" or CI runners that stamp a pipeline prefix on
    # every session id).
    fingerprint = hashlib.md5(slot.encode("utf-8")).hexdigest()[:8]
    return f"{agent_name}#{fingerprint}"


# --- IO primitives (separable for tests) -----------------------------------

def _post_json(url: str, payload: dict, timeout: float, token: str | None) -> dict:
    """POST JSON to ``url`` and return the parsed response, or ``{}`` on error."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _read_cache(workspace: Path, slot: str | None = None) -> dict:
    """Read the cache for this slot. No cross-slot fallback.

    Each slot (Claude Code session) gets its own identity. When no slot is
    provided, reads the legacy unslotted file for backward compat.
    A slotted session that has no cache yet returns {} — fresh onboard,
    not inheritance from another session's identity.
    """
    path = workspace / CACHE_DIR / _slot_filename(slot)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(workspace: Path, payload: dict, slot: str | None = None) -> None:
    path = workspace / CACHE_DIR / _slot_filename(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --- Response unwrap -------------------------------------------------------

def unwrap_tool_response(raw: dict) -> dict:
    """Unwrap the REST ``/v1/tools/call`` envelope.

    Handles two shapes:

    * Native MCP: ``{"result": {"content": [{"text": "<json>"}]}}``
    * REST-direct: ``{"result": {...fields...}}``

    Returns the inner dict, or ``{}`` if unrecognizable.
    """
    if not isinstance(raw, dict):
        return {}
    result = raw.get("result", raw)
    if not isinstance(result, dict):
        return {}
    content = result.get("content")
    if isinstance(content, list) and content:
        item = content[0]
        if isinstance(item, dict) and "text" in item:
            try:
                return json.loads(item["text"])
            except (json.JSONDecodeError, TypeError):
                return {}
    return result


def is_successful_onboard(parsed: dict) -> bool:
    """Onboard is successful iff the response has ``success != False`` and a uuid."""
    if not isinstance(parsed, dict):
        return False
    if parsed.get("success") is False:
        return False
    return bool(parsed.get("uuid"))


def trajectory_required(parsed: dict) -> bool:
    """Detect the ``trajectory_required`` recovery reason."""
    if not isinstance(parsed, dict):
        return False
    if parsed.get("success") is not False:
        return False
    recovery = parsed.get("recovery") or {}
    return isinstance(recovery, dict) and recovery.get("reason") == "trajectory_required"


# --- Core flow -------------------------------------------------------------

def run_onboard(
    *,
    server_url: str,
    agent_name: str,
    model_type: str,
    workspace: Path,
    slot: str | None = None,
    force_new: bool = False,
    auth_token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    post_json: Callable[[str, dict, float, str | None], dict] = _post_json,
    read_cache: Callable[..., dict] = _read_cache,
    write_cache: Callable[..., None] = _write_cache,
) -> dict:
    """Run the onboard flow. Returns a dict with status info.

    ``slot`` namespaces the cache file so multiple processes in the same
    workspace can each own their own identity (typically the Claude Code
    session_id from hook input). When omitted, falls back to the legacy
    shared session.json — preserves single-process behavior.
    """
    url = f"{server_url.rstrip('/')}/v1/tools/call"
    cache = read_cache(workspace, slot)

    # Fast path: UUID-direct resume (like SDK agents).
    # If we have a cached UUID, call identity(agent_uuid=...) instead of
    # going through the token/session resolution chain.
    #
    # Forward continuity_token alongside agent_uuid when the cache has one.
    # The server's Part C gate (UNITARES_IDENTITY_STRICT) requires the
    # token's `aid` claim to match agent_uuid; without it the call logs as
    # a suspected hijack today and will be rejected once strict mode
    # becomes default. The token is already in cache (written below at
    # write_cache time); the prior version simply did not forward it.
    cached_uuid = (cache.get("uuid") or cache.get("agent_uuid") or "").strip()
    if cached_uuid and not force_new:
        identity_args: dict[str, Any] = {"agent_uuid": cached_uuid, "resume": True}
        # S1 deprecation (identity ontology, docs/ontology/plan.md §S1):
        # `continuity_token` is a compatibility surface for external
        # clients; plugin-internal flows should declare lineage
        # (parent_agent_id) on fresh onboard rather than resume via token.
        # The token field is empty on v2 caches written by hooks/post-
        # identity — only legacy v1 caches or external-client writes
        # populate it here.
        cached_token = (cache.get("continuity_token") or "").strip()
        if cached_token:
            identity_args["continuity_token"] = cached_token
        raw = post_json(
            url,
            {"name": "identity", "arguments": identity_args},
            timeout, auth_token,
        )
        parsed = unwrap_tool_response(raw)
        if is_successful_onboard(parsed):
            # UUID resume succeeded — update cache and return
            new_cache = {
                "server_url": server_url,
                "agent_name": agent_name,
                "slot": slot or "",
                "uuid": parsed.get("uuid"),
                "agent_id": parsed.get("agent_id") or parsed.get("resolved_agent_id") or "",
                "client_session_id": parsed.get("client_session_id", ""),
                "continuity_token": parsed.get("continuity_token", ""),
                "session_resolution_source": parsed.get("session_resolution_source", ""),
                "continuity_token_supported": parsed.get("continuity_token_supported", False),
                "display_name": parsed.get("display_name", ""),
            }
            write_cache(workspace, new_cache, slot)
            return {
                "status": "ok",
                **{k: v for k, v in new_cache.items() if k not in ("server_url", "slot")},
            }
        # UUID not found — fall through to fresh onboard

    # Scope the name by slot so the server's name-claim lookup doesn't bind
    # this slot's onboard to an agent owned by another slot. UUID-direct
    # resume already ran above for slots with a cached identity, so this
    # only matters on the first onboard per slot.
    scoped_name = _scope_name_by_slot(agent_name, slot)
    arguments: dict[str, Any] = {"name": scoped_name, "model_type": model_type}
    if force_new:
        arguments["force_new"] = True

    raw = post_json(url, {"name": "onboard", "arguments": arguments}, timeout, auth_token)
    parsed = unwrap_tool_response(raw)

    if not is_successful_onboard(parsed):
        # Per 718ccd3: never auto-force_new. Surface the error so the operator
        # can decide (run `/governance-start --force` or clear the cache).
        # Clobbering trajectory with force_new silently substitutes identity.
        recovery = parsed.get("recovery") or {}
        return {
            "status": "trajectory_required" if trajectory_required(parsed) else "onboard_failed",
            "error": parsed.get("error", "onboard returned no uuid"),
            "recovery_reason": recovery.get("reason", ""),
            "recovery_hint": recovery.get("hint", ""),
        }

    # Build fresh cache payload — never preserve stale fields.
    new_cache = {
        "server_url": server_url,
        "agent_name": agent_name,
        "slot": slot or "",
        "uuid": parsed.get("uuid"),
        "agent_id": parsed.get("agent_id") or parsed.get("resolved_agent_id") or "",
        "client_session_id": parsed.get("client_session_id", ""),
        "continuity_token": parsed.get("continuity_token", ""),
        "session_resolution_source": parsed.get("session_resolution_source", ""),
        "continuity_token_supported": parsed.get("continuity_token_supported", False),
        "display_name": parsed.get("display_name", ""),
    }
    write_cache(workspace, new_cache, slot)

    return {
        "status": "ok",
        "uuid": new_cache["uuid"],
        "agent_id": new_cache["agent_id"],
        "client_session_id": new_cache["client_session_id"],
        "continuity_token": new_cache["continuity_token"],
        "session_resolution_source": new_cache["session_resolution_source"],
        "continuity_token_supported": new_cache["continuity_token_supported"],
        "display_name": new_cache["display_name"],
    }


# --- CLI -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default=os.environ.get("UNITARES_SERVER_URL", DEFAULT_SERVER_URL))
    parser.add_argument("--name", required=True, help="Agent display name")
    parser.add_argument("--model-type", default="claude-code")
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--force-new", action="store_true",
                        help="Explicit opt-in to create a fresh identity (never automatic)")
    parser.add_argument(
        "--slot",
        default=os.environ.get("UNITARES_SESSION_SLOT", ""),
        help="Per-process slot key (typically Claude Code session_id) so "
             "parallel processes in the same workspace don't collide on "
             "the same cache file.",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    auth_token = os.environ.get("UNITARES_HTTP_API_TOKEN") or None
    workspace = Path(args.workspace).expanduser().resolve()
    slot = (args.slot or "").strip() or None
    result = run_onboard(
        server_url=args.server_url,
        agent_name=args.name,
        model_type=args.model_type,
        workspace=workspace,
        slot=slot,
        force_new=args.force_new,
        auth_token=auth_token,
        timeout=args.timeout,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
