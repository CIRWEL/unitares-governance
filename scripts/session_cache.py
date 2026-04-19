#!/usr/bin/env python3
"""Transport-neutral local cache helper for UNITARES client adapters.

Stores lightweight continuity state in:

    .unitares/session.json
    .unitares/last-milestone.json

This helper is intentionally small and dependency-free so Claude hooks, Codex
commands, and other thin clients can share one cache format.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_DIR = ".unitares"
CACHE_FILES = {
    "session": "session.json",
    "milestone": "last-milestone.json",
}


def _workspace_path(raw: str | None) -> Path:
    base = raw or os.getcwd()
    return Path(base).expanduser().resolve()


def _slot_suffix(slot: str | None) -> str:
    """Safe-filename slot suffix. Matches onboard_helper/_session_lookup."""
    if not slot:
        return ""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slot)
    return safe[:64]


def _cache_path(kind: str, workspace: Path, slot: str | None = None) -> Path:
    try:
        filename = CACHE_FILES[kind]
    except KeyError as exc:
        raise ValueError(f"unknown cache kind: {kind}") from exc
    # Only the session cache is slot-scoped — milestone accumulator is
    # workspace-level (per the auto-checkin design).
    safe_slot = _slot_suffix(slot) if kind == "session" else ""
    if safe_slot:
        stem, _, ext = filename.rpartition(".")
        filename = f"{stem}-{safe_slot}.{ext}"
    return workspace / CACHE_DIR / filename


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic write with mode 0600.

    The session cache carries continuity tokens. A world-readable cache
    (the default when using Path.write_text, which inherits umask 022)
    lets any same-UID process impersonate the cached identity against
    the governance API. Inlined rather than imported from unitares_sdk
    because this helper is intentionally dependency-free — shared by
    thin plugin clients that don't pull in the SDK.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    os.replace(tmp, str(path))


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    raw = args.json
    if raw is None and not sys.stdin.isatty():
        raw = sys.stdin.read()
    if raw is None:
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def cmd_path(args: argparse.Namespace) -> int:
    workspace = _workspace_path(args.workspace)
    print(_cache_path(args.kind, workspace, getattr(args, "slot", None)))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    workspace = _workspace_path(args.workspace)
    payload = _read_json(_cache_path(args.kind, workspace, getattr(args, "slot", None)))
    if args.key:
        value = payload.get(args.key)
        if value is None:
            return 0
        if isinstance(value, (dict, list)):
            print(json.dumps(value))
        else:
            print(value)
        return 0
    print(json.dumps(payload))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    workspace = _workspace_path(args.workspace)
    path = _cache_path(args.kind, workspace, getattr(args, "slot", None))
    payload = _load_payload(args)
    if args.merge:
        existing = _read_json(path)
        existing.update(payload)
        payload = existing
    if args.stamp:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, payload)
    if args.echo:
        print(json.dumps(payload))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    workspace = _workspace_path(args.workspace)
    path = _cache_path(args.kind, workspace, getattr(args, "slot", None))
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return 0


# Per-workspace cap on how many distinct file paths we remember in the
# milestone accumulator. The accumulator exists so auto-checkin can report a
# concrete file list; beyond ~20 entries the summary becomes noise and the
# cache starts growing unbounded in long-running sessions.
MILESTONE_FILE_CAP = 20


def cmd_bump_edit(args: argparse.Namespace) -> int:
    """Append an edit event to the milestone accumulator.

    Increments edit_count, dedupes file_path into files_touched (capped),
    stamps first_edit_ts on the first bump since reset, and always refreshes
    last_edit_ts + updated_at. Backwards-compatible keys (event, file_path,
    timestamp) are preserved so existing readers keep working.
    """
    workspace = _workspace_path(args.workspace)
    path = _cache_path("milestone", workspace)
    existing = _read_json(path)

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    now_iso = datetime.now(timezone.utc).isoformat()

    existing["edit_count"] = int(existing.get("edit_count") or 0) + 1
    if not existing.get("first_edit_ts"):
        existing["first_edit_ts"] = now_epoch
    existing["last_edit_ts"] = now_epoch
    existing["updated_at"] = now_iso

    files = existing.get("files_touched")
    if not isinstance(files, list):
        files = []
    fp = (args.file_path or "").strip()
    if fp and fp not in files:
        files.append(fp)
        if len(files) > MILESTONE_FILE_CAP:
            files = files[-MILESTONE_FILE_CAP:]
    existing["files_touched"] = files

    # Legacy shape — keep for readers that predate the accumulator.
    existing.setdefault("event", "edit")
    if fp:
        existing["file_path"] = fp
    existing["timestamp"] = now_epoch

    _write_json(path, existing)
    if args.echo:
        print(json.dumps(existing))
    return 0


def cmd_reset_milestone(args: argparse.Namespace) -> int:
    """Reset the milestone accumulator after a successful check-in."""
    workspace = _workspace_path(args.workspace)
    path = _cache_path("milestone", workspace)
    existing = _read_json(path)
    existing["edit_count"] = 0
    existing["files_touched"] = []
    existing["first_edit_ts"] = None
    existing["last_edit_ts"] = None
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, existing)
    if args.echo:
        print(json.dumps(existing))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_path = sub.add_parser("path", help="Print the absolute cache path")
    p_path.add_argument("kind", choices=sorted(CACHE_FILES))
    p_path.add_argument("--workspace")
    p_path.add_argument("--slot", help="Claude Code session_id for slotted cache")
    p_path.set_defaults(func=cmd_path)

    p_get = sub.add_parser("get", help="Read cached JSON")
    p_get.add_argument("kind", choices=sorted(CACHE_FILES))
    p_get.add_argument("--workspace")
    p_get.add_argument("--slot", help="Claude Code session_id for slotted cache")
    p_get.add_argument("--key")
    p_get.set_defaults(func=cmd_get)

    p_set = sub.add_parser("set", help="Write cached JSON")
    p_set.add_argument("kind", choices=sorted(CACHE_FILES))
    p_set.add_argument("--workspace")
    p_set.add_argument("--slot", help="Claude Code session_id for slotted cache")
    p_set.add_argument("--json")
    p_set.add_argument("--merge", action="store_true")
    p_set.add_argument("--stamp", action="store_true")
    p_set.add_argument("--echo", action="store_true")
    p_set.set_defaults(func=cmd_set)

    p_clear = sub.add_parser("clear", help="Delete a cache file")
    p_clear.add_argument("kind", choices=sorted(CACHE_FILES))
    p_clear.add_argument("--workspace")
    p_clear.add_argument("--slot", help="Claude Code session_id for slotted cache")
    p_clear.set_defaults(func=cmd_clear)

    p_bump = sub.add_parser(
        "bump-edit",
        help="Append an edit event to the milestone accumulator",
    )
    p_bump.add_argument("--workspace")
    p_bump.add_argument("--file-path", default="")
    p_bump.add_argument("--echo", action="store_true")
    p_bump.set_defaults(func=cmd_bump_edit)

    p_reset = sub.add_parser(
        "reset-milestone",
        help="Reset the milestone accumulator after a check-in",
    )
    p_reset.add_argument("--workspace")
    p_reset.add_argument("--echo", action="store_true")
    p_reset.set_defaults(func=cmd_reset_milestone)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"session_cache.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
