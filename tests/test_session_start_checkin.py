"""Contract tests for the SessionStart hook.

After the identity-honesty Part C refactor, the hook does NOT create an
identity on the agent's behalf. It only confirms governance is reachable
and emits context instructing the agent to make its own first MCP tool
call (onboard / identity / bind_session). The post-identity PostToolUse
hook captures the response and writes the session cache.

These tests lock in the new contract:
  1. Hook emits ZERO HTTP tool calls on SessionStart.
  2. Online context describes the provisional-free state and lists the
     three first-call options.
  3. Offline context reports OFFLINE and does not reference a fake identity.
  4. Recent session UUIDs (if any in ~/.unitares/) surface as resume hints.
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


def _run_hook(tmp_path, server_url, extra_env=None):
    """Run session-start with a given server URL and return (stdout, tool_calls)."""
    RecordingHandler.calls = []
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "UNITARES_SERVER_URL": server_url,
        "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "PWD": str(tmp_path),
        "USER": "testuser",
    }
    if extra_env:
        env.update(extra_env)

    hook = PLUGIN_ROOT / "hooks" / "session-start"
    result = subprocess.run(
        [str(hook)],
        env=env,
        cwd=str(tmp_path),
        input="{}",
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    return result.stdout, list(RecordingHandler.calls)


class TestSessionStartMakesNoToolCalls:
    """The hook's single most important invariant: no governance mutations on start."""

    def test_online_path_emits_zero_tool_calls(self, tmp_path):
        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            _, calls = _run_hook(tmp_path, f"http://127.0.0.1:{port}")
        finally:
            srv.shutdown()
            thread.join(timeout=2)

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

    def test_online_context_names_three_first_call_options(self, tmp_path):
        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            stdout, _ = _run_hook(tmp_path, f"http://127.0.0.1:{port}")
        finally:
            srv.shutdown()
            thread.join(timeout=2)

        ctx = json.loads(stdout).get("additional_context", "")
        assert "UNITARES Governance: ONLINE" in ctx
        assert "No identity has been created on your behalf" in ctx
        assert "onboard(" in ctx
        assert "identity(agent_uuid=" in ctx
        assert "bind_session(agent_uuid=" in ctx

    def test_offline_context_reports_offline_without_fake_identity(self, tmp_path):
        stdout, _ = _run_hook(tmp_path, "http://127.0.0.1:1")
        ctx = json.loads(stdout).get("additional_context", "")
        assert "OFFLINE" in ctx
        assert "provisional identity" not in ctx.lower()
        assert "uuid:" not in ctx.lower()

    def test_online_context_surfaces_recent_uuids_when_present(self, tmp_path):
        """Existing ~/.unitares/session-*.json entries surface as resume hints."""
        unitares = tmp_path / ".unitares"
        unitares.mkdir()
        (unitares / "session-abc.json").write_text(json.dumps({
            "uuid": "11111111-2222-3333-4444-555555555555",
            "display_name": "Prior-Session",
            "updated_at": "2026-04-17T12:00:00+00:00",
        }))

        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            stdout, _ = _run_hook(tmp_path, f"http://127.0.0.1:{port}")
        finally:
            srv.shutdown()
            thread.join(timeout=2)

        ctx = json.loads(stdout).get("additional_context", "")
        assert "Recent session UUIDs" in ctx
        assert "11111111-2222-3333-4444-555555555555" in ctx
        assert "Prior-Session" in ctx

    def test_online_context_omits_recent_uuids_when_none_exist(self, tmp_path):
        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            stdout, _ = _run_hook(tmp_path, f"http://127.0.0.1:{port}")
        finally:
            srv.shutdown()
            thread.join(timeout=2)

        ctx = json.loads(stdout).get("additional_context", "")
        assert "Recent session UUIDs" not in ctx


class TestSkillInjection:
    """Fundamentals skill content is injected on both paths (online/offline)."""

    def test_online_context_includes_skill(self, tmp_path):
        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            stdout, _ = _run_hook(tmp_path, f"http://127.0.0.1:{port}")
        finally:
            srv.shutdown()
            thread.join(timeout=2)

        ctx = json.loads(stdout).get("additional_context", "")
        assert "Governance Fundamentals" in ctx

    def test_offline_context_includes_skill(self, tmp_path):
        stdout, _ = _run_hook(tmp_path, "http://127.0.0.1:1")
        ctx = json.loads(stdout).get("additional_context", "")
        assert "Governance Fundamentals" in ctx
