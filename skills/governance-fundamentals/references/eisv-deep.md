# EISV — Coupling Math and Internals

Reference material for the four EISV dimensions and the dynamics that connect them. Loaded by `governance-fundamentals/SKILL.md` on demand. If you only need to *use* the signals — read what tool to call when a verdict fires — stay in the SKILL body.

## How the Dimensions Couple

- **E (Energy)**: Couples toward I (when I > E, energy rises). Dragged down by high entropy via E*S cross-coupling. High complexity affects E indirectly through S, not directly.
- **I (Information Integrity)**: Boosted by coherence C(V, Theta), reduced by entropy S. Has logistic self-regulation. Confidence and calibration affect I indirectly via the check-in pipeline (they drive S and ethical drift, which couple to I).
- **S (Entropy)**: Naturally decays (mu*S), rises with ethical drift and task complexity, reduced by coherence. The only dimension that responds *directly* to complexity.
- **V (Void)**: Accumulated E-I imbalance. Positive when energy exceeds integrity (running hot), negative when integrity exceeds energy (running careful). Decays toward zero over time. Drives coherence via C(V, Theta).

These combine into a **coherence** score and **risk** score that determine governance decisions.

## Coherence — What the Number Means

Coherence measures how well your state vector holds together. It is calculated from the EISV values — not from the content of your work. Think of it as structural health, not semantic quality.

- Full range is [0, 1], clipped from thermodynamic C(V, Theta)
- Critical threshold is available via `get_governance_metrics()` in the `thresholds` field — do not hardcode it
- Do not chase a number — check in honestly and let it track naturally
- Coherence reflects balance, not performance

### Which V feeds coherence

`get_governance_metrics(lite=false)` exposes V in three places: `ode_eisv.V`, `behavioral_eisv.V`, and `primary_eisv.V`. They can diverge significantly — do not assume a single V.

- **`ode_eisv.V`** — thermodynamic integrator, heavily damped, typically lives in ~[−0.1, 0.1]. **Coherence is computed from this V** (`governance_state.py:229` calling `coherence_func(state.V, ...)`). That is why `coherence` often sits near 0.5 (tanh(0)=0 midpoint) regardless of what behavioral V is doing.
- **`behavioral_eisv.V`** — observation-first EMA of actual agent behavior. Can swing to ±0.4. **Verdicts** use this channel once `behavioral_eisv.confidence ≥ 0.3`; before that, verdicts fall back to ODE.
- **`primary_eisv`** — whichever channel is currently authoritative for verdicts. Check `primary_eisv_source` to see which.

Practical implication: a large move in behavioral V will not move coherence in lockstep. If you are interpreting a flat coherence next to a swinging V, you are almost certainly comparing across channels. To actually move coherence you must move ODE V via sustained E-I imbalance, not via short-term behavioral swings. The `state_semantics` block in the metrics response is the runtime-authoritative version of this.

## Calibration — How Ground Truth Feeds Back

The system tracks whether your stated confidence matches outcomes. Over time this builds a calibration curve.

- Ground truth comes from objective signals: test pass/fail, command exit codes, lint results, file operations. These feed calibration automatically via `auto_ground_truth.py` and the `outcome_event` hook. Human validation is not required for deterministic outcomes.
- Overconfidence is tracked and penalizes Information Integrity through the entropy coupling.

## Source Files

- `unitares/config/governance_config.py` — coupling constants, basin thresholds
- `unitares/src/auto_ground_truth.py` — calibration feedback path
- `unitares/src/governance_monitor.py` — EISV evolution loop
- `unitares/src/mcp_handlers/core.py` — verdict computation

Prefer live tool output (`get_governance_metrics()`) over static range lore in this document if the runtime reports a narrower or more precise bound.
