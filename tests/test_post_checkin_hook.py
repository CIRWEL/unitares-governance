"""Integration test for hooks/post-checkin.

The hook is a small shell script, but its contract — reset the accumulator
and stamp session.last_checkin_ts whenever process_agent_update runs — is
load-bearing for the auto-checkin forcing function. A broken or missing
reset causes the post-edit hook to re-fire on the very next edit.

S20 §3.5 (2026-04-26): the cache write must be slot-scoped, sourced from
the session_id in the hook's stdin payload. Tests now pass session_id and
seed slotted caches.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_CACHE = ROOT / "scripts" / "session_cache.py"
POST_CHECKIN = ROOT / "hooks" / "post-checkin"

DEFAULT_SLOT = "test-slot-checkin"


def _seed_session(workspace: Path, slot: str = DEFAULT_SLOT, **extra) -> None:
    payload = {
        "client_session_id": "sid-xyz",
        "continuity_token": "ct-abc",
        **extra,
    }
    cmd = [
        sys.executable,
        str(SESSION_CACHE),
        "set",
        "session",
        "--workspace",
        str(workspace),
        "--stamp",
        "--json",
        json.dumps(payload),
    ]
    if slot:
        cmd.extend(["--slot", slot])
    subprocess.run(cmd, check=True, capture_output=True)


def _seed_milestone_edits(workspace: Path, n: int) -> None:
    for i in range(n):
        subprocess.run(
            [
                sys.executable,
                str(SESSION_CACHE),
                "bump-edit",
                "--workspace",
                str(workspace),
                "--file-path",
                f"/w/f{i}.py",
            ],
            check=True,
            capture_output=True,
        )


def _read(kind: str, workspace: Path, slot: str = "") -> dict:
    cmd = [
        sys.executable,
        str(SESSION_CACHE),
        "get",
        kind,
        "--workspace",
        str(workspace),
    ]
    if slot:
        cmd.extend(["--slot", slot])
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _run_hook(
    workspace: Path,
    tool_name: str = "mcp__unitares__process_agent_update",
    session_id: str | None = DEFAULT_SLOT,
):
    payload_dict: dict = {"tool_name": tool_name, "tool_input": {}}
    if session_id:
        payload_dict["session_id"] = session_id
    payload = json.dumps(payload_dict)
    return subprocess.run(
        ["bash", str(POST_CHECKIN)],
        input=payload,
        text=True,
        cwd=str(workspace),
        capture_output=True,
    )


def test_hook_resets_accumulator_and_stamps_last_checkin(tmp_path: Path) -> None:
    _seed_session(tmp_path)
    _seed_milestone_edits(tmp_path, 3)

    before_milestone = _read("milestone", tmp_path)
    assert before_milestone["edit_count"] == 3
    assert before_milestone["first_edit_ts"] is not None

    before_ts = int(time.time())
    result = _run_hook(tmp_path)
    assert result.returncode == 0, result.stderr

    after_milestone = _read("milestone", tmp_path)
    assert after_milestone["edit_count"] == 0
    assert after_milestone["files_touched"] == []
    assert after_milestone["first_edit_ts"] is None
    assert after_milestone["last_edit_ts"] is None

    # last_checkin_ts is stamped in the slot-scoped file, NOT flat session.json
    after_session = _read("session", tmp_path, slot=DEFAULT_SLOT)
    assert "last_checkin_ts" in after_session
    assert int(after_session["last_checkin_ts"]) >= before_ts


def test_hook_is_noop_without_session(tmp_path: Path) -> None:
    # Never onboarded — the hook must not create files or crash. Claude will
    # install this plugin in workspaces that never call governance, and we
    # don't want the hook to leave behind a stub .unitares/ directory.
    result = _run_hook(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".unitares").exists()


def test_hook_updates_last_checkin_on_each_call(tmp_path: Path) -> None:
    _seed_session(tmp_path, last_checkin_ts=1_000_000_000)
    _seed_milestone_edits(tmp_path, 1)

    _run_hook(tmp_path)
    first = _read("session", tmp_path, slot=DEFAULT_SLOT)["last_checkin_ts"]
    assert int(first) > 1_000_000_000

    # A second check-in should push the stamp forward, not preserve the
    # original — the forcing function relies on last_checkin_ts tracking
    # the most recent successful check-in.
    time.sleep(1)
    _seed_milestone_edits(tmp_path, 1)
    _run_hook(tmp_path)
    second = _read("session", tmp_path, slot=DEFAULT_SLOT)["last_checkin_ts"]
    assert int(second) >= int(first)


def test_hook_does_not_write_flat_session_when_stdin_lacks_session_id(tmp_path: Path) -> None:
    # S20 §3.5: when stdin has no session_id, the hook must NOT fall back to
    # flat session.json. The slot-scoped session it can't see remains
    # unchanged; nothing is written to the flat path.
    _seed_session(tmp_path, last_checkin_ts=1_000_000_000)
    _seed_milestone_edits(tmp_path, 2)

    result = _run_hook(tmp_path, session_id=None)
    assert result.returncode == 0, result.stderr

    # Slot-scoped session is unchanged (hook cannot see it without stdin slot)
    after_session = _read("session", tmp_path, slot=DEFAULT_SLOT)
    assert int(after_session["last_checkin_ts"]) == 1_000_000_000

    # Flat session.json is NOT created as a fallback. This is the load-
    # bearing assertion: pre-S20.1a, the helper would have happily written
    # flat session.json on the no-slot path, defeating partition.
    flat = tmp_path / ".unitares" / "session.json"
    assert not flat.exists(), "hook must not write flat session.json when no slot is known"
