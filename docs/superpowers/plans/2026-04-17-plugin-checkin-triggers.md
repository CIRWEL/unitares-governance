# Plugin Check-In Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the UNITARES governance plugin to emit check-ins at three new trigger points — SessionStart (post-onboard), Stop (per Claude turn), and SessionEnd — so every plugin-managed agent produces behavioral EISV signal automatically. Existing edit-threshold auto-checkin keeps working; this plan adds event-driven coverage around it.

**Architecture:** Extract a shared `scripts/checkin.py` helper that builds check-in payloads, redacts common secret patterns, POSTs to governance over REST, and logs the outcome to `~/.unitares/checkins.log`. New hook scripts (`hooks/post-stop`, `hooks/session-end`) call into it; existing `hooks/session-start` is extended to fire one check-in immediately after successful onboard; existing `hooks/post-edit` is refactored to use the shared helper without behavior change. A single `UNITARES_CHECKINS=off` kill switch disables every new emission.

**Tech Stack:** Bash (hook scripts), Python 3 (helpers), pytest (tests), existing `session_cache.py` for session persistence, Claude Code hook lifecycle (SessionStart, Stop, SessionEnd, PostToolUse).

---

## Prerequisites

- Governance MCP reachable at `http://localhost:8767` (default) or `$UNITARES_SERVER_URL`.
- Plugin source checkout at `/Users/cirwel/projects/unitares-governance-plugin`.
- Existing helpers reused without modification: `scripts/session_cache.py` (session file I/O), `scripts/onboard_helper.py` (onboard + continuity token).
- Phase 0 deploy step: the plugin cache at `~/.claude/plugins/cache/unitares-governance-plugin/unitares-governance/0.2.0/` is pre-`5ec2eaf`, meaning even the existing auto-checkin is not deployed. Phase 0 bumps plugin version and forces a cache refresh so Phase 1's hooks land along with the already-shipped auto-checkin. Do Phase 0 first.

## Hook Event Catalog (reference)

Per Claude Code docs, these are the hooks we use:

| Hook | When it fires | Our handler |
|---|---|---|
| `SessionStart` (startup\|resume\|clear\|compact) | Session begins or resumes | `hooks/session-start` (extends existing) |
| `Stop` | Claude finishes a turn cleanly | `hooks/post-stop` (new) |
| `SessionEnd` | Window closes / session terminates | `hooks/session-end` (new) |
| `PostToolUse` (Edit\|Write) | After any Edit or Write tool use | `hooks/post-edit` (refactor only) |
| `PostToolUse` (mcp__.*__process_agent_update) | After explicit check-in tool call | `hooks/post-checkin` (unchanged) |

Out of scope for Phase 1: `SubagentStop`, `StopFailure`, `PreCompact`, `PostCompact`, `TaskCreated`, `TaskCompleted`. Tracked in "Future Work" at bottom.

## Payload Schema (contract for every check-in)

Every check-in posted by the plugin has the same shape:

```json
{
  "name": "process_agent_update",
  "arguments": {
    "response_text": "<human-readable summary, <= 512 chars after redaction>",
    "complexity": 0.0-1.0,
    "confidence": 0.0-1.0,
    "client_session_id": "<from session.json>",
    "continuity_token": "<from session.json>",
    "metadata": {
      "source": "plugin_hook",
      "event": "<hook name>",
      "plugin_version": "<from plugin.json>"
    }
  }
}
```

The `metadata.event` field distinguishes the trigger. The server currently ignores `metadata` but writes it to `audit.tool_usage.payload` where it's queryable. The `response_text` drives behavioral EISV.

Per-trigger derivations:

| Trigger | `response_text` | `complexity` | `confidence` |
|---|---|---|---|
| `SessionStart` (post-onboard) | `"Session initialized for <workspace-basename> on branch <git branch>"` | `0.1` | `0.9` |
| `Stop` | `"Turn summary: <N> tool calls (<top-3-tool-names>); response excerpt: <first-120-chars-of-assistant-text>"` | `min(tool_count / 10, 0.85)` | `0.7` |
| `SessionEnd` | `"Session ended: <N> turns, <M> check-ins posted, <duration-minutes>m elapsed"` | `0.1` | `0.9` |
| `PostToolUse(Edit\|Write)` (existing) | unchanged from `auto_checkin_decision.decide()` | unchanged | unchanged |

## Kill Switch

Single env var: `UNITARES_CHECKINS=off` short-circuits every call in `scripts/checkin.py` before any network work. Default is `on`. Set in `~/.unitares/env` or exported in shell rc for per-operator override.

The existing `UNITARES_AUTO_CHECKIN_ENABLED` continues to gate only the edit-threshold hook (don't repurpose it; keeping it narrow avoids surprise).

## Logging

Every check-in attempt appends one line to `~/.unitares/checkins.log`:

```
2026-04-17T02:45:12Z | slot=f99a6b7c | event=turn_stop | uuid=86ae619f | status=sent | latency_ms=42
2026-04-17T02:45:13Z | slot=f99a6b7c | event=session_end | uuid=86ae619f | status=skip_kill_switch
2026-04-17T02:46:01Z | slot=f99a6b7c | event=turn_stop | uuid=86ae619f | status=fail_timeout | err="connect refused"
```

One file per operator, appended atomically (open-append-close per line), rotated by external logrotate config (not our concern). Readable by the operator for diagnosis.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `scripts/checkin.py` | Shared check-in helper: build payload, redact, POST, log |
| `scripts/_redact.py` | Regex-based secret redaction (imported by `checkin.py`) |
| `hooks/post-stop` | Bash wrapper for Stop hook |
| `hooks/session-end` | Bash wrapper for SessionEnd hook |
| `tests/test_checkin_helper.py` | Unit tests for `checkin.py` (payload build, kill switch, log format) |
| `tests/test_redact.py` | Unit tests for secret redaction patterns |

**Modify:**

| Path | Change |
|---|---|
| `hooks/hooks.json` | Add `Stop` and `SessionEnd` entries |
| `hooks/session-start` | After successful onboard, call `checkin.py` with `event=session_start` |
| `hooks/post-edit` | Refactor to use `checkin.py`; behavior unchanged |
| `config/defaults.env` | Add `UNITARES_CHECKINS=on` (new), document `UNITARES_CHECKIN_LOG=~/.unitares/checkins.log` |
| `.claude-plugin/plugin.json` | Bump version 0.2.0 → 0.3.0 (forces cache refresh on next Claude Code load) |

---

## Task List

### Phase 0: Deploy Existing Auto-Checkin

### Task 0: Bump plugin version to force cache refresh

**Files:**
- Modify: `.claude-plugin/plugin.json`

Why: The installed plugin cache at `~/.claude/plugins/cache/unitares-governance-plugin/unitares-governance/0.2.0/` is pre-commit `5ec2eaf` ("restore auto-checkin with threshold-based firing"). Even the edit-threshold check-in is not deployed. A version bump forces Claude Code to refresh the cache on next load, picking up both the existing auto-checkin and the new hooks from this plan.

- [ ] **Step 1: Bump version in `.claude-plugin/plugin.json`**

```json
{
  "name": "unitares-governance",
  "description": "Thermodynamic governance for AI agents — auto-onboard, auto-checkin, EISV monitoring, dialectic reasoning, knowledge graph",
  "version": "0.3.0",
  "author": {"name": "CIRWEL"},
  "homepage": "https://github.com/CIRWEL/unitares-governance-plugin",
  "repository": "https://github.com/CIRWEL/unitares-governance-plugin",
  "license": "MIT",
  "keywords": ["governance", "eisv", "thermodynamic", "multi-agent", "dialectic", "coherence"]
}
```

- [ ] **Step 2: Commit the version bump**

```bash
git add .claude-plugin/plugin.json
git commit -m "bump plugin version to 0.3.0 for check-in trigger rollout"
```

Do NOT push yet. We'll push after Phase 1 lands.

---

### Phase 1: Shared Check-In Helper

### Task 1: Secret redaction module

**Files:**
- Create: `scripts/_redact.py`
- Create: `tests/test_redact.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_redact.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/cirwel/projects/unitares-governance-plugin
python3 -m pytest tests/test_redact.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named '_redact'`.

- [ ] **Step 3: Implement `scripts/_redact.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_redact.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_redact.py tests/test_redact.py
git commit -m "add _redact.py: secret-pattern redaction for check-in payloads"
```

---

### Task 2: Kill switch + log format

**Files:**
- Create: `scripts/checkin.py`
- Create: `tests/test_checkin_helper.py`

- [ ] **Step 1: Write the failing test for kill switch**

Create `tests/test_checkin_helper.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_checkin_helper.py::test_kill_switch_skips_post tests/test_checkin_helper.py::test_kill_switch_default_on -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'checkin'`.

- [ ] **Step 3: Implement `scripts/checkin.py` skeleton**

```python
"""Shared check-in helper for UNITARES governance plugin hooks.

One entry point: ``submit_checkin``. Builds a ``process_agent_update``
REST payload, applies secret redaction, POSTs to the governance server,
and appends one diagnostic line to ``UNITARES_CHECKIN_LOG``.

Fire-and-forget semantics: never raises, always returns a status string
that callers may record. The kill switch ``UNITARES_CHECKINS=off``
short-circuits every call.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from _redact import redact_secrets

DEFAULT_SERVER_URL = "http://localhost:8767"
DEFAULT_LOG_PATH = "~/.unitares/checkins.log"
POST_TIMEOUT_SEC = 5.0
RESPONSE_TEXT_MAX = 512


def _is_killed() -> bool:
    return os.environ.get("UNITARES_CHECKINS", "on").strip().lower() == "off"


def _log_path() -> Path:
    raw = os.environ.get("UNITARES_CHECKIN_LOG", DEFAULT_LOG_PATH)
    return Path(raw).expanduser()


def _append_log(
    *,
    slot: str,
    event: str,
    uuid: str,
    status: str,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Append one line to the diagnostic log. Never raises."""
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = [
            stamp,
            f"slot={slot}",
            f"event={event}",
            f"uuid={uuid[:8] if uuid else '?'}",
            f"status={status}",
        ]
        if latency_ms is not None:
            parts.append(f"latency_ms={latency_ms}")
        if error:
            parts.append(f'err="{error[:120]}"')
        line = " | ".join(parts) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Logging failures are swallowed — we must not break the hook.
        pass


def _post_to_governance(
    url: str,
    payload: dict,
    timeout: float = POST_TIMEOUT_SEC,
) -> tuple[bool, int, Optional[str]]:
    """POST payload to /v1/tools/call. Returns (success, latency_ms, err_text)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/v1/tools/call",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()  # drain
        latency_ms = int((time.monotonic() - t0) * 1000)
        return True, latency_ms, None
    except urllib.error.URLError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return False, latency_ms, str(getattr(e, "reason", e))
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return False, latency_ms, str(e)


def submit_checkin(
    *,
    event: str,
    response_text: str,
    complexity: float,
    confidence: float,
    client_session_id: str,
    continuity_token: str,
    slot: str,
    uuid: str = "",
    server_url: Optional[str] = None,
    plugin_version: str = "0.3.0",
) -> str:
    """Send one check-in. Returns a status string suitable for logging."""
    if _is_killed():
        _append_log(slot=slot, event=event, uuid=uuid, status="skip_kill_switch")
        return "skip_kill_switch"

    safe_text = redact_secrets(response_text)[:RESPONSE_TEXT_MAX]
    url = server_url or os.environ.get("UNITARES_SERVER_URL", DEFAULT_SERVER_URL)

    payload = {
        "name": "process_agent_update",
        "arguments": {
            "response_text": safe_text,
            "complexity": max(0.0, min(1.0, float(complexity))),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "client_session_id": client_session_id,
            "continuity_token": continuity_token,
            "metadata": {
                "source": "plugin_hook",
                "event": event,
                "plugin_version": plugin_version,
            },
        },
    }

    ok, latency_ms, err = _post_to_governance(url, payload)
    status = "sent" if ok else "fail"
    _append_log(
        slot=slot,
        event=event,
        uuid=uuid,
        status=status,
        latency_ms=latency_ms,
        error=err,
    )
    return status
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_checkin_helper.py::test_kill_switch_skips_post tests/test_checkin_helper.py::test_kill_switch_default_on -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/checkin.py tests/test_checkin_helper.py
git commit -m "add checkin.py: shared hook helper with kill switch + log"
```

---

### Task 3: Payload construction and redaction integration

**Files:**
- Modify: `tests/test_checkin_helper.py`

- [ ] **Step 1: Add tests for payload shape and redaction**

Append to `tests/test_checkin_helper.py`:

```python
def test_payload_shape(monkeypatch, tmp_path):
    """Built payload matches the documented contract."""
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(tmp_path / "cl.log"))
    captured: dict = {}

    def fake_post(url, payload, timeout=5.0):
        captured["url"] = url
        captured["payload"] = payload
        return True, 33, None

    with patch("checkin._post_to_governance", side_effect=fake_post):
        checkin.submit_checkin(
            event="turn_stop",
            response_text="did stuff",
            complexity=0.4,
            confidence=0.7,
            client_session_id="agent-abc1234567",
            continuity_token="v1.tok",
            slot="slot-1",
            uuid="86ae619f-87e0-4040-8f29-eacece0c7904",
        )

    args = captured["payload"]["arguments"]
    assert captured["payload"]["name"] == "process_agent_update"
    assert args["response_text"] == "did stuff"
    assert args["complexity"] == 0.4
    assert args["confidence"] == 0.7
    assert args["client_session_id"] == "agent-abc1234567"
    assert args["continuity_token"] == "v1.tok"
    assert args["metadata"]["source"] == "plugin_hook"
    assert args["metadata"]["event"] == "turn_stop"


def test_payload_redacts_secrets(monkeypatch, tmp_path):
    """Secret-looking strings in response_text are redacted before POST."""
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(tmp_path / "cl.log"))
    captured: dict = {}

    def fake_post(url, payload, timeout=5.0):
        captured["payload"] = payload
        return True, 10, None

    with patch("checkin._post_to_governance", side_effect=fake_post):
        checkin.submit_checkin(
            event="turn_stop",
            response_text="Leaked ANTHROPIC_API_KEY=sk-ant-api03-abc123DEF456ghi789JKL012",
            complexity=0.3,
            confidence=0.7,
            client_session_id="agent-x",
            continuity_token="v1.t",
            slot="s",
        )

    assert "sk-ant-api03" not in captured["payload"]["arguments"]["response_text"]
    assert "[REDACTED:anthropic_key]" in captured["payload"]["arguments"]["response_text"]


def test_response_text_truncated(monkeypatch, tmp_path):
    """Response text longer than 512 chars is truncated."""
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(tmp_path / "cl.log"))
    captured: dict = {}

    def fake_post(url, payload, timeout=5.0):
        captured["payload"] = payload
        return True, 10, None

    with patch("checkin._post_to_governance", side_effect=fake_post):
        checkin.submit_checkin(
            event="turn_stop",
            response_text="x" * 2000,
            complexity=0.3,
            confidence=0.7,
            client_session_id="agent-x",
            continuity_token="v1.t",
            slot="s",
        )

    assert len(captured["payload"]["arguments"]["response_text"]) == 512


def test_post_failure_logged_as_fail(monkeypatch, tmp_path):
    """POST timeouts / errors are logged and returned as 'fail'."""
    log_path = tmp_path / "cl.log"
    monkeypatch.setenv("UNITARES_CHECKIN_LOG", str(log_path))

    with patch("checkin._post_to_governance", return_value=(False, 5000, "timeout")):
        result = checkin.submit_checkin(
            event="turn_stop",
            response_text="x",
            complexity=0.3,
            confidence=0.7,
            client_session_id="agent-x",
            continuity_token="v1.t",
            slot="s",
        )

    assert result == "fail"
    line = log_path.read_text().strip()
    assert "status=fail" in line
    assert 'err="timeout"' in line
```

- [ ] **Step 2: Run tests to verify they pass**

The `submit_checkin` implementation already supports these contracts.

```bash
python3 -m pytest tests/test_checkin_helper.py -v
```

Expected: 6 passed (the 4 new + the 2 kill-switch tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_checkin_helper.py
git commit -m "test(checkin): payload shape, redaction, truncation, failure logging"
```

---

### Task 4: Post-onboard check-in in session-start hook

**Files:**
- Modify: `hooks/session-start`
- Create: `tests/test_session_start_checkin.py`

- [ ] **Step 1: Write the contract test**

Create `tests/test_session_start_checkin.py`:

```python
"""Contract test: session-start hook fires a post-onboard check-in.

The test runs the hook with a mock governance server and asserts that
exactly one process_agent_update with event='session_start' is received
after the onboard call.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import threading
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent


class RecordingHandler(http.server.BaseHTTPRequestHandler):
    calls: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body.decode(errors="replace")}
        RecordingHandler.calls.append(data)
        # Canned onboard / checkin response
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "result": {
                "success": True,
                "uuid": "test-uuid-12345",
                "agent_id": "test_agent",
                "client_session_id": "agent-test1234",
                "continuity_token": "v1.fake",
                "display_name": "TestAgent",
            }
        }
        self.wfile.write(json.dumps(resp).encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"alive"}')

    def log_message(self, *a, **k):
        pass


def test_session_start_emits_post_onboard_checkin(tmp_path, monkeypatch):
    """session-start hook posts a check-in with event='session_start' after onboard."""
    RecordingHandler.calls = []
    port = 18769
    srv = socketserver.TCPServer(("127.0.0.1", port), RecordingHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
        }
        hook = PLUGIN_ROOT / "hooks" / "session-start"
        subprocess.run([str(hook)], env=env, timeout=15, check=False)
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    events = [c["arguments"].get("metadata", {}).get("event")
              for c in RecordingHandler.calls
              if c.get("name") == "process_agent_update"]
    assert "session_start" in events, (
        f"no session_start check-in seen; received tools: "
        f"{[c.get('name') for c in RecordingHandler.calls]}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/cirwel/projects/unitares-governance-plugin
python3 -m pytest tests/test_session_start_checkin.py -v
```

Expected: FAIL — the session-start hook currently does not emit a post-onboard check-in.

- [ ] **Step 3: Add post-onboard check-in to `hooks/session-start`**

Find the last successful `call_tool` onboard response block in `hooks/session-start` (search for `onboard` + `client_session_id` handling). After the block that saves the session cache, add a call to `checkin.py`:

Append (near end of hook, after session_cache.py has persisted the response):

```bash
# Post-onboard check-in: anchor EISV baseline for this session.
# Fire-and-forget: never fail the hook if this fails.
if [[ -n "${CLIENT_SESSION_ID:-}" ]]; then
  WORKSPACE_BASENAME=$(basename "${PWD}")
  BRANCH=$(git -C "${PWD}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
  SUMMARY="Session initialized for ${WORKSPACE_BASENAME} on branch ${BRANCH}"
  python3 "${PLUGIN_ROOT}/scripts/checkin.py" \
    --event session_start \
    --response-text "${SUMMARY}" \
    --complexity 0.1 \
    --confidence 0.9 \
    --client-session-id "${CLIENT_SESSION_ID}" \
    --continuity-token "${CONTINUITY_TOKEN:-}" \
    --uuid "${AGENT_UUID:-}" \
    --slot "${SLOT:-default}" \
    >/dev/null 2>&1 &
fi
```

The variables `CLIENT_SESSION_ID`, `CONTINUITY_TOKEN`, `AGENT_UUID`, and `SLOT` come from the onboard response — confirm they are set earlier in the hook. If not, extract from the session cache JSON after writing it; the shell block above should be adapted to read them from the cache file.

- [ ] **Step 4: Add CLI entry point to `scripts/checkin.py`**

Append to end of `scripts/checkin.py`:

```python
def _cli() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event", required=True)
    p.add_argument("--response-text", required=True)
    p.add_argument("--complexity", type=float, required=True)
    p.add_argument("--confidence", type=float, required=True)
    p.add_argument("--client-session-id", required=True)
    p.add_argument("--continuity-token", default="")
    p.add_argument("--slot", required=True)
    p.add_argument("--uuid", default="")
    p.add_argument("--server-url", default=None)
    p.add_argument("--plugin-version", default="0.3.0")
    args = p.parse_args()

    status = submit_checkin(
        event=args.event,
        response_text=args.response_text,
        complexity=args.complexity,
        confidence=args.confidence,
        client_session_id=args.client_session_id,
        continuity_token=args.continuity_token,
        slot=args.slot,
        uuid=args.uuid,
        server_url=args.server_url,
        plugin_version=args.plugin_version,
    )
    # Exit 0 for sent / skipped; non-zero only for true logic errors.
    return 0 if status in ("sent", "skip_kill_switch") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_session_start_checkin.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add hooks/session-start scripts/checkin.py tests/test_session_start_checkin.py
git commit -m "feat(hooks): post-onboard check-in in session-start"
```

---

### Task 5: Stop hook + hooks.json registration

**Files:**
- Create: `hooks/post-stop`
- Modify: `hooks/hooks.json`
- Create: `tests/test_post_stop_hook.py`

- [ ] **Step 1: Write the contract test**

Create `tests/test_post_stop_hook.py`:

```python
"""Contract test: Stop hook fires exactly one turn_stop check-in."""

from __future__ import annotations

import json
import socketserver
import subprocess
import threading
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent

# Reuse the same RecordingHandler module pattern as test_session_start_checkin.py
from test_session_start_checkin import RecordingHandler  # noqa: E402


def test_post_stop_emits_turn_stop_checkin(tmp_path, monkeypatch):
    """post-stop hook posts a check-in with event='turn_stop'."""
    RecordingHandler.calls = []
    port = 18770
    srv = socketserver.TCPServer(("127.0.0.1", port), RecordingHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    # Pre-populate session cache with a fake session file
    session_dir = tmp_path / ".unitares"
    session_dir.mkdir()
    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps({
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-test1234",
        "continuity_token": "v1.faketoken",
        "slot": "test-slot",
    }))

    # Claude Code feeds Stop hook a JSON payload on stdin;
    # minimal shape the hook reads:
    stop_payload = json.dumps({
        "hook_event_name": "Stop",
        "tool_calls": [
            {"name": "Read"}, {"name": "Edit"}, {"name": "Bash"}
        ],
        "final_text": "Completed the refactor; all tests pass.",
    })

    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "checkins.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
        }
        hook = PLUGIN_ROOT / "hooks" / "post-stop"
        subprocess.run(
            [str(hook)],
            env=env,
            input=stop_payload,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    checkins = [
        c for c in RecordingHandler.calls
        if c.get("name") == "process_agent_update"
        and c["arguments"].get("metadata", {}).get("event") == "turn_stop"
    ]
    assert len(checkins) == 1, (
        f"expected exactly 1 turn_stop check-in; got {len(checkins)}"
    )
    text = checkins[0]["arguments"]["response_text"]
    assert "3 tool call" in text
    assert "Completed the refactor" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_post_stop_hook.py -v
```

Expected: FAIL — `hooks/post-stop` does not exist yet.

- [ ] **Step 3: Create `hooks/post-stop`**

```bash
#!/usr/bin/env bash
# UNITARES Governance Plugin — Stop hook
#
# Fires once per Claude turn (when Claude stops emitting actions).
# Reads the Stop hook JSON payload on stdin, builds a turn summary,
# submits a process_agent_update via scripts/checkin.py, exits fast.
#
# Runs async — must never block or produce output on failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Read stdin (hook payload). Ignore errors if empty.
PAYLOAD=$(cat 2>/dev/null || echo "{}")
[[ -z "${PAYLOAD}" ]] && PAYLOAD="{}"

# Resolve session cache to get UUID/token/session_id
SESSION_FILE="${PWD}/.unitares/session.json"
[[ ! -f "${SESSION_FILE}" ]] && SESSION_FILE="${HOME}/.unitares/session.json"
[[ ! -f "${SESSION_FILE}" ]] && exit 0

UUID=$(python3 -c "import json,sys; print(json.load(open('${SESSION_FILE}')).get('uuid',''))" 2>/dev/null || echo "")
CSID=$(python3 -c "import json,sys; print(json.load(open('${SESSION_FILE}')).get('client_session_id',''))" 2>/dev/null || echo "")
TOK=$(python3 -c "import json,sys; print(json.load(open('${SESSION_FILE}')).get('continuity_token',''))" 2>/dev/null || echo "")
SLOT=$(python3 -c "import json,sys; print(json.load(open('${SESSION_FILE}')).get('slot','default'))" 2>/dev/null || echo "default")

[[ -z "${CSID}" ]] && exit 0

# Build summary from payload
SUMMARY=$(python3 - <<PY
import json, sys
try:
    p = json.loads("""${PAYLOAD}""")
except Exception:
    p = {}
tools = p.get("tool_calls", []) or []
names = [t.get("name") for t in tools if t.get("name")]
top3 = ", ".join(names[:3]) if names else "no tools"
text = (p.get("final_text") or "").strip().replace("\n", " ")
summary = f"Turn summary: {len(tools)} tool calls ({top3}); response excerpt: {text[:120]}"
print(summary)
PY
)

# Complexity: tool count / 10, capped at 0.85
COMPLEXITY=$(python3 - <<PY
import json
try:
    p = json.loads("""${PAYLOAD}""")
except Exception:
    p = {}
n = len(p.get("tool_calls", []) or [])
print(f"{min(n/10.0, 0.85):.3f}")
PY
)

python3 "${PLUGIN_ROOT}/scripts/checkin.py" \
  --event turn_stop \
  --response-text "${SUMMARY}" \
  --complexity "${COMPLEXITY}" \
  --confidence 0.7 \
  --client-session-id "${CSID}" \
  --continuity-token "${TOK}" \
  --uuid "${UUID}" \
  --slot "${SLOT}" \
  >/dev/null 2>&1 &

exit 0
```

Mark executable:

```bash
chmod +x hooks/post-stop
```

- [ ] **Step 4: Register in `hooks/hooks.json`**

Replace the existing `hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' session-start", "async": false}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-stop", "async": true}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-edit", "async": true}
        ]
      },
      {
        "matcher": "mcp__.*__process_agent_update",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-checkin", "async": true}
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_post_stop_hook.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add hooks/post-stop hooks/hooks.json tests/test_post_stop_hook.py
git commit -m "feat(hooks): Stop -> per-turn check-in"
```

---

### Task 6: SessionEnd hook

**Files:**
- Create: `hooks/session-end`
- Modify: `hooks/hooks.json`
- Create: `tests/test_session_end_hook.py`

- [ ] **Step 1: Write the contract test**

Create `tests/test_session_end_hook.py`:

```python
"""Contract test: SessionEnd hook emits a session_end check-in."""

from __future__ import annotations

import json
import socketserver
import subprocess
import threading
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
from test_session_start_checkin import RecordingHandler  # noqa: E402


def test_session_end_emits_checkin(tmp_path):
    RecordingHandler.calls = []
    port = 18771
    srv = socketserver.TCPServer(("127.0.0.1", port), RecordingHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    session_dir = tmp_path / ".unitares"
    session_dir.mkdir()
    (session_dir / "session.json").write_text(json.dumps({
        "uuid": "86ae619f-87e0-4040-8f29-eacece0c7904",
        "client_session_id": "agent-test1234",
        "continuity_token": "v1.tok",
        "slot": "test-slot",
    }))

    try:
        env = {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "UNITARES_SERVER_URL": f"http://127.0.0.1:{port}",
            "UNITARES_CHECKIN_LOG": str(tmp_path / "cl.log"),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PWD": str(tmp_path),
        }
        hook = PLUGIN_ROOT / "hooks" / "session-end"
        subprocess.run([str(hook)], env=env, timeout=15, check=False)
    finally:
        srv.shutdown()
        thread.join(timeout=2)

    events = [c["arguments"]["metadata"]["event"]
              for c in RecordingHandler.calls
              if c.get("name") == "process_agent_update"]
    assert "session_end" in events
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_session_end_hook.py -v
```

Expected: FAIL — `hooks/session-end` does not exist.

- [ ] **Step 3: Create `hooks/session-end`**

```bash
#!/usr/bin/env bash
# UNITARES Governance Plugin — SessionEnd hook
#
# Fires when the Claude Code session terminates (window close, etc).
# Posts a final session_end check-in. Best-effort: session may be
# closing abruptly, so this must be fast and cannot block.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SESSION_FILE="${PWD}/.unitares/session.json"
[[ ! -f "${SESSION_FILE}" ]] && SESSION_FILE="${HOME}/.unitares/session.json"
[[ ! -f "${SESSION_FILE}" ]] && exit 0

UUID=$(python3 -c "import json; print(json.load(open('${SESSION_FILE}')).get('uuid',''))" 2>/dev/null || echo "")
CSID=$(python3 -c "import json; print(json.load(open('${SESSION_FILE}')).get('client_session_id',''))" 2>/dev/null || echo "")
TOK=$(python3 -c "import json; print(json.load(open('${SESSION_FILE}')).get('continuity_token',''))" 2>/dev/null || echo "")
SLOT=$(python3 -c "import json; print(json.load(open('${SESSION_FILE}')).get('slot','default'))" 2>/dev/null || echo "default")

[[ -z "${CSID}" ]] && exit 0

# Tally check-ins posted this session from the log (best effort).
LOG="${UNITARES_CHECKIN_LOG:-${HOME}/.unitares/checkins.log}"
COUNT=0
if [[ -f "${LOG}" ]]; then
  COUNT=$(grep -c "slot=${SLOT}" "${LOG}" 2>/dev/null || echo "0")
fi

SUMMARY="Session ended: ${COUNT} check-ins posted this session"

python3 "${PLUGIN_ROOT}/scripts/checkin.py" \
  --event session_end \
  --response-text "${SUMMARY}" \
  --complexity 0.1 \
  --confidence 0.9 \
  --client-session-id "${CSID}" \
  --continuity-token "${TOK}" \
  --uuid "${UUID}" \
  --slot "${SLOT}" \
  >/dev/null 2>&1

exit 0
```

Note: SessionEnd is NOT async — we want to block briefly so the check-in actually lands before the process exits. The 5-second POST timeout in `checkin.py` bounds this.

Mark executable:

```bash
chmod +x hooks/session-end
```

- [ ] **Step 4: Register in `hooks/hooks.json`**

Insert a `SessionEnd` entry alongside `SessionStart`:

```json
"SessionEnd": [
  {
    "matcher": "*",
    "hooks": [
      {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' session-end", "async": false}
    ]
  }
],
```

The full `hooks/hooks.json` becomes:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' session-start", "async": false}
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' session-end", "async": false}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-stop", "async": true}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-edit", "async": true}
        ]
      },
      {
        "matcher": "mcp__.*__process_agent_update",
        "hooks": [
          {"type": "command", "command": "'${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd' post-checkin", "async": true}
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/test_session_end_hook.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add hooks/session-end hooks/hooks.json tests/test_session_end_hook.py
git commit -m "feat(hooks): SessionEnd -> final check-in"
```

---

### Task 7: Refactor post-edit to use shared helper

**Files:**
- Modify: `hooks/post-edit`

Why: The existing `post-edit` hook builds its own payload and POSTs inline. Migrating it to call `checkin.py` reduces drift and gives the edit-threshold check-in the same redaction, logging, and kill-switch treatment as the new hooks. Behavior is unchanged — the DECISION logic in `auto_checkin_decision.py` still gates firing; only the transport swaps.

- [ ] **Step 1: Add a regression test that pins current behavior**

Append to `tests/test_post_checkin_hook.py` (or a new file `tests/test_post_edit_refactor.py` if cleaner):

```python
def test_post_edit_routes_through_checkin_py(tmp_path, monkeypatch):
    """Threshold-triggered auto-checkin posts via scripts/checkin.py,
    producing a 'plugin_hook' + event='auto_edit' metadata payload."""
    # Setup: mock governance server on port 18772
    # Setup: session cache populated, milestone accumulator past threshold
    # Invoke: hooks/post-edit with a synthetic Edit tool payload
    # Assert: exactly one process_agent_update with metadata.source == "plugin_hook"
    #         and metadata.event == "auto_edit"
    # (implementation left to task executor — follow pattern from
    # test_post_stop_hook.py with pre-populated milestone file)
    ...
```

Run to confirm it fails (the current post-edit does not stamp `metadata.source`).

- [ ] **Step 2: Update `hooks/post-edit` to call `checkin.py`**

Find the section in `hooks/post-edit` that constructs the JSON body and calls `curl` or the inline Python POST. Replace that block with a call to `checkin.py`, passing values produced by `auto_checkin_decision.decide()`:

```bash
# After auto_checkin_decision.decide() returns a DECISION json,
# extract fields and delegate to the shared helper.
if [[ "${FIRE}" == "true" ]]; then
  RESPONSE_TEXT=$(echo "${DECISION}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('response_text',''))")
  COMPLEXITY=$(echo "${DECISION}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('complexity',0.3))")

  python3 "${PLUGIN_ROOT}/scripts/checkin.py" \
    --event auto_edit \
    --response-text "${RESPONSE_TEXT}" \
    --complexity "${COMPLEXITY}" \
    --confidence 0.6 \
    --client-session-id "${CSID}" \
    --continuity-token "${TOK}" \
    --uuid "${UUID}" \
    --slot "${SLOT}" \
    >/dev/null 2>&1 &
fi
```

Preserve the accumulator-reset logic that runs after firing.

- [ ] **Step 3: Run all hook tests**

```bash
python3 -m pytest tests/test_post_checkin_hook.py tests/test_post_edit_refactor.py tests/test_auto_checkin_decision.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add hooks/post-edit tests/
git commit -m "refactor(hooks): post-edit routes through checkin.py"
```

---

### Task 8: Config defaults and documentation

**Files:**
- Modify: `config/defaults.env`
- Modify: `README.md`

- [ ] **Step 1: Update `config/defaults.env`**

```
# UNITARES Governance Plugin — Default Configuration
UNITARES_SERVER_URL=http://localhost:8767
UNITARES_AGENT_PREFIX=claude

# Check-in emission (Phase-1 additions)
UNITARES_CHECKINS=on                   # set to 'off' to suppress every plugin-emitted check-in
UNITARES_CHECKIN_LOG=~/.unitares/checkins.log

# Existing edit-threshold auto-checkin (unchanged)
UNITARES_AUTO_CHECKIN_ENABLED=1
UNITARES_AUTO_CHECKIN_EDITS=5
UNITARES_AUTO_CHECKIN_SECS=600
```

- [ ] **Step 2: Add a README section**

Append to `README.md`:

```markdown
## Check-In Triggers

The plugin emits `process_agent_update` calls at four trigger points:

| Trigger | Hook | Frequency | Payload `metadata.event` |
|---|---|---|---|
| Session starts | `session-start` | once per session | `session_start` |
| Claude turn ends | `post-stop` | per turn | `turn_stop` |
| Edit-threshold crossed | `post-edit` | every N edits | `auto_edit` |
| Session closes | `session-end` | once per session | `session_end` |

All emissions are gated by `UNITARES_CHECKINS=off` (kill switch) and logged to
`~/.unitares/checkins.log` for diagnosis. Secret-looking strings in payloads
are redacted before POSTing.

Disable any single trigger by removing its entry from `hooks/hooks.json`.
```

- [ ] **Step 3: Commit**

```bash
git add config/defaults.env README.md
git commit -m "docs: plugin check-in triggers + kill switch + config"
```

---

### Task 9: Integration smoke test against live governance

**Files:** none (operational verification)

- [ ] **Step 1: Install plugin locally**

From Claude Code's perspective, the easiest refresh is to restart Claude Code with a plugin-cache reset. Manual option:

```bash
rm -rf ~/.claude/plugins/cache/unitares-governance-plugin/unitares-governance/0.3.0/
```

On next Claude Code launch, the cache repopulates from the source. (Exact mechanism depends on how the plugin is published/registered; validate that 0.3.0 actually lands in cache after restart.)

- [ ] **Step 2: Launch a fresh Claude Code session and watch the log**

```bash
tail -f ~/.unitares/checkins.log
```

Start a new Claude Code window. Within ~2 seconds you should see:

```
2026-04-17T... | slot=<slot> | event=session_start | uuid=... | status=sent | latency_ms=...
```

Ask Claude to do a trivial task (e.g. "what's in this directory?"). After the turn:

```
2026-04-17T... | slot=<slot> | event=turn_stop | uuid=... | status=sent | latency_ms=...
```

Close the window. SessionEnd should fire:

```
2026-04-17T... | slot=<slot> | event=session_end | uuid=... | status=sent | latency_ms=...
```

- [ ] **Step 3: Verify check-ins land in governance**

```bash
psql -h localhost -U postgres -d governance -t -c "
SELECT to_char(ts, 'HH24:MI:SS') AS t,
       agent_id,
       payload->'arguments'->'metadata'->>'event' AS event,
       payload->'arguments'->>'response_text' AS summary
FROM audit.tool_usage
WHERE tool_name = 'process_agent_update'
  AND payload->'arguments'->'metadata'->>'source' = 'plugin_hook'
  AND ts > NOW() - INTERVAL '10 minutes'
ORDER BY ts DESC;
"
```

Expected: rows showing the three events from your smoke test.

- [ ] **Step 4: Verify EISV is moving**

Call `get_governance_metrics` for the agent UUID from the smoke test. The `behavioral_eisv.warmup.updates_completed` counter should reflect the check-ins you just fired (1 + N-turns + 1).

- [ ] **Step 5: Commit the rollout marker**

```bash
git commit --allow-empty -m "chore: rollout marker for check-in triggers verification"
git push origin HEAD
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task(s) |
|---|---|
| SessionStart post-onboard check-in | Task 4 |
| Stop per-turn check-in | Task 5 |
| SessionEnd close check-in | Task 6 |
| Kill switch (UNITARES_CHECKINS=off) | Tasks 2, 8 |
| Secret redaction | Tasks 1, 3 |
| Local logging for diagnosis | Tasks 2, 9 |
| Payload schema documented | Top of plan + Task 3 tests |
| Existing auto-checkin preserved | Task 7 |
| Plugin deployed (cache refresh) | Task 0 |

### Not yet covered (documented as Future Work)

- `SubagentStop` handling — scope deferred, needs separate UUID ownership decision.
- `StopFailure` check-ins — differentiates API errors from clean turns.
- `PreCompact` / `PostCompact` — trajectory preservation across compaction.
- `TaskCreated` / `TaskCompleted` — work-unit-aligned check-ins.
- Dedup / rate-limit — Stop may fire unexpectedly twice; current design is idempotent-ish but not explicit about it.
- Verbosity knob (`UNITARES_CHECKIN_MODE=minimal|standard|verbose`) — payload fidelity tuning.
- Dashboard tile for "check-ins per slot last hour" — relies on `audit.tool_usage.payload->metadata` queries.

---

## Future Work (Phase 2)

**SubagentStop:** when Claude's Task tool spawns a subagent, `SubagentStop` fires when the subagent chain completes. Design decision: does the subagent onboard separately (own UUID) or roll up as parent? Recommendation: separate UUID with `parent_agent_id` set, so the subagent's work produces its own EISV trajectory but lineage is preserved. Requires plumbing `parent_agent_id` through the subagent's onboard call — a hook in Claude Code isn't obvious; may need a manual step inside subagents for now.

**StopFailure:** same shape as Stop but `event=turn_failed`, `response_text` includes the error class. Complexity 0.2, confidence 0.9 — we're confident something went wrong. Useful signal for risk scoring.

**PreCompact / PostCompact:** PreCompact fires before context compression; capture the pre-compaction trajectory. PostCompact confirms identity survived. These are rare events but high-value for debugging continuity regressions.

**Verbosity knob:** replace the fixed `RESPONSE_TEXT_MAX = 512` with per-mode limits and per-mode content inclusion rules. `minimal` = event marker + timestamp only, ~50 chars. `verbose` = full turn transcript up to 4096 chars.

**Dedup:** track `(slot, event, window-start-second)` in Redis with a 2-second TTL; skip if already fired. Prevents accidental double-fire on Stop edge cases.
