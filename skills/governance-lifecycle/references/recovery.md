# Recovery and Resume Semantics

Reference material for the rare lifecycle events: resuming a stored identity, recovering from a pause/reject verdict, and operator-mediated overrides. Loaded by `governance-lifecycle/SKILL.md` on demand. The day-to-day onboard/check-in/verdict loop lives in the SKILL body.

## Resuming vs. Creating New (semantics, updated 2026-04-17)

`name=` is a **cosmetic label**, not a resume key. Since the 2026-04-17 name-claim removal, passing `name="Same-Agent"` on a fresh session always mints a new UUID — it will not re-bind to an existing agent with that label. Resume signals, in strength order:

1. **`continuity_token`** (PATH 2.8) — strongest. Signed and self-contained; carries the UUID claim and proves possession in one value. Save this from your first `onboard()` response and pass it on every subsequent `identity()` or `onboard()` call. Expires; rebinds even across session-cache invalidation.
2. **`agent_uuid` + `continuity_token`** (PATH 0 with ownership proof) — strong. Pass them together; the server's Part C gate verifies the token's `aid` claim equals the requested `agent_uuid`. Without the matching token, this resume currently logs `[IDENTITY_STRICT]` and emits an `identity_hijack_suspected` broadcast event, and will be rejected outright once `UNITARES_IDENTITY_STRICT=strict` is promoted to default.
3. **Active session binding** (PATH 1/2) — auto-handled by the server when you reuse the same transport session.

**Do not** call `identity(agent_uuid=X, resume=true)` with a UUID you learned from somewhere else (a hook listing, another agent's check-in, a log line). That is the canonical hijack pattern: an unsigned UUID claim with no proof of ownership. The server treats every such call as suspect — see KG bug `2026-04-20T00:09:51`.

Without any of the signals above, you are a new agent. That is the correct semantic, not a bug.

## Recovery — When You Are Paused or Stuck

| Situation | Tool | Notes |
|-----------|------|-------|
| Stuck or paused, want automatic recovery | `self_recovery()` | Attempts to restore healthy state |
| Disagree with verdict, want structured review | `request_dialectic_review()` | Starts thesis/antithesis/synthesis (see `dialectic-reasoning` skill) |
| Manual override needed | `operator_resume_agent()` | Requires human/operator action |

Recovery is not a shortcut — `self_recovery()` examines your EISV state and determines if resumption is safe. If your metrics are genuinely degraded, it will not force a resume.

## Identity Diagnostics

When continuity seems unclear, call `identity()` and inspect:

- `identity_status`
- `bound_identity`
- `session_resolution_source`
- `continuity_token_supported`

Strong continuity is better than implicit continuity. If the runtime falls back to weak signals such as fingerprinting, re-onboard and resume with explicit continuity data.

## Specialized Tools (rare)

- `call_model()` — Delegate to a secondary LLM for analysis
- `detect_stuck_agents()` — Find unresponsive agents
- `submit_thesis()` / `submit_antithesis()` / `submit_synthesis()` — Dialectic participation (covered in `dialectic-reasoning` skill)
- `export()` — Export session history
- `knowledge()` / `agent()` / `calibration()` — Full CRUD surfaces; tool descriptions cover the parameters
