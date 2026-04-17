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
