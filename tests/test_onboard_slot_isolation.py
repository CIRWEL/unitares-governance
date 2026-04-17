"""Tests that two slots in the same workspace get distinct identities.

The regression fixed here: commit ``29a3a77`` made the plugin's client cache
per-slot, but the plugin still sent the same ``name`` on onboard. The server
resolves identity by label in ``resolve_by_name_claim`` without session-key
scoping, so both slots got bound to the same existing agent.

The fix appends a short slot fingerprint to the agent name when a slot is
provided. These tests pin that behavior — both the client-side mechanics
(what the plugin sends) and, when the governance server is reachable, the
end-to-end promise that different slots yield different UUIDs.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from onboard_helper import (  # noqa: E402
    _scope_name_by_slot,
    run_onboard,
)


# ---- Unit tests on the scoping helper itself -------------------------------


def test_scope_name_noop_when_no_slot() -> None:
    assert _scope_name_by_slot("cirwel", None) == "cirwel"
    assert _scope_name_by_slot("cirwel", "") == "cirwel"


def test_scope_name_appends_slot_fingerprint() -> None:
    scoped = _scope_name_by_slot("cirwel", "1d118271-7384-42cb-adce-c4f4b314e089")
    assert scoped.startswith("cirwel#")
    # Fingerprint is an 8-hex-char hash of the full slot — enough entropy
    # to avoid collisions even when two slots share a prefix. Exact value
    # is pinned so we catch accidental changes to the hashing scheme.
    assert scoped == "cirwel#74608bf3"


def test_scope_name_is_collision_resistant_on_prefix_overlap() -> None:
    """Regression: slots with identical first-8 chars must still produce
    distinct fingerprints. Earlier iteration used slot[:8] and collapsed
    all slots sharing a prefix (e.g. CI runners stamping "runner-N-*")
    into the same label, which put us right back at the original bug."""
    a = _scope_name_by_slot("w", "itest-slot-aaaa1111")
    b = _scope_name_by_slot("w", "itest-slot-bbbb2222")
    assert a != b


def test_scope_name_stable_across_calls() -> None:
    a = _scope_name_by_slot("w", "50346241-6659")
    b = _scope_name_by_slot("w", "50346241-6659")
    assert a == b


def test_different_slots_produce_different_scoped_names() -> None:
    a = _scope_name_by_slot("w", "1d118271-aaa")
    b = _scope_name_by_slot("w", "50346241-bbb")
    assert a != b


# ---- Behavior tests on run_onboard with injected transport -----------------


class _FakeTransport:
    """Record every outbound request so tests can assert on what was sent."""

    def __init__(self, response: dict[str, Any]):
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, payload: dict, timeout: float, token: str | None) -> dict:
        self.calls.append({"url": url, "payload": payload, "token": token})
        return self._response


def _onboard_ok_response(uuid: str, display_name: str) -> dict:
    return {
        "result": {
            "success": True,
            "uuid": uuid,
            "agent_id": f"Claude_Code_{uuid[:8]}",
            "client_session_id": f"agent-{uuid[:12]}",
            "continuity_token": f"token-{uuid}",
            "session_resolution_source": "explicit_client_session_id_scoped",
            "continuity_token_supported": True,
            "display_name": display_name,
        }
    }


def test_unslotted_onboard_sends_bare_name(tmp_path: Path) -> None:
    """Codex / stdio flows must not have their agent names rewritten — only
    slotted callers need the scoping, and changing the name silently for
    single-process flows would be a surprise regression."""
    transport = _FakeTransport(_onboard_ok_response("aaaa1111-0000-0000-0000-000000000000", "cirwel"))

    result = run_onboard(
        server_url="http://unit-test",
        agent_name="cirwel",
        model_type="claude-code",
        workspace=tmp_path,
        slot=None,
        post_json=transport,
    )

    assert result["status"] == "ok"
    sent_name = transport.calls[0]["payload"]["arguments"]["name"]
    assert sent_name == "cirwel"


def test_slotted_onboard_sends_scoped_name(tmp_path: Path) -> None:
    transport = _FakeTransport(_onboard_ok_response("bbbb2222-0000-0000-0000-000000000000", "cirwel#74608bf3"))

    result = run_onboard(
        server_url="http://unit-test",
        agent_name="cirwel",
        model_type="claude-code",
        workspace=tmp_path,
        slot="1d118271-7384-42cb-adce-c4f4b314e089",
        post_json=transport,
    )

    assert result["status"] == "ok"
    sent_name = transport.calls[0]["payload"]["arguments"]["name"]
    assert sent_name == "cirwel#74608bf3"


def test_two_slots_receive_distinct_server_calls(tmp_path: Path) -> None:
    """Different slots → different names sent → server's name-claim can no
    longer bind both slots to the same label. This is the behavior that was
    broken before the fix: both slots were sending an identical ``name``."""
    response_a = _onboard_ok_response("1111aaaa-0000-0000-0000-000000000000", "cirwel#slot-aaa")
    transport_a = _FakeTransport(response_a)
    run_onboard(
        server_url="http://unit-test",
        agent_name="cirwel",
        model_type="claude-code",
        workspace=tmp_path,
        slot="slot-aaaaaaaa",
        post_json=transport_a,
    )

    response_b = _onboard_ok_response("2222bbbb-0000-0000-0000-000000000000", "cirwel#slot-bbb")
    transport_b = _FakeTransport(response_b)
    run_onboard(
        server_url="http://unit-test",
        agent_name="cirwel",
        model_type="claude-code",
        workspace=tmp_path,
        slot="slot-bbbbbbbb",
        post_json=transport_b,
    )

    name_a = transport_a.calls[0]["payload"]["arguments"]["name"]
    name_b = transport_b.calls[0]["payload"]["arguments"]["name"]
    assert name_a != name_b
    assert name_a.startswith("cirwel#")
    assert name_b.startswith("cirwel#")


def test_uuid_direct_resume_does_not_rescope_name(tmp_path: Path) -> None:
    """When the slot cache already has a UUID, the helper resumes via the
    ``identity()`` tool — no onboard, no name-claim, so the name never hits
    the wire. This test guards against a future edit that would insert
    name-scoping into the UUID-direct path (which would break resume)."""
    # Seed the slot cache with an existing UUID, as if a prior run onboarded.
    cache_dir = tmp_path / ".unitares"
    cache_dir.mkdir()
    (cache_dir / "session-existing.json").write_text(
        json.dumps({"uuid": "cccc3333-0000-0000-0000-000000000000"}),
        encoding="utf-8",
    )

    identity_response = {
        "result": {
            "success": True,
            "uuid": "cccc3333-0000-0000-0000-000000000000",
            "agent_id": "Claude_Code_cccc3333",
            "client_session_id": "agent-cccc3333-000",
            "continuity_token": "token-cccc3333",
            "session_resolution_source": "agent_uuid_direct",
            "continuity_token_supported": True,
            "display_name": "cirwel",
        }
    }
    transport = _FakeTransport(identity_response)

    result = run_onboard(
        server_url="http://unit-test",
        agent_name="cirwel",
        model_type="claude-code",
        workspace=tmp_path,
        slot="existing",
        post_json=transport,
    )

    assert result["status"] == "ok"
    assert result["uuid"] == "cccc3333-0000-0000-0000-000000000000"
    # Helper must have taken the identity() path — not onboard(). That path
    # passes agent_uuid, not name, so a "name" field should NOT appear.
    sent = transport.calls[0]["payload"]
    assert sent["name"] == "identity"
    assert sent["arguments"]["agent_uuid"] == "cccc3333-0000-0000-0000-000000000000"
    assert "name" not in sent["arguments"]


# ---- Integration: real server, real distinct UUIDs -------------------------


def _server_reachable() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8767/health", timeout=1)
        return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


@pytest.mark.skipif(not _server_reachable(), reason="governance server on :8767 unreachable")
def test_integration_two_slots_get_distinct_uuids(tmp_path: Path) -> None:
    """End-to-end: ask the real server to onboard two slots. Verify they
    actually resolve to different UUIDs. This is the regression test that
    would have caught the original bug before shipping."""
    slot_a = "itest-slot-aaaa1111"
    slot_b = "itest-slot-bbbb2222"
    ws_a = tmp_path / "ws-a"
    ws_b = tmp_path / "ws-b"
    ws_a.mkdir()
    ws_b.mkdir()

    result_a = run_onboard(
        server_url="http://127.0.0.1:8767",
        agent_name="itest-plugin",
        model_type="claude-code",
        workspace=ws_a,
        slot=slot_a,
    )
    result_b = run_onboard(
        server_url="http://127.0.0.1:8767",
        agent_name="itest-plugin",
        model_type="claude-code",
        workspace=ws_b,
        slot=slot_b,
    )

    assert result_a["status"] == "ok", result_a
    assert result_b["status"] == "ok", result_b
    assert result_a["uuid"] != result_b["uuid"], (
        f"slot isolation broken: both slots resolved to the same UUID {result_a['uuid']}"
    )
