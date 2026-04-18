"""Contract test: session-start hook fires a post-onboard check-in.

The test runs the hook with a mock governance server and asserts that
exactly one process_agent_update with event='session_start' is received
after the onboard call.
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
        resp = {
            "result": {
                "success": True,
                "uuid": "test-uuid-12345",
                "agent_id": "test_agent",
                "client_session_id": "agent-test1234",
                "continuity_token": "v1.fake",
                "display_name": "TestAgent",
                "continuity_token_supported": True,
            }
        }
        self.wfile.write(json.dumps(resp).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"alive"}')

    def log_message(self, *a, **k):
        pass


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def test_session_start_emits_post_onboard_checkin(tmp_path):
    """session-start hook posts a check-in with event='session_start'."""
    RecordingHandler.calls = []
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
            # Legacy-path tests: opt back into auto-onboard (default is now 1).
            "UNITARES_DISABLE_AUTO_ONBOARD": "0",
        }
        hook = PLUGIN_ROOT / "hooks" / "session-start"
        # The hook expects a hook-context JSON on stdin (see its `HOOK_INPUT`
        # variable). An empty object is enough — the hook falls back to PWD
        # for the slot.
        subprocess.run(
            [str(hook)],
            env=env,
            input="{}",
            text=True,
            timeout=20,
            check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    checkin_events = [
        c["arguments"].get("metadata", {}).get("event")
        for c in RecordingHandler.calls
        if c.get("name") == "process_agent_update"
    ]
    assert "session_start" in checkin_events, (
        f"no session_start check-in seen; tools received: "
        f"{[c.get('name') for c in RecordingHandler.calls]}"
    )


def test_session_start_context_instructs_first_call_identity_bind(tmp_path):
    """Context surfaced to Claude explicitly instructs the first-MCP-call bind.

    The HTTP onboard done by this hook creates one identity; the MCP stdio
    transport auto-derives a *different* identity from transport signals
    unless the agent calls identity(agent_uuid=..., resume=true) first.
    That instruction must appear verbatim in the SessionStart additional_context
    so Claude actually performs the bind.
    """
    RecordingHandler.calls = []
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
            # Legacy-path tests: opt back into auto-onboard (default is now 1).
            "UNITARES_DISABLE_AUTO_ONBOARD": "0",
        }
        hook = PLUGIN_ROOT / "hooks" / "session-start"
        result = subprocess.run(
            [str(hook)],
            env=env,
            input="{}",
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    context = payload.get("additional_context", "")
    assert "identity(agent_uuid=" in context, (
        "context must instruct `identity(agent_uuid=..., resume=true)` as the "
        "first MCP call — otherwise stdio binds to an auto-derived ghost"
    )
    assert "resume=true" in context, "bind instruction must include resume=true"
    assert "test-uuid-12345" in context, "bind instruction must include the actual UUID"


def test_session_start_context_is_a_receipt_not_an_assertion(tmp_path):
    """SessionStart context reports what was created; it does not assert identity.

    The axiom: 'Never silently substitute identity' (identity-invariants #1).
    Phrasing matters — telling the agent 'Agent: X' is an assertion of fact.
    Telling the agent 'A provisional identity was created' is a receipt the
    agent can accept, override, or ignore.
    """
    RecordingHandler.calls = []
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
            # Legacy-path tests: opt back into auto-onboard (default is now 1).
            "UNITARES_DISABLE_AUTO_ONBOARD": "0",
        }
        hook = PLUGIN_ROOT / "hooks" / "session-start"
        result = subprocess.run(
            [str(hook)], env=env, input="{}", text=True,
            capture_output=True, timeout=20, check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    context = json.loads(result.stdout).get("additional_context", "")
    assert "provisional" in context.lower(), (
        "context must describe the created identity as provisional, not assert it"
    )
    assert "derived from" in context, (
        "context must surface the label's provenance (workspace, USER@date, etc.)"
    )
    assert "not your choice" in context, (
        "context must explicitly name the presumption so the agent can override"
    )
    assert "abandon" in context.lower(), (
        "context must describe the abandon path — orphaned identity is a valid choice"
    )


def test_disable_auto_onboard_emits_no_tool_calls(tmp_path):
    """UNITARES_DISABLE_AUTO_ONBOARD=1 → hook must not invoke any tool calls.

    The whole point of the flag is that the agent's first MCP tool call
    becomes the sole identity-creation path, eliminating the HTTP/stdio
    bifurcation that generated ghosts.
    """
    RecordingHandler.calls = []
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
            "UNITARES_DISABLE_AUTO_ONBOARD": "1",
        }
        hook = PLUGIN_ROOT / "hooks" / "session-start"
        result = subprocess.run(
            [str(hook)], env=env, cwd=str(tmp_path), input="{}", text=True,
            capture_output=True, timeout=20, check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    tool_calls = [c.get("name") for c in RecordingHandler.calls if isinstance(c, dict)]
    assert tool_calls == [], (
        f"hook must not invoke tool calls when auto-onboard is disabled; "
        f"saw: {tool_calls}"
    )

    context = json.loads(result.stdout).get("additional_context", "")
    assert "No identity has been created" in context, (
        "flag-enabled context must state identity was not pre-created"
    )
    assert "onboard(" in context and "identity(agent_uuid=" in context, (
        "context must show the three first-call options (onboard/identity/bind_session)"
    )


def test_disable_auto_onboard_still_reports_offline(tmp_path):
    """Flag does not change the offline path — unreachable server still reports OFFLINE."""
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "UNITARES_SERVER_URL": "http://127.0.0.1:1",
        "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "PWD": str(tmp_path),
        "UNITARES_DISABLE_AUTO_ONBOARD": "1",
    }
    hook = PLUGIN_ROOT / "hooks" / "session-start"
    result = subprocess.run(
        [str(hook)], env=env, cwd=str(tmp_path), input="{}", text=True,
        capture_output=True, timeout=20, check=False,
    )
    context = json.loads(result.stdout).get("additional_context", "")
    assert "OFFLINE" in context


class TestAgentNameDerivation:
    """The hook must not fall back to hostname -s for agent naming.

    Historical bug: a user's Mac hostname was 'The-CIRWEL-Group'. Every
    session started from $HOME inherited that hostname as the agent label,
    leaking a machine-level identifier into session-level identity. The
    new preference order is override → workspace basename → $USER@date,
    with hostname deliberately excluded.
    """

    def _run_hook(self, env_overrides, pwd, tmp_path, input_payload="{}"):
        RecordingHandler.calls = []
        srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": str(tmp_path),
                "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
                "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
                "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
                "PWD": str(pwd),
                "USER": "testuser",
                # Legacy-path: these tests verify the onboard call's name arg.
                "UNITARES_DISABLE_AUTO_ONBOARD": "0",
            }
            env.update(env_overrides)
            hook = PLUGIN_ROOT / "hooks" / "session-start"
            # cwd=pwd is REQUIRED: bash overwrites $PWD at startup to match
            # the actual working directory, so we can't just set PWD in env.
            result = subprocess.run(
                [str(hook)], env=env, cwd=str(pwd), input=input_payload, text=True,
                capture_output=True, timeout=20, check=False,
            )
        finally:
            srv.shutdown()
            thread.join(timeout=2)
        return result, RecordingHandler.calls

    def test_override_file_wins_over_everything(self, tmp_path):
        """~/.unitares/display-name is the top-priority name source."""
        (tmp_path / ".unitares").mkdir()
        (tmp_path / ".unitares" / "display-name").write_text("my-chosen-name\n")

        project = tmp_path / "some-project"
        project.mkdir()
        (project / ".git").mkdir()

        _, calls = self._run_hook({}, project, tmp_path)
        onboard_calls = [c for c in calls if c.get("name") == "onboard"]
        assert onboard_calls, "hook should onboard"
        assert onboard_calls[0]["arguments"].get("name") == "my-chosen-name"

    def test_git_repo_uses_workspace_basename(self, tmp_path):
        """PWD has .git → agent name is the directory basename."""
        project = tmp_path / "my-project"
        project.mkdir()
        (project / ".git").mkdir()

        _, calls = self._run_hook({}, project, tmp_path)
        onboard_calls = [c for c in calls if c.get("name") == "onboard"]
        assert onboard_calls[0]["arguments"].get("name") == "my-project"

    def test_home_dir_uses_user_at_date_not_hostname(self, tmp_path):
        """PWD == HOME and no git → $USER@YYYYMMDD, NEVER the hostname."""
        _, calls = self._run_hook({}, tmp_path, tmp_path)
        onboard_calls = [c for c in calls if c.get("name") == "onboard"]
        name = onboard_calls[0]["arguments"].get("name", "")
        import re
        assert re.match(r"^testuser@\d{8}$", name), (
            f"expected testuser@YYYYMMDD, got {name!r} — hostname fallback must not return"
        )
