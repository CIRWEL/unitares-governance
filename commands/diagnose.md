---
description: "Show current UNITARES governance state — EISV, coherence, risk, verdict"
---

Call `get_governance_metrics` with `include_state=true` for the current agent.

Display a readable summary:
- EISV values with brief interpretation (e.g., "E=0.74 (healthy)" or "S=1.3 (high, needs attention)")
- Coherence score and whether it's trending up or down
- Risk score
- Current verdict
- Basin (high/low/boundary)
- Any active dialectic sessions (check via the `dialectic` tool with `action=list`)

Format as clean text, not raw JSON. Use the governance-fundamentals skill for interpretation guidelines.
