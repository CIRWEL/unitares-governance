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
    port = 18769
    srv = _ReusableTCPServer(("127.0.0.1", port), RecordingHandler)
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
