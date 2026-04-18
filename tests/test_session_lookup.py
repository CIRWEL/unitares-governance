"""Unit tests for scripts/_session_lookup.py — slot-aware cache read."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from _session_lookup import (
    _extract_slot,
    _slot_filename,
    load_session_for_hook,
    resolve_session_file,
)


def test_slot_filename_matches_onboard_helper():
    """Must stay byte-identical with onboard_helper._slot_filename."""
    from onboard_helper import _slot_filename as onboard_slot_filename  # type: ignore
    assert _slot_filename("abc-xyz") == onboard_slot_filename("abc-xyz")
    assert _slot_filename(None) == onboard_slot_filename(None)
    assert _slot_filename("") == onboard_slot_filename("")


def test_extract_slot_handles_missing_payload():
    assert _extract_slot("") is None
    assert _extract_slot("{}") is None
    assert _extract_slot("not json") is None


def test_extract_slot_reads_session_id():
    assert _extract_slot('{"session_id":"abc-123"}') == "abc-123"


def test_resolve_prefers_slotted_file(tmp_path):
    (tmp_path / ".unitares").mkdir()
    slotted_name = _slot_filename("my-slot")
    slotted = tmp_path / ".unitares" / slotted_name
    unslotted = tmp_path / ".unitares" / "session.json"
    slotted.write_text("{}")
    unslotted.write_text("{}")
    assert resolve_session_file(tmp_path, "my-slot") == slotted


def test_resolve_falls_back_to_unslotted(tmp_path):
    (tmp_path / ".unitares").mkdir()
    unslotted = tmp_path / ".unitares" / "session.json"
    unslotted.write_text("{}")
    # slot is set but no slotted file exists; fall back
    assert resolve_session_file(tmp_path, "my-slot") == unslotted


def test_resolve_returns_none_when_nothing_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "nonexistent_home"))
    assert resolve_session_file(tmp_path, None) is None


def test_load_session_for_hook_full_roundtrip(tmp_path):
    (tmp_path / ".unitares").mkdir()
    slot = "session-4321"
    path = tmp_path / ".unitares" / _slot_filename(slot)
    payload = {
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-test1234",
        "continuity_token": "v1.faketoken",
        "slot": slot,
    }
    path.write_text(json.dumps(payload))
    result = load_session_for_hook(tmp_path, json.dumps({"session_id": slot}))
    assert result["uuid"] == payload["uuid"]
    assert result["client_session_id"] == payload["client_session_id"]
    assert result["continuity_token"] == payload["continuity_token"]
    assert result["slot"] == slot


def test_load_session_for_hook_empty_stdin_falls_back(tmp_path):
    (tmp_path / ".unitares").mkdir()
    unslotted = tmp_path / ".unitares" / "session.json"
    unslotted.write_text('{"uuid":"u","client_session_id":"c","continuity_token":"t","slot":"s"}')
    result = load_session_for_hook(tmp_path, "")
    assert result["uuid"] == "u"


def test_home_fallback_removed_closes_cross_agent_siphoning(tmp_path, monkeypatch):
    """Regression: ~/.unitares/session.json must NOT be silently shared
    across parallel agents.

    Scenario reproduces the 2026-04-18 siphoning incident: one agent writes
    its identity to $HOME/.unitares/session.json (via legacy onboard_helper
    or older hook). A second Claude Code session in a different workspace
    starts, its own slotted cache is empty, and resolve_session_file is
    called. Before this fix it would fall through to the HOME file and the
    second agent would silently adopt the first's UUID — identity-invariant
    #3 violation (per-instance isolation). After the fix it returns None.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    shared_home_cache = fake_home / ".unitares"
    shared_home_cache.mkdir()
    # Simulate a stale identity from a prior session sitting in $HOME
    (shared_home_cache / "session.json").write_text(json.dumps({
        "uuid": "stolen-uuid-from-another-agent",
        "client_session_id": "agent-stolen",
        "continuity_token": "v1.stolen_token",
    }))
    monkeypatch.setenv("HOME", str(fake_home))

    # Different workspace, empty .unitares — the vulnerable case
    other_workspace = tmp_path / "other_workspace"
    other_workspace.mkdir()

    result_path = resolve_session_file(other_workspace, "some-slot")
    assert result_path is None, (
        f"HOME fallback must not leak across workspaces; got {result_path}"
    )

    # And the hook-level helper must also return empty, not silently siphon
    hook_result = load_session_for_hook(
        other_workspace, json.dumps({"session_id": "some-slot"}),
    )
    assert hook_result == {}, (
        f"load_session_for_hook must return empty rather than siphoning "
        f"from $HOME; got {hook_result}"
    )


def test_workspace_local_unslotted_still_reachable(tmp_path):
    """Sanity: the per-workspace unslotted fallback is preserved — it's
    scoped to the workspace dir so cross-workspace collision is impossible."""
    ws = tmp_path / "ws"
    (ws / ".unitares").mkdir(parents=True)
    (ws / ".unitares" / "session.json").write_text('{"uuid":"ws-local"}')
    result = resolve_session_file(ws, None)
    assert result == ws / ".unitares" / "session.json"
    assert json.loads(result.read_text())["uuid"] == "ws-local"


def test_home_path_still_reachable_when_workspace_is_home(tmp_path, monkeypatch):
    """CLI / ad-hoc tools that genuinely want the HOME-level file can still
    get it by passing workspace=$HOME explicitly. This is the "be explicit
    about shared identity" escape hatch the axiom allows."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".unitares").mkdir()
    (fake_home / ".unitares" / "session.json").write_text('{"uuid":"cli-shared"}')
    monkeypatch.setenv("HOME", str(fake_home))

    # Explicit home workspace — identity sharing is opt-in, not fallback
    result = resolve_session_file(fake_home, None)
    assert result == fake_home / ".unitares" / "session.json"
