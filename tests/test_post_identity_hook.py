"""Contract tests for the post-identity PostToolUse hook.

The hook fires after `mcp__<server>__(onboard|identity|bind_session)` tool
calls and writes the response's identity fields to the slot-scoped session
cache. This lets the agent's own first MCP call become the source of truth
for session identity — Part C of the identity honesty series.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "post-identity"


def _run_hook(hook_input: dict, workspace: Path):
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps(hook_input),
        text=True,
        capture_output=True,
        timeout=10,
        cwd=str(workspace),
    )


def _read_session_cache(workspace: Path, slot: str | None = None) -> dict:
    """Read the slotted session cache directly."""
    filename = "session.json"
    if slot:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slot)[:64]
        filename = f"session-{safe}.json"
    path = workspace / ".unitares" / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _mcp_response(uuid="u-123", agent_id="Test_Agent", sid="agent-abc",
                  token="v1.tok", display_name="TestAgent"):
    """Build a realistic MCP tool response envelope."""
    inner = {
        "success": True,
        "uuid": uuid,
        "agent_id": agent_id,
        "client_session_id": sid,
        "continuity_token": token,
        "display_name": display_name,
        "continuity_token_supported": True,
    }
    return {"content": [{"type": "text", "text": json.dumps(inner)}]}


class TestPostIdentityRecordsResponse:
    def test_onboard_response_writes_slotted_cache(self, tmp_path):
        slot = "session-xyz-1234"
        hook_input = {
            "session_id": slot,
            "tool_name": "mcp__unitares-governance__onboard",
            "tool_input": {"name": "my-agent"},
            "tool_response": _mcp_response(uuid="u-onboard-1"),
        }
        result = _run_hook(hook_input, tmp_path)
        assert result.returncode == 0

        cache = _read_session_cache(tmp_path, slot)
        assert cache["uuid"] == "u-onboard-1"
        assert cache["agent_id"] == "Test_Agent"
        assert cache["client_session_id"] == "agent-abc"
        assert cache["continuity_token"] == "v1.tok"
        assert "updated_at" in cache, "should stamp updated_at"

    def test_identity_response_writes_slotted_cache(self, tmp_path):
        hook_input = {
            "session_id": "slot-id",
            "tool_name": "mcp__unitares-governance__identity",
            "tool_input": {"agent_uuid": "u-resume-1", "resume": True},
            "tool_response": _mcp_response(uuid="u-resume-1"),
        }
        result = _run_hook(hook_input, tmp_path)
        assert result.returncode == 0
        assert _read_session_cache(tmp_path, "slot-id")["uuid"] == "u-resume-1"

    def test_bind_session_response_writes_slotted_cache(self, tmp_path):
        hook_input = {
            "session_id": "slot-bind",
            "tool_name": "mcp__unitares-governance__bind_session",
            "tool_input": {"agent_uuid": "u-bind-1", "resume": True},
            "tool_response": _mcp_response(uuid="u-bind-1"),
        }
        result = _run_hook(hook_input, tmp_path)
        assert result.returncode == 0
        assert _read_session_cache(tmp_path, "slot-bind")["uuid"] == "u-bind-1"


class TestPostIdentityIgnoresOtherTools:
    def test_ignores_process_agent_update(self, tmp_path):
        """process_agent_update has its own hook — post-identity must skip."""
        hook_input = {
            "session_id": "s1",
            "tool_name": "mcp__unitares-governance__process_agent_update",
            "tool_input": {"response_text": "..."},
            "tool_response": _mcp_response(uuid="u-checkin"),
        }
        _run_hook(hook_input, tmp_path)
        assert _read_session_cache(tmp_path, "s1") == {}, "no cache should be written"

    def test_ignores_get_governance_metrics(self, tmp_path):
        hook_input = {
            "session_id": "s1",
            "tool_name": "mcp__unitares-governance__get_governance_metrics",
            "tool_input": {},
            "tool_response": _mcp_response(),
        }
        _run_hook(hook_input, tmp_path)
        assert _read_session_cache(tmp_path, "s1") == {}


class TestPostIdentityResilience:
    def test_no_stdin_exits_cleanly(self, tmp_path):
        """Running with no stdin must not error."""
        result = subprocess.run(
            [str(HOOK)],
            input="",
            text=True,
            capture_output=True,
            timeout=5,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_malformed_json_exits_cleanly(self, tmp_path):
        result = subprocess.run(
            [str(HOOK)],
            input="not valid json{{{",
            text=True,
            capture_output=True,
            timeout=5,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert _read_session_cache(tmp_path) == {}

    def test_response_without_uuid_skips_write(self, tmp_path):
        """A failed onboard response (no uuid) must not write cache."""
        failed_response = {
            "content": [{"type": "text", "text": json.dumps({
                "success": False,
                "error": "trajectory_required",
            })}]
        }
        hook_input = {
            "session_id": "s1",
            "tool_name": "mcp__unitares-governance__onboard",
            "tool_input": {"name": "x"},
            "tool_response": failed_response,
        }
        _run_hook(hook_input, tmp_path)
        assert _read_session_cache(tmp_path, "s1") == {}

    def test_bound_identity_uuid_recovered_on_resume(self, tmp_path):
        """identity(resume=true) may return bound_identity dict instead of top-level uuid."""
        inner = {
            "success": True,
            "resumed": True,
            "bound_identity": {
                "uuid": "u-bound-1",
                "agent_id": "ResumedAgent",
                "display_name": "Resumed",
            },
            "continuity_token": "v1.recovered",
        }
        response = {"content": [{"type": "text", "text": json.dumps(inner)}]}
        hook_input = {
            "session_id": "s-bound",
            "tool_name": "mcp__unitares-governance__identity",
            "tool_input": {"agent_uuid": "u-bound-1"},
            "tool_response": response,
        }
        _run_hook(hook_input, tmp_path)
        cache = _read_session_cache(tmp_path, "s-bound")
        assert cache["uuid"] == "u-bound-1"
        assert cache["agent_id"] == "ResumedAgent"
