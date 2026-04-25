---
name: governance-fundamentals
description: >
  Use when an agent needs to understand UNITARES governance concepts — EISV state vectors,
  basins, verdicts, coherence, calibration. Reference material for interpreting governance
  metrics and understanding the thermodynamic model.
last_verified: "2026-04-25"
freshness_days: 14
source_files:
  - unitares/config/governance_config.py
  - unitares/src/auto_ground_truth.py
  - unitares/src/governance_monitor.py
  - unitares/src/mcp_handlers/core.py
---

# Governance Fundamentals

UNITARES gives AI agents digital proprioception — awareness of their own state, their relationship to the system, and whether they are drifting. Agent work is tracked through a thermodynamic model (energy, entropy, coherence) and a shared knowledge graph across all agents.

## EISV State Vector

Four dimensions, updated through check-ins:

| Dim | Range | Meaning |
|-----|-------|---------|
| **E** (Energy) | [0, 1] | Productive capacity |
| **I** (Information Integrity) | [0, 1] | Signal fidelity |
| **S** (Entropy) | [0, 1] | Semantic uncertainty (lower is better) |
| **V** (Void) | [-1, 1] | Accumulated E-I imbalance |

The dimensions couple — E pulls toward I, S responds to complexity, V accumulates imbalance, **coherence** falls out of all four. Coherence is *structural health* (how well E/I/S/V hold together as a vector), **not a quality score for your work** — this is what makes the "do not game coherence" rule below meaningful. For the coupling math, see `references/eisv-deep.md`.

## Verdicts — What to Do

Governance issues a verdict after each check-in. This is the operational signal:

| Verdict | Meaning | Action |
|---------|---------|--------|
| **proceed** | State is healthy | Continue working |
| **guide** | Something is slightly off | Read the guidance text, adjust approach |
| **pause** | Needs attention | Stop current work, reflect, consider dialectic review |
| **reject** | Significant concern | Requires dialectic review or human input |

A `margin: tight` flag means you are near a basin edge. Be more careful with next steps.

## Basins

Your state sits in a basin — a region of EISV space:

- **High basin**: Healthy. E and I high, S and V low. Normal operating range.
- **Low basin**: Degraded. May need recovery or intervention.
- **Boundary**: Transitioning. Verdicts may carry `margin: tight`.

Use `get_governance_metrics()` for the current basin/mode labels — do not assume they are constant across runtime versions.

## Diagnostics — When the Numbers Look Wrong

Do not guess first. Use:

- `identity()` — verify who the runtime thinks you are
- `health_check()` — verify the server and knowledge graph are healthy
- `get_governance_metrics()` — current live thresholds and interpreted state

## What NOT to Do

- **Do not game coherence** by reporting low complexity / high confidence on everything
- **Do not ignore guide verdicts** — they are early warnings before pause/reject
- **Do not create duplicate discoveries** — search the knowledge graph first
- **Do not check in after every trivial action** — it is noise, not signal
- **Do not leave high-severity findings open forever** — resolve or archive them

## Going Deeper

- `references/eisv-deep.md` — coupling math, coherence definition C(V, Theta), calibration internals
- `governance-lifecycle` skill — onboard, check-in, recovery flow
- `dialectic-reasoning` skill — what happens when a verdict pauses you
