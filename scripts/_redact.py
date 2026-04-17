"""Secret redaction for plugin check-in payloads.

Matches common API key / token patterns and replaces them with a labelled
placeholder before text is submitted to governance. Governance data lives
on the operator's own machine, so this is defense in depth — not a
security boundary.

Patterns are deliberately narrow. We'd rather miss some secrets than
mangle legitimate text that happens to look secret-ish.
"""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic_key", re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[a-zA-Z0-9]{32,}")),
    ("github_token", re.compile(r"gh[pousr]_[a-zA-Z0-9]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    ("generic_bearer", re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{40,}\b")),
]


def redact_secrets(text: Optional[str]) -> str:
    """Replace recognized secret patterns in ``text`` with labelled tokens."""
    if not text:
        return ""
    result = text
    for label, pattern in _PATTERNS:
        result = pattern.sub(f"[REDACTED:{label}]", result)
    return result
