"""session_cache.py writes session and milestone files mode 0600.

The session cache carries continuity tokens. A world-readable cache lets
any same-UID process on the host read another agent's token and
impersonate it against the governance API. Guards against regressing
_write_json back to Path.write_text (which inherits umask 022 → 0644).
"""

from __future__ import annotations

import json
import os
import stat as _stat
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_cache.py"


def _run(args: list[str], workspace: Path, stdin: str | None = None) -> str:
    cmd = [sys.executable, str(SCRIPT), *args, "--workspace", str(workspace)]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, input=stdin
    )
    return result.stdout.strip()


def test_set_session_writes_mode_0600(tmp_path: Path) -> None:
    _run(
        ["set", "session", "--json", '{"continuity_token": "secret-abc"}'],
        tmp_path,
    )
    cache_file = tmp_path / ".unitares" / "session.json"
    assert cache_file.exists()
    assert _stat.S_IMODE(os.stat(cache_file).st_mode) == 0o600


def test_bump_edit_milestone_writes_mode_0600(tmp_path: Path) -> None:
    """Milestone doesn't carry tokens, but perm consistency matters —
    all writers in this helper should emit 0600 files."""
    _run(["bump-edit", "--file-path", "/w/a.py"], tmp_path)
    milestone = tmp_path / ".unitares" / "last-milestone.json"
    assert milestone.exists()
    assert _stat.S_IMODE(os.stat(milestone).st_mode) == 0o600


def test_set_session_overwrite_tightens_loose_mode(tmp_path: Path) -> None:
    """If a pre-existing cache was written 0644 by an older version,
    the next write must tighten it to 0600 — old loose permissions
    must not leak through."""
    cache_dir = tmp_path / ".unitares"
    cache_dir.mkdir()
    legacy = cache_dir / "session.json"
    legacy.write_text(json.dumps({"continuity_token": "old-secret"}))
    os.chmod(legacy, 0o644)
    assert _stat.S_IMODE(os.stat(legacy).st_mode) == 0o644

    _run(
        ["set", "session", "--json", '{"continuity_token": "new-secret"}'],
        tmp_path,
    )
    assert _stat.S_IMODE(os.stat(legacy).st_mode) == 0o600
