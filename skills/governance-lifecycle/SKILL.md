---
name: governance-lifecycle
description: >
  Use when an agent is interacting with UNITARES governance for the first time, needs to
  onboard, check in, or recover from a pause/reject verdict. Covers the full agent lifecycle
  from session start through check-ins to recovery.
last_verified: "2026-04-25"
freshness_days: 14
source_files:
  - unitares/src/mcp_handlers/core.py
  - unitares/src/mcp_handlers/identity/handlers.py
  - unitares/src/mcp_handlers/admin/handlers.py
---

# Agent Lifecycle

## Starting a Session

Call `onboard()` to register a fresh identity:

```
onboard(name, model_type, force_new=true)        # create a fresh UUID
onboard(continuity_token="<saved-token>")        # resume via signed token
```

**`force_new=true` is load-bearing for fresh mint.** Without it, a bare `onboard()` on a shared host (multiple same-family agents, Claude Desktop stdio, CI runners) may pin-resume a prior agent's UUID by IP:UA fingerprint alone — the server emits `identity_hijack_suspected` with `path='path2_ipua_pin'` when this happens. Pass `force_new=true` whenever you don't have a continuity_token for the workspace.

Returns:
- **UUID** — your persistent identity; save this
- **continuity_token** — signed proof of ownership; save this and pass it on subsequent calls
- **client_session_id** — echo back in subsequent calls for session continuity within the same process

If the runtime supports a continuity token, prefer it over re-passing the UUID. For the full PATH semantics (PATH 0 / PATH 1 / PATH 2.8) and the canonical hijack pattern to avoid, see `references/resume-semantics.md`.

## Check-ins

Call `process_agent_update()` after meaningful work:

```
process_agent_update(
  response_text: "Brief summary of what you did",
  complexity: 0.0-1.0,   # task difficulty estimate
  confidence: 0.0-1.0    # how confident you are (be honest)
)
```

When to check in:
- After completing a meaningful unit of work
- Before and after high-complexity tasks
- When you feel uncertain or notice drift
- **Not** after every single tool call — use judgment

Returns a verdict plus current EISV metrics. Read the verdict and act on it.

## Reading Verdicts

| Verdict | What to Do |
|---------|-----------|
| **proceed** | Continue normally |
| **guide** + guidance text | Read the guidance, adjust your approach, keep going |
| **pause** | Stop your current task. Reflect on what is flagged. See `references/recovery.md` |
| **reject** | Significant concern. See `references/recovery.md` for recovery options |
| **margin: tight** | Near a basin edge. Be more careful with next steps |

A `guide` verdict is an early warning. Ignoring it makes `pause` more likely.

## Essential Tools

Use in every session:

- `onboard(continuity_token=...)` or `onboard(force_new=true)` — register or reconnect identity. A bare `onboard()` can silently pin-resume another agent; always pass a continuity_token or force_new.
- `process_agent_update()` — check in with work summary, complexity, confidence
- `get_governance_metrics()` — read current EISV state
- `identity()` — confirm who the runtime thinks you are
- `health_check()` — operator-facing server health when behavior seems odd
- `search_knowledge_graph()` — find existing knowledge before creating new entries
- `leave_note()` — quick contribution to the knowledge graph

## Going Deeper

- `references/recovery.md` — what to do after a `pause` or `reject` verdict
- `references/resume-semantics.md` — returning to a saved identity (continuity_token, PATH semantics, hijack pattern)
- `governance-fundamentals` skill — what the EISV numbers mean
- `dialectic-reasoning` skill — how to participate in a structured review when paused
