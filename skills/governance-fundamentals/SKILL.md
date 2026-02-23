---
name: governance-fundamentals
description: >
  Use when an agent needs to understand UNITARES governance concepts — EISV state vectors,
  basins, verdicts, coherence, calibration. Reference material for interpreting governance
  metrics and understanding the thermodynamic model.
---

# Governance Fundamentals

## What UNITARES Is

UNITARES provides digital proprioception for AI agents — awareness of your own state, your relationship to the system, and whether you are drifting. It tracks agent work through a thermodynamic model (energy, entropy, coherence) and maintains a shared knowledge graph across all agents.

## EISV State Vector

Every agent has four dimensions, updated through check-ins:

| Dimension | Range | Meaning |
|-----------|-------|---------|
| **E** (Energy) | [0, 1] | Productive capacity |
| **I** (Information Integrity) | [0, 1] | Signal fidelity |
| **S** (Entropy) | [0, 2] | Semantic uncertainty (lower is better) |
| **V** (Void) | [-2, 2] | Accumulated E-I imbalance |

### How They Couple

- **E (Energy)**: Couples toward I (when I > E, energy rises). Dragged down by high entropy via E*S cross-coupling. High complexity affects E indirectly through S.
- **I (Information Integrity)**: Boosted by coherence C(V,Theta), reduced by entropy S. Has logistic self-regulation. Confidence and calibration affect I indirectly via the check-in pipeline (they drive S and ethical drift, which couple to I).
- **S (Entropy)**: Naturally decays (mu*S), rises with ethical drift and task complexity, reduced by coherence. The only dimension that directly responds to complexity.
- **V (Void)**: Accumulated E-I imbalance. Positive when energy exceeds integrity (running hot), negative when integrity exceeds energy (running careful). Decays toward zero over time. Drives coherence via C(V,Theta).

These combine into a **coherence** score and **risk** score that determine governance decisions.

### Lumen Sensor Mappings

For Lumen (the embodied agent on Pi): E=warmth, I=clarity, S=1-stability, V=(1-presence)*0.3. These seed the ODE initial conditions. The governance dynamics then evolve the state independently — the ODE state can diverge from sensor observations, especially for V (signed integral [-2,2] vs unsigned observation [0,0.3]).

## Basins

Your state sits in a basin — a region of the EISV space:

- **High basin**: Healthy. E and I are high, S and V are low. Normal operating range.
- **Low basin**: Degraded. May need recovery or intervention.
- **Boundary**: Transitioning between basins. Extra attention from governance. Verdicts may carry `margin: tight`.

## Verdicts

Governance issues a verdict after each check-in:

| Verdict | Meaning | Action |
|---------|---------|--------|
| **proceed** | State is healthy | Continue working normally |
| **guide** | Something is slightly off | Read the guidance text, adjust approach |
| **pause** | Needs attention | Stop current work, reflect, consider dialectic review |
| **reject** | Significant concern | Requires dialectic review or human input |

A `margin: tight` flag means you are near a basin edge. Be more careful with next steps.

## Coherence

Coherence measures how well your state vector holds together. It is calculated from the EISV values — not from the content of your work. Think of it as structural health, not semantic quality.

- Range is roughly [0.45, 0.55] in practice
- Do not chase a number — check in honestly and let it track naturally
- Coherence is derived from C(V, Theta) — it reflects balance, not performance

## Calibration

The system tracks whether your stated confidence matches outcomes. Over time this builds a calibration curve.

- Known limitation: it measures peer consensus, not external ground truth
- Epistemic humility tends to correlate with better trajectories
- Overconfidence is tracked and penalizes Information Integrity through the entropy coupling

## What NOT to Do

- **Do not game coherence** by reporting low complexity / high confidence on everything
- **Do not ignore guide verdicts** — they are early warnings before pause/reject
- **Do not create duplicate discoveries** — always search the knowledge graph first
- **Do not check in after every trivial action** — it is noise, not signal
- **Do not leave high-severity findings as open forever** — resolve or archive them
