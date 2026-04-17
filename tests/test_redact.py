"""Unit tests for scripts/_redact.py — secret redaction regexes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from _redact import redact_secrets


def test_redacts_anthropic_api_key():
    text = "ran with ANTHROPIC_API_KEY=sk-ant-api03-abc123DEF456ghi789JKL"
    out = redact_secrets(text)
    assert "sk-ant-api03" not in out
    assert "[REDACTED:anthropic_key]" in out


def test_redacts_openai_api_key():
    text = "curl -H 'Authorization: Bearer sk-proj-abc123DEF456GHI789jkl012MNO345pqr678STU901vwx234'"
    out = redact_secrets(text)
    assert "sk-proj-" not in out
    assert "[REDACTED:openai_key]" in out


def test_redacts_github_token():
    text = "export GH_TOKEN=ghp_abc123DEF456ghi789JKL012mno345PQR"
    out = redact_secrets(text)
    assert "ghp_" not in out
    assert "[REDACTED:github_token]" in out


def test_redacts_aws_access_key():
    text = "AKIAIOSFODNN7EXAMPLE is the key"
    out = redact_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED:aws_key]" in out


def test_preserves_non_secret_text():
    text = "Ran pytest and 257 tests passed"
    assert redact_secrets(text) == text


def test_handles_none_input():
    assert redact_secrets(None) == ""


def test_handles_empty_string():
    assert redact_secrets("") == ""
