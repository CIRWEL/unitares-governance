"""Tests for session_cache.py milestone accumulator.

Covers the behavior the post-edit hook depends on:
  * bump-edit increments the counter and dedupes files_touched
  * first_edit_ts is stamped on first bump, not overwritten after
  * reset-milestone zeros the accumulator but leaves legacy keys alone
  * the files_touched cap is enforced (no unbounded growth)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_cache.py"


def _run(args: list[str], workspace: Path) -> str:
    cmd = [sys.executable, str(SCRIPT), *args, "--workspace", str(workspace)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _read_milestone(workspace: Path) -> dict:
    raw = _run(["get", "milestone"], workspace)
    return json.loads(raw) if raw else {}


def test_bump_edit_increments_counter(tmp_path: Path) -> None:
    _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/b.py"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/c.py"], tmp_path)

    state = _read_milestone(tmp_path)
    assert state["edit_count"] == 3
    assert state["files_touched"] == ["/w/a.py", "/w/b.py", "/w/c.py"]


def test_bump_edit_dedupes_files(tmp_path: Path) -> None:
    for _ in range(4):
        _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/b.py"], tmp_path)

    state = _read_milestone(tmp_path)
    assert state["edit_count"] == 5
    assert state["files_touched"] == ["/w/a.py", "/w/b.py"]


def test_first_edit_ts_only_stamped_once(tmp_path: Path) -> None:
    _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    first = _read_milestone(tmp_path)["first_edit_ts"]

    _run(["bump-edit", "--file-path", "/w/b.py"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/c.py"], tmp_path)
    final = _read_milestone(tmp_path)

    assert final["first_edit_ts"] == first
    # last_edit_ts always updates; first_edit_ts never moves after bump 1.
    assert final["last_edit_ts"] >= first


def test_files_touched_is_capped(tmp_path: Path) -> None:
    # 30 distinct files — cap is 20, should keep only the most recent 20.
    for i in range(30):
        _run(["bump-edit", "--file-path", f"/w/f{i:02d}.py"], tmp_path)

    state = _read_milestone(tmp_path)
    assert state["edit_count"] == 30
    assert len(state["files_touched"]) == 20
    assert state["files_touched"][0] == "/w/f10.py"
    assert state["files_touched"][-1] == "/w/f29.py"


def test_reset_milestone_zeros_accumulator(tmp_path: Path) -> None:
    _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/b.py"], tmp_path)
    _run(["reset-milestone"], tmp_path)

    state = _read_milestone(tmp_path)
    assert state["edit_count"] == 0
    assert state["files_touched"] == []
    assert state["first_edit_ts"] is None
    assert state["last_edit_ts"] is None


def test_bump_after_reset_restamps_first_edit(tmp_path: Path) -> None:
    _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    _run(["reset-milestone"], tmp_path)
    _run(["bump-edit", "--file-path", "/w/b.py"], tmp_path)

    state = _read_milestone(tmp_path)
    assert state["edit_count"] == 1
    assert state["files_touched"] == ["/w/b.py"]
    assert state["first_edit_ts"] is not None
