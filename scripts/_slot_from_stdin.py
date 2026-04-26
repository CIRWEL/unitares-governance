"""Extract sanitized slot from hook stdin JSON.

Single sanitization site for slot derivation in hooks that need to know
which slot-scoped cache file to write under (S20.1a, 2026-04-26). Hooks
that pre-date this helper (post-identity, session-start) inline the same
logic; converging them is scoped as a follow-up — see plan.md S20.1a
resolution notes.

The sanitization rule mirrors session_cache.py:_slot_suffix and
_session_lookup.py:_slot_filename — alphanumeric, hyphen, underscore;
everything else replaced with underscore; truncated to 64 chars.

Usage:
    SLOT=$(printf '%s' "${HOOK_INPUT}" | python3 scripts/_slot_from_stdin.py)

Outputs the sanitized slot on stdout. Emits empty stdout when stdin is
empty, non-JSON, not a JSON object, or lacks a non-empty session_id —
the caller decides what to do with empty (typically: skip slot-scoped
writes rather than collapsing onto flat session.json).
"""

from __future__ import annotations

import json
import sys


def slot_from_payload(payload: str) -> str:
    """Pure function — exposed for unit tests."""
    if not payload:
        return ""
    try:
        data = json.loads(payload)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    sid = (data.get("session_id") or "").strip()
    if not sid:
        return ""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in sid)
    return safe[:64]


def main() -> int:
    print(slot_from_payload(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
