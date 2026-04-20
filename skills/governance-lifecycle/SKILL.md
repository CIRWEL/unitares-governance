---
name: governance-lifecycle
description: >
  Use when an agent is interacting with UNITARES governance for the first time, needs to
  onboard, check in, or recover from a pause/reject verdict. Covers the full agent lifecycle
  from session start through check-ins to recovery.
last_verified: "2026-04-17"
freshness_days: 14
source_files:
  - unitares/src/mcp_handlers/core.py
  - unitares/src/mcp_handlers/identity/handlers.py
  - unitares/src/mcp_handlers/admin/handlers.py
---

# Agent Lifecycle

## Starting a Session

Call `onboard()` to register a fresh identity, or `identity(agent_uuid=..., resume=true)` to resume a stored one:

```
onboard(name, model_type)                        # always creates a fresh UUID
identity(agent_uuid="<saved-uuid>", resume=true) # resume an existing identity
```

Returns:
- **UUID**: Your persistent identity — save this to resume later
- **client_session_id**: Echo this back in subsequent calls for session continuity within the same process
- **continuity metadata**: Newer runtimes may also return `continuity_token_supported` and session-resolution diagnostics

If the runtime supports a continuity token, prefer it. Otherwise always echo `client_session_id`.

### Resuming vs. creating new (updated 2026-04-17)

`name=` is a **cosmetic label**, not a resume key. Since the 2026-04-17 name-claim removal, passing `name="Same-Agent"` on a fresh session always mints a new UUID — it will not re-bind to an existing agent with that label. Resume signals, in strength order:

1. **`continuity_token`** (PATH 2.8) — strongest. Signed and self-contained; carries the UUID claim and proves possession in one value. Save this from your first `onboard()` response and pass it on every subsequent `identity()` or `onboard()` call. Expires; rebinds even across session-cache invalidation.
2. **`agent_uuid` + `continuity_token`** (PATH 0 with ownership proof) — strong. Pass them together; the server's Part C gate verifies the token's `aid` claim equals the requested `agent_uuid`. Without the matching token, this resume currently logs `[IDENTITY_STRICT]` and emits a `identity_hijack_suspected` broadcast event, and will be rejected outright once `UNITARES_IDENTITY_STRICT=strict` is promoted to default.
3. **Active session binding** (PATH 1/2) — auto-handled by the server when you reuse the same transport session.

**Do not** call `identity(agent_uuid=X, resume=true)` with a UUID you learned from somewhere else (a hook listing, another agent's check-in, a log line). That is the canonical hijack pattern: an unsigned UUID claim with no proof of ownership. The server treats every such call as suspect — see KG bug `2026-04-20T00:09:51`.

Without any of the signals above, you are a new agent. That is the correct semantic, not a bug.

## Check-ins

Call `process_agent_update()` after meaningful work:

```
process_agent_update(
  response_text: "Brief summary of what you did",
  complexity: 0.0-1.0,   # Task difficulty estimate
  confidence: 0.0-1.0    # How confident you are (be honest)
)
```

### When to Check In

- After completing a meaningful unit of work
- Before and after high-complexity tasks
- When you feel uncertain or notice drift
- **Not** after every single tool call — use judgment

### What You Get Back

A verdict plus current EISV metrics. Read the verdict and act on it.

## Reading Verdicts

| Verdict | What to Do |
|---------|-----------|
| **proceed** | Continue normally |
| **guide** + guidance text | Read the guidance, adjust your approach, keep going |
| **pause** | Stop your current task. Reflect on what is flagged. Consider requesting a dialectic review |
| **reject** | Significant concern. Requires dialectic review or human intervention |
| **margin: tight** | You are near a basin edge. Be more careful with next steps |

A `guide` verdict is an early warning. Ignoring it makes `pause` more likely.

## Identity

- Your identity persists across sessions via UUID
- Session binding can happen via transport session, `client_session_id`, or continuity token
- Use `identity()` when continuity seems unclear
- Inspect:
  - `identity_status`
  - `bound_identity`
  - `session_resolution_source`
  - `continuity_token_supported`

Strong continuity is better than implicit continuity. If the runtime falls back to weak signals such as fingerprinting, re-onboard and resume with explicit continuity data.

## Recovery

When you are paused, stuck, or need intervention:

| Situation | Tool | Notes |
|-----------|------|-------|
| Stuck or paused, want automatic recovery | `self_recovery()` | Attempts to restore healthy state |
| Disagree with verdict, want structured review | `request_dialectic_review()` | Starts thesis/antithesis/synthesis process |
| Manual override needed | `operator_resume_agent()` | Requires human/operator action |

Recovery is not a shortcut — `self_recovery()` examines your EISV state and determines if resumption is safe. If your metrics are genuinely degraded, it will not force a resume.

## MCP Tools Reference

### Essential (use in every session)

- `onboard()` — Register or reconnect identity
- `process_agent_update()` — Check in with work summary, complexity, confidence
- `get_governance_metrics()` — Read your current EISV state
- `identity()` — Confirm who the runtime thinks you are and how continuity was resolved
- `health_check()` — Check operator-facing server health when behavior seems odd
- `search_knowledge_graph()` — Find existing knowledge before creating new entries
- `leave_note()` — Quick contribution to the knowledge graph

### Common (use when needed)

- `knowledge()` — Full knowledge graph CRUD (store, update, details, cleanup)
- `agent()` — Agent lifecycle (list, archive, get details)
- `calibration()` — Check or update calibration data
- `request_dialectic_review()` — Start a dialectic session
- `export()` — Export session history

### Specialized

- `call_model()` — Delegate to a secondary LLM for analysis
- `detect_stuck_agents()` — Find unresponsive agents
- `self_recovery()` — Resume from stuck or paused state
- `submit_thesis()` / `submit_antithesis()` / `submit_synthesis()` — Dialectic participation
