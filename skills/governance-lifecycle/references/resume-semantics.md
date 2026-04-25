# Resume Semantics — Returning to a Saved Identity

Reference material for the rare case of resuming a previously-saved identity (continuity_token from a prior session, agent_uuid from a workspace cache). Loaded by `governance-lifecycle/SKILL.md` on demand from the "Starting a Session" pointer. Day-to-day onboarding lives in the SKILL body.

For the *other* kind of recovery — recovering from a paused verdict — see `references/recovery.md` instead. The two are unrelated.

## Updated 2026-04-17 — Name Is Cosmetic

`name=` is a **cosmetic label**, not a resume key. Since the 2026-04-17 name-claim removal, passing `name="Same-Agent"` on a fresh session always mints a new UUID — it will not re-bind to an existing agent with that label.

## Resume Signals (strength order)

1. **`continuity_token`** (PATH 2.8) — strongest. Signed and self-contained; carries the UUID claim and proves possession in one value. Save this from your first `onboard()` response and pass it on every subsequent `identity()` or `onboard()` call. Expires; rebinds even across session-cache invalidation.

2. **`agent_uuid` + `continuity_token`** (PATH 0 with ownership proof) — strong. Pass them together; the server's Part C gate verifies the token's `aid` claim equals the requested `agent_uuid`. Without the matching token, this resume currently logs `[IDENTITY_STRICT]` and emits an `identity_hijack_suspected` broadcast event, and will be rejected outright once `UNITARES_IDENTITY_STRICT=strict` is promoted to default.

3. **Active session binding** (PATH 1/2) — auto-handled by the server when you reuse the same transport session.

## The Canonical Hijack Pattern — Do Not Do This

**Do not** call `identity(agent_uuid=X, resume=true)` with a UUID you learned from somewhere else (a hook listing, another agent's check-in, a log line). That is the canonical hijack pattern: an unsigned UUID claim with no proof of ownership. The server treats every such call as suspect — see KG bug `2026-04-20T00:09:51`.

Without any of the signals above, you are a new agent. That is the correct semantic, not a bug.

## Identity Diagnostics

When continuity seems unclear, call `identity()` and inspect:

- `identity_status`
- `bound_identity`
- `session_resolution_source`
- `continuity_token_supported`

Strong continuity is better than implicit continuity. If the runtime falls back to weak signals such as fingerprinting, re-onboard and resume with explicit continuity data.
