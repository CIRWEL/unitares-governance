---
name: unitares-governance
description: >
  Compatibility umbrella skill for the UNITARES governance framework. Use this
  as the entrypoint when you need the overall model and route into the split
  governance skills.
last_verified: "2026-04-25"
freshness_days: 14
source_files:
  - skills/governance-lifecycle/SKILL.md
  - skills/governance-fundamentals/SKILL.md
  - skills/knowledge-graph/SKILL.md
  - skills/dialectic-reasoning/SKILL.md
  - skills/discord-bridge/SKILL.md
---

# UNITARES Governance

This umbrella skill exists for backward compatibility and as a stable top-level
entrypoint into the UNITARES framework.

## Core Model

UNITARES evaluates agent state with the **EISV** model:

- `E`: effective energy / execution drive
- `I`: integrity / coherence of alignment
- `S`: entropy / disorder / instability
- `V`: void pressure / collapse tendency

Agents typically start with `onboard(force_new=true)` and continue with
`process_agent_update()` as their main check-in loop.

## Session Continuity

Use `onboard(force_new=true)` to register a fresh process identity. If
the process is continuing prior work, declare that with
`parent_agent_id=<prior uuid>` and `spawn_reason="new_session"`.

`identity(agent_uuid=..., continuity_token=...)` is an advanced PATH 0
rebind for still-live UUIDs only — not part of the normal session-start
or check-in flow. The `continuity_token` is short-lived (1h, rolling)
ownership proof for anti-hijack gates, not indefinite cross-process
continuity.

Bare `onboard()` is no longer a silent hazard: the server's S13 fresh-
instance gate auto-promotes `force_new=true` when no proof signal is
presented and emits `[FRESH_INSTANCE]` in the audit log. Pass
`force_new=true` explicitly anyway — it makes intent legible. Bare
`identity(agent_uuid=<uuid>)` without a matching token remains the
canonical hijack pattern and is strict-mode rejected.

Use `process_agent_update()` after meaningful work to record progress,
complexity, and confidence, then read the returned governance verdict.

## Knowledge Layer

The governance system is coupled to the **knowledge graph**. Agents should
search existing knowledge before duplicating work, and contribute discoveries,
questions, and answers as they learn.

## Split Skills

The old monolithic skill was split into focused skills:

- `skills/governance-lifecycle/SKILL.md` for onboarding, check-ins, and recovery
- `skills/governance-fundamentals/SKILL.md` for EISV, basins, coherence, and verdicts
- `skills/knowledge-graph/SKILL.md` for knowledge graph search and contribution
- `skills/dialectic-reasoning/SKILL.md` for thesis/antithesis/synthesis workflows
- `skills/discord-bridge/SKILL.md` for the Discord governance bridge

If you need the full mental model, start here. If you know the task shape,
prefer the focused skill directly.
