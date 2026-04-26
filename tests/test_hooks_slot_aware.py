"""Regression test: post-stop, session-end, and post-edit all find the
slotted session cache when Claude Code passes a session_id on stdin.

Before commit that introduces scripts/_session_lookup.py, these hooks
read only the unslotted session.json and silently exited when the
slotted file was the only one present.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
import sys

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _session_lookup import _slot_filename  # noqa: E402

from tests.test_session_start_checkin import RecordingHandler, _ReusableTCPServer  # noqa: E402


def _seed_slotted_cache(workspace: Path, slot: str, payload: dict) -> Path:
    unitares = workspace / ".unitares"
    unitares.mkdir(exist_ok=True)
    path = unitares / _slot_filename(slot)
    path.write_text(json.dumps(payload))
    return path


def _run_hook_with_mock_server(
    hook_name: str,
    workspace: Path,
    slot: str,
    extra_stdin_fields: dict = None,
):
    """Launch mock server, invoke hook with {"session_id": slot}, collect calls."""
    RecordingHandler.calls = []
    srv = _ReusableTCPServer(("127.0.0.1", 0), RecordingHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    stdin_payload = {"session_id": slot}
    if extra_stdin_fields:
        stdin_payload.update(extra_stdin_fields)
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(workspace),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(workspace / "checkins.log"),
            "UNITARES_AUTO_CHECKIN_ENABLED": "1",
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(workspace),
        }
        hook = PLUGIN_ROOT / "hooks" / hook_name
        subprocess.run(
            [str(hook)],
            env=env,
            cwd=str(workspace),
            input=json.dumps(stdin_payload),
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)
    return [c for c in RecordingHandler.calls if c.get("name") == "process_agent_update"]


def test_post_stop_reads_slotted_cache(tmp_path):
    slot = "real-slot-1234"
    _seed_slotted_cache(tmp_path, slot, {
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-real-1234",
        "continuity_token": "v1.real-tok",
        "slot": slot,
    })
    checkins = _run_hook_with_mock_server("post-stop", tmp_path, slot)
    events = [c["arguments"]["metadata"]["event"] for c in checkins]
    assert "turn_stop" in events, (
        f"post-stop did not fire turn_stop when only the slotted cache existed; "
        f"events: {events}"
    )


def test_session_end_reads_slotted_cache(tmp_path):
    slot = "real-slot-5678"
    _seed_slotted_cache(tmp_path, slot, {
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-real-5678",
        "continuity_token": "v1.real-tok",
        "slot": slot,
    })
    checkins = _run_hook_with_mock_server("session-end", tmp_path, slot)
    events = [c["arguments"]["metadata"]["event"] for c in checkins]
    assert "session_end" in events

    # Fix I1 regression: response_text must not contain a newline.
    session_end_checkins = [
        c for c in checkins
        if c["arguments"]["metadata"]["event"] == "session_end"
    ]
    assert session_end_checkins, "no session_end check-in found"
    text = session_end_checkins[0]["arguments"]["response_text"]
    assert "\n" not in text, f"response_text contains newline: {text!r}"
    assert "check-ins posted" in text


def test_post_edit_reads_slotted_cache(tmp_path):
    slot = "real-slot-9012"
    _seed_slotted_cache(tmp_path, slot, {
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-real-9012",
        "continuity_token": "v1.real-tok",
        "slot": slot,
        "last_checkin_ts": int(time.time()) - 10_000,
    })
    milestone = tmp_path / ".unitares" / "last-milestone.json"
    milestone.write_text(json.dumps({
        "edit_count": 10,
        "files_touched": ["a.py"],
        "last_edit_ts": int(time.time()),
    }))
    checkins = _run_hook_with_mock_server(
        "post-edit", tmp_path, slot,
        extra_stdin_fields={
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tmp_path / "a.py")},
        },
    )
    events = [c["arguments"]["metadata"]["event"] for c in checkins]
    assert "auto_edit" in events, (
        f"post-edit did not fire auto_edit when only the slotted cache existed; "
        f"events: {events}"
    )


def test_post_edit_writes_last_checkin_to_slotted_cache(tmp_path):
    """S20 §3.5 write-path assertion: post-edit's last_checkin_ts stamp lands
    in the slot-scoped file, never falling back to flat session.json.

    Pre-S20.1a, the literal `SLOT="${SLOT:-default}"` fallback at post-edit:192
    plus the slotless `set session` at post-edit:221 produced a write to
    flat session.json (or a workspace-shared `session-default.json`). This
    test pins the corrected slot-scoped write path."""
    slot = "real-slot-write-3456"
    initial_ts = int(time.time()) - 10_000
    _seed_slotted_cache(tmp_path, slot, {
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-real-3456",
        "continuity_token": "v1.real-tok",
        "slot": slot,
        "last_checkin_ts": initial_ts,
    })
    milestone = tmp_path / ".unitares" / "last-milestone.json"
    milestone.write_text(json.dumps({
        "edit_count": 10,
        "files_touched": ["a.py"],
        "last_edit_ts": int(time.time()),
    }))
    _run_hook_with_mock_server(
        "post-edit", tmp_path, slot,
        extra_stdin_fields={
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tmp_path / "a.py")},
        },
    )

    slotted = tmp_path / ".unitares" / _slot_filename(slot)
    assert slotted.exists()
    after = json.loads(slotted.read_text())
    assert int(after.get("last_checkin_ts", 0)) > initial_ts, (
        "slot-scoped last_checkin_ts not bumped — post-edit write may have "
        "fallen back to flat session.json"
    )
    flat = tmp_path / ".unitares" / "session.json"
    assert not flat.exists(), (
        "post-edit wrote flat session.json — slot-scope partition broken"
    )
