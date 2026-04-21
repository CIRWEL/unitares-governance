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


# ---------------------------------------------------------------------------
# Post-S11 lineage-only session cache contract
# (docs/ontology/plan.md S11 + docs/ontology/identity.md in unitares repo)
# ---------------------------------------------------------------------------


def _read_session_file(tmp_path: Path) -> dict:
    raw = (tmp_path / ".unitares" / "session.json").read_text(encoding="utf-8")
    return json.loads(raw)


def test_session_set_strips_continuity_token(tmp_path: Path) -> None:
    """Writing a session payload that includes continuity_token (or any
    other forbidden v1 resume-credential field) must scrub them. The
    written file must contain neither the token nor session_resolution_source.
    """
    payload = {
        "uuid": "u-123",
        "agent_id": "Test",
        "continuity_token": "v1.SHOULD-NOT-BE-WRITTEN",
        "client_session_id": "agent-abc",
        "session_resolution_source": "fingerprint",
        "continuity_token_supported": True,
    }
    _run(
        ["set", "session", "--stamp", "--json", json.dumps(payload)],
        tmp_path,
    )
    cache = _read_session_file(tmp_path)
    assert cache["uuid"] == "u-123"
    assert cache["agent_id"] == "Test"
    assert cache["schema"] == 2, "set session must stamp schema=2"
    assert "updated_at" in cache
    # Forbidden fields must not be persisted.
    assert "continuity_token" not in cache
    assert "client_session_id" not in cache
    assert "session_resolution_source" not in cache
    assert "continuity_token_supported" not in cache


def test_session_get_ignores_v1_continuity_token(tmp_path: Path) -> None:
    """Reading a v1 cache (written by an old plugin version) must surface
    the UUID as a lineage candidate but suppress the continuity_token so
    it cannot be read back as a resume credential.
    """
    cache_dir = tmp_path / ".unitares"
    cache_dir.mkdir()
    # Write a v1-shaped cache directly — no schema field, has token.
    (cache_dir / "session.json").write_text(
        json.dumps({
            "uuid": "u-v1-legacy",
            "agent_id": "Legacy",
            "continuity_token": "v1.legacy-token",
            "client_session_id": "legacy-sid",
            "updated_at": "2026-04-19T00:00:00+00:00",
        })
    )
    raw = _run(["get", "session"], tmp_path)
    payload = json.loads(raw)
    # UUID still surfaces (lineage candidate).
    assert payload["uuid"] == "u-v1-legacy"
    assert payload["agent_id"] == "Legacy"
    # Token MUST NOT surface — even though it's still on disk.
    assert "continuity_token" not in payload
    assert "client_session_id" not in payload


def test_session_get_v1_token_unreachable_via_key_lookup(tmp_path: Path) -> None:
    """Even targeted `--key continuity_token` lookups against a v1 cache
    must return nothing — the read-side scrub is what closes the loop.
    """
    cache_dir = tmp_path / ".unitares"
    cache_dir.mkdir()
    (cache_dir / "session.json").write_text(
        json.dumps({"uuid": "u-x", "continuity_token": "v1.tok"})
    )
    raw = _run(["get", "session", "--key", "continuity_token"], tmp_path)
    assert raw == "", "v1 continuity_token must not be readable via session cache"
    # UUID is still readable.
    raw_uuid = _run(["get", "session", "--key", "uuid"], tmp_path)
    assert raw_uuid == "u-x"
