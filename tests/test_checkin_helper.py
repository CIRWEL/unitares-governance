"""Unit tests for scripts/checkin.py — build/redact/post/log helper."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import checkin  # noqa: E402


def test_kill_switch_skips_post(monkeypatch, tmp_path):
    """UNITARES_CHECKINS=off short-circuits before any network call."""
    log_path = tmp_path / "checkins.log"
    monkeypatch.setenv("UNITARES_CHECKINS", "off")
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(log_path))

    with patch("checkin._post_to_governance") as mock_post:
        result = checkin.submit_checkin(
            event="turn_stop",
            response_text="test",
            complexity=0.3,
            confidence=0.7,
            client_session_id="agent-test1234",
            continuity_token="v1.faketoken",
            slot="test-slot",
        )

    assert result == "skip_kill_switch"
    mock_post.assert_not_called()
    assert log_path.exists()
    line = log_path.read_text().strip()
    assert "status=skip_kill_switch" in line
    assert "event=turn_stop" in line


def test_kill_switch_default_on(monkeypatch, tmp_path):
    """Unset UNITARES_CHECKINS defaults to on."""
    log_path = tmp_path / "checkins.log"
    monkeypatch.delenv("UNITARES_CHECKINS", raising=False)
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(log_path))

    with patch("checkin._post_to_governance", return_value=(True, 42, None)) as mock_post:
        result = checkin.submit_checkin(
            event="session_start",
            response_text="init",
            complexity=0.1,
            confidence=0.9,
            client_session_id="agent-test1234",
            continuity_token="v1.faketoken",
            slot="test-slot",
        )

    assert result == "sent"
    mock_post.assert_called_once()
