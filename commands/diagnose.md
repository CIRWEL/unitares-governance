---
description: "Show current UNITARES governance state and operator-relevant diagnostics"
---

Call `get_governance_metrics` for the current agent.

Also call:

- `identity()` when identity continuity is unclear
- `health_check()` when system health may be part of the issue

Display:

- E, I, S, V
- coherence
- risk score
- verdict
- summary or mode/basin if available

If `identity()` is used, also show:

- `identity_status`
- `bound_identity`
- `session_resolution_source`
- whether continuity is strong or weak

If `health_check()` is used, also show:

- overall system status
- degraded checks
- first operator action

Do not dump raw JSON unless the user explicitly asks for it.
Prefer a short interpreted summary.
