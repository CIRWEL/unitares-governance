"""Integration test for hooks/post-checkin.

The hook is a small shell script, but its contract — reset the accumulator
and stamp session.last_checkin_ts whenever process_agent_update runs — is
load-bearing for the auto-checkin forcing function. A broken or missing
reset causes the post-edit hook to re-fire on the very next edit.
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


def _seed_session(workspace: Path, **extra) -> None:
    payload = {
        "client_session_id": "sid-xyz",
        "continuity_token": "ct-abc",
        **extra,
    }
    subprocess.run(
        [
            sys.executable,
            str(SESSION_CACHE),
            "set",
            "session",
            "--workspace",
            str(workspace),
            "--stamp",
            "--json",
            json.dumps(payload),
        ],
        check=True,
        capture_output=True,
    )


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


def _read(kind: str, workspace: Path) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SESSION_CACHE),
            "get",
            kind,
            "--workspace",
            str(workspace),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _run_hook(workspace: Path, tool_name: str = "mcp__unitares__process_agent_update"):
    payload = json.dumps({"tool_name": tool_name, "tool_input": {}})
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

    after_session = _read("session", tmp_path)
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
    first = _read("session", tmp_path)["last_checkin_ts"]
    assert int(first) > 1_000_000_000

    # A second check-in should push the stamp forward, not preserve the
    # original — the forcing function relies on last_checkin_ts tracking
    # the most recent successful check-in.
    time.sleep(1)
    _seed_milestone_edits(tmp_path, 1)
    _run_hook(tmp_path)
    second = _read("session", tmp_path)["last_checkin_ts"]
    assert int(second) >= int(first)
