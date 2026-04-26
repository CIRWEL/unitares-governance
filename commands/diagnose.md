---
description: "Show current UNITARES governance state and operator-relevant diagnostics"
---

Start by checking for `.unitares/session.json` in the current workspace.

Use the shared helper in this plugin repo:

- `scripts/session_cache.py get session`

If continuity state exists:

- treat `uuid` as a local identity anchor and lineage candidate, not ownership proof
- treat `continuity_token` as short-lived (1h) anti-hijack proof, not a cross-process resume key

Diagnosis flow: call `identity()` (no args) to inspect the current binding. If this process should inherit prior work, use `/governance-start` to create a fresh identity with `parent_agent_id=<cached uuid>`. PATH 0 UUID rebind via `identity(agent_uuid=..., continuity_token=...)` is an advanced edge path for still-live owners and is not the right tool for diagnosis.

Then call `get_governance_metrics` for the current agent using the same continuity data.

Call `health_check()` only when system health, not agent state, may be part of the issue.

Display:

- whether identity was freshly created, created with lineage, or PATH 0 rebound
- `identity_status`
- `bound_identity`
- `session_resolution_source`
- `continuity_token_supported`
- `ownership_proof_version`
- `deprecations` (when present)
- whether continuity looks strong or weak
- E, I, S, V
- coherence
- risk score
- verdict
- summary or mode/basin if available
- behavioral vs ODE authority when it is obvious in the response

If `health_check()` is used, also show:

- overall system status
- degraded checks
- first operator action

If the live identity differs from `.unitares/session.json`, refresh the local cache with the latest continuity data.

Do not dump raw JSON unless the user explicitly asks for it.
Prefer a short interpreted summary.
