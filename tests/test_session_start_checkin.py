"""Contract tests for the SessionStart hook.

After the identity-honesty Part C refactor (2026-04-17) and the identity-
hijack hardening of 2026-04-20, the hook does NOT create an identity on
the agent's behalf AND does NOT surface other instances' UUIDs as a
resume menu. It only:

  1. Confirms governance is reachable.
  2. Suggests onboard() — fresh identity by default.
  3. If THIS workspace has its own continuity cache (./.unitares/session.json,
     written by the post-identity hook on a prior run in this directory),
     suggests resuming via that signed continuity_token.
  4. Never enumerates ~/.unitares/session-*.json — those are other instances'
     identities, and surfacing them as an unfiltered "Recent session UUIDs"
     menu invited cross-instance hijack (KG bug 2026-04-20T00:09:51).

These tests lock in the post-2026-04-20 contract:
  - Hook emits ZERO HTTP tool calls on SessionStart.
  - Online context describes the provisional-free state.
  - Online context surfaces ONLY the workspace-local continuity cache, if any.
  - Online context never lists ~/.unitares/session-*.json contents.
  - Offline context reports OFFLINE and does not reference a fake identity.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import threading
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent


class RecordingHandler(http.server.BaseHTTPRequestHandler):
    """HTTP test double that records every POST (tool call) for inspection."""

    calls: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body.decode(errors="replace")}
        RecordingHandler.calls.append(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"result": {"success": True}}).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"alive"}')

    def log_message(self, *a, **k):
        pass


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def _run_hook(tmp_path, server_url, extra_env=None, cwd=None):
    """Run session-start with a given server URL and return (stdout, tool_calls).

    cwd defaults to tmp_path. Pass a different cwd to test workspace-local
    continuity cache discovery independently of HOME.
    """
    RecordingHandler.calls = []
    workdir = cwd if cwd is not None else tmp_path
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "UNITARES_SERVER_URL": server_url,
        "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "PWD": str(workdir),
        "USER": "testuser",
    }
    if extra_env:
        env.update(extra_env)

    hook = PLUGIN_ROOT / "hooks" / "session-start"
    result = subprocess.run(
        [str(hook)],
        env=env,
        cwd=str(workdir),
        input="{}",
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    return result.stdout, list(RecordingHandler.calls)


def _serve_and_run(tmp_path, **run_kwargs):
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        return _run_hook(tmp_path, f"http://127.0.0.1:{port}", **run_kwargs)
    finally:
        srv.shutdown()
        thread.join(timeout=2)


class TestSessionStartMakesNoToolCalls:
    """The hook's single most important invariant: no governance mutations on start."""

    def test_online_path_emits_zero_tool_calls(self, tmp_path):
        _, calls = _serve_and_run(tmp_path)
        tool_calls = [c.get("name") for c in calls if isinstance(c, dict)]
        assert tool_calls == [], (
            f"SessionStart must not invoke any governance tools; saw: {tool_calls}"
        )

    def test_offline_path_emits_zero_tool_calls(self, tmp_path):
        _, calls = _run_hook(tmp_path, "http://127.0.0.1:1")
        tool_calls = [c.get("name") for c in calls if isinstance(c, dict)]
        assert tool_calls == []


class TestSessionStartContext:
    """Context wording teaches the agent how to bind its own identity."""

    def test_online_context_offers_fresh_onboard(self, tmp_path):
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "UNITARES Governance: ONLINE" in ctx
        assert "No identity has been created on your behalf" in ctx
        assert "onboard(" in ctx

    def test_online_context_instructs_force_new_on_fresh_onboard(self, tmp_path):
        """Regression guard: a bare `onboard()` suggestion lets the server
        pin-resume a prior agent's UUID by IP:UA fingerprint alone on shared
        hosts (PATH 2 bleed — server emits `identity_hijack_suspected` with
        path='path2_ipua_pin'). The default fresh-mint suggestion must pass
        `force_new=true` so the server cannot silently adopt an unrelated
        identity.

        See KG council follow-up to #83 (server-side PATH 2 observation)
        and the companion server PR #92.
        """
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "force_new=true" in ctx, (
            "Fresh-onboard suggestion must include force_new=true to avoid "
            "silent pin-resume. Context was: " + ctx[:500]
        )

    def test_online_context_does_not_offer_agent_uuid_resume_by_default(self, tmp_path):
        """agent_uuid resume is a hijack vector when paired with cross-instance
        UUID enumeration. Surfacing it in the default menu invites fresh agents
        to pick someone else's UUID. Recovery via known UUID still works as an
        explicit operator action via /diagnose, but the hook must not advertise
        it as a first-call option.

        See KG bug 2026-04-20T00:09:51.
        """
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "identity(agent_uuid=" not in ctx
        assert "bind_session(agent_uuid=" not in ctx

    def test_offline_context_reports_offline_without_fake_identity(self, tmp_path):
        stdout, _ = _run_hook(tmp_path, "http://127.0.0.1:1")
        ctx = json.loads(stdout).get("additional_context", "")
        assert "OFFLINE" in ctx
        assert "provisional identity" not in ctx.lower()
        assert "uuid:" not in ctx.lower()


class TestS11BannerShape:
    """Post-S11 banner contract (docs/ontology/plan.md S11 + ontology v2 in
    docs/ontology/identity.md, in the unitares repo).

    The banner leads with `force_new=true` as THE recommendation (not one of
    two peer alternatives). Lineage is the honest cross-process bond and is
    referenced via `parent_agent_id`. The pre-S11 footgun warning that
    framed `force_new=true` as "load-bearing" mitigation is dropped (PR #16
    repaired the underlying server-side pin-resume issue).
    """

    def test_banner_leads_with_force_new(self, tmp_path):
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        # `force_new=true` must appear before any other onboard()-shaped
        # suggestion. The pre-S11 banner suggested a bare onboard() first
        # and only mentioned force_new as a pin-resume mitigation.
        force_new_idx = ctx.find("force_new=true")
        assert force_new_idx >= 0, "banner must mention force_new=true"
        # No bare onboard() recommendation that lacks force_new=true.
        # We allow other contexts to mention onboard() — but the lead
        # recommendation must be the force_new+lineage shape.
        assert "force_new=true" in ctx
        assert "spawn_reason" in ctx, (
            "Lead recommendation must include spawn_reason — that's the "
            "honest signal that this is a new process-instance."
        )

    def test_banner_drops_load_bearing_warning(self, tmp_path):
        """Pre-S11 banner warned that `force_new=true` was 'load-bearing'
        as a pin-resume mitigation. PR #16 in the unitares server repo
        repaired the underlying footgun, and the new ontology frames
        force_new as the default posture, not a defensive override.
        """
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "load-bearing" not in ctx.lower()
        assert "pin-resume" not in ctx.lower()

    def test_banner_cites_ontology(self, tmp_path):
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "docs/ontology/identity.md" in ctx, (
            "Banner must cite the v2 ontology by path."
        )

    def test_lineage_hint_uses_parent_agent_id_framing(self, tmp_path):
        """When a workspace cache is present, the banner must present its
        UUID as a `parent_agent_id` candidate, not as a resume credential.
        """
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".unitares").mkdir()
        (workspace / ".unitares" / "session.json").write_text(json.dumps({
            "schema": 2,
            "uuid": "deadbeef-1111-2222-3333-444444444444",
            "agent_id": "Prior_Process",
            "updated_at": "2026-04-20T00:00:00+00:00",
        }))
        stdout, _ = _serve_and_run(tmp_path, cwd=workspace)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "parent_agent_id" in ctx
        assert "deadbeef-1111-2222-3333-444444444444" in ctx
        # Lineage framing — not resume framing.
        assert "lineage" in ctx.lower()
        assert "To resume that identity" not in ctx


class TestNoCrossInstanceUuidEnumeration:
    """Regression guard: the hook must NOT enumerate ~/.unitares/session-*.json.

    That file glob produced an unfiltered menu of every UUID that had ever
    onboarded from this host — across every Claude tab, Codex run, and
    subagent. Combined with an `identity(agent_uuid=..., resume=true)`
    suggestion in the same context block, fresh agents pattern-matched on
    model name and resumed into other instances' identities. KG bug
    2026-04-20T00:09:51. The fix removes the enumeration entirely.
    """

    def test_does_not_list_other_instances_session_files(self, tmp_path):
        unitares = tmp_path / ".unitares"
        unitares.mkdir()
        # Two session files belonging to two unrelated prior instances —
        # neither owned by the current workspace.
        (unitares / "session-aaaaaaaaaaaa.json").write_text(json.dumps({
            "uuid": "aaaaaaaa-1111-2222-3333-444444444444",
            "display_name": "Other-Instance-A",
            "updated_at": "2026-04-19T12:00:00+00:00",
        }))
        (unitares / "session-bbbbbbbbbbbb.json").write_text(json.dumps({
            "uuid": "bbbbbbbb-1111-2222-3333-444444444444",
            "display_name": "Other-Instance-B",
            "updated_at": "2026-04-19T13:00:00+00:00",
        }))

        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")

        # Neither UUID nor label may appear — surfacing them is the hijack vector.
        assert "aaaaaaaa-1111-2222-3333-444444444444" not in ctx
        assert "bbbbbbbb-1111-2222-3333-444444444444" not in ctx
        assert "Other-Instance-A" not in ctx
        assert "Other-Instance-B" not in ctx
        # The misleading section header must be gone.
        assert "Recent session UUIDs on this host" not in ctx


class TestWorkspaceLocalLineage:
    """Post-S11 contract (docs/ontology/plan.md + docs/ontology/identity.md
    in the unitares repo): the workspace-local cache is no longer surfaced
    as a resume credential. Per the v2 ontology, the cached UUID identifies
    a *prior process-instance* that ran in this workspace — process-instance
    continuity ended when that process ended. The honest use is as a
    *lineage candidate* via parent_agent_id, not as a resume target.
    """

    def test_surfaces_lineage_candidate_when_workspace_cache_present(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".unitares").mkdir()
        (workspace / ".unitares" / "session.json").write_text(json.dumps({
            "schema": 2,
            "uuid": "ffffffff-1111-2222-3333-444444444444",
            "agent_id": "Claude_Workspace_X",
            "updated_at": "2026-04-20T00:00:00+00:00",
        }))

        stdout, _ = _serve_and_run(tmp_path, cwd=workspace)
        ctx = json.loads(stdout).get("additional_context", "")

        # The hint must frame the cached UUID as a lineage candidate,
        # not as a resume credential. parent_agent_id is the honest bond.
        assert "lineage" in ctx.lower(), (
            "Cache hint must use lineage framing, not resume framing. "
            "Context: " + ctx[:600]
        )
        assert "parent_agent_id" in ctx
        # Surfacing the bare UUID is intentional under the new ontology —
        # it is the lineage-candidate identifier the agent declares as
        # parent_agent_id. (Hijack risk is addressed by the framing: it's
        # a parent reference, not a UUID-to-resume-as.)
        assert "ffffffff-1111-2222-3333-444444444444" in ctx
        # And it must NOT be presented as a resume credential.
        assert "To resume" not in ctx
        assert "resume that identity" not in ctx

    def test_v1_cache_uuid_is_surfaced_as_lineage_not_resume(self, tmp_path):
        """A v1 cache (with continuity_token, no schema marker) must still
        be readable for its lineage UUID, but the token must NOT be
        surfaced as a resume credential.
        """
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".unitares").mkdir()
        (workspace / ".unitares" / "session.json").write_text(json.dumps({
            # Legacy v1 shape — no schema field, has continuity_token.
            "uuid": "11111111-2222-3333-4444-555555555555",
            "agent_id": "Legacy_Agent",
            "continuity_token": "v1.legacy-token.signature",
            "client_session_id": "legacy-sid",
            "updated_at": "2026-04-19T00:00:00+00:00",
        }))

        stdout, _ = _serve_and_run(tmp_path, cwd=workspace)
        ctx = json.loads(stdout).get("additional_context", "")

        # UUID surfaces as lineage candidate.
        assert "11111111-2222-3333-4444-555555555555" in ctx
        assert "lineage" in ctx.lower()
        # The v1 token must NOT be surfaced as a resume credential.
        assert "v1.legacy-token.signature" not in ctx
        assert "To resume" not in ctx

    def test_no_workspace_cache_means_no_lineage_hint(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        stdout, _ = _serve_and_run(tmp_path, cwd=workspace)
        ctx = json.loads(stdout).get("additional_context", "")
        # No workspace cache → no lineage hint block.
        assert "Lineage candidate" not in ctx


class TestSkillInjection:
    """Fundamentals skill content is injected on both paths (online/offline)."""

    def test_online_context_includes_skill(self, tmp_path):
        stdout, _ = _serve_and_run(tmp_path)
        ctx = json.loads(stdout).get("additional_context", "")
        assert "Governance Fundamentals" in ctx

    def test_offline_context_includes_skill(self, tmp_path):
        stdout, _ = _run_hook(tmp_path, "http://127.0.0.1:1")
        ctx = json.loads(stdout).get("additional_context", "")
        assert "Governance Fundamentals" in ctx
