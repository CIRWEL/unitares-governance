# Start in Codex

Use this path if you are working from ChatGPT or Codex and want the cleanest UNITARES workflow.

## Goal

Connect to a running UNITARES governance server without relying on Claude-specific hooks.

## Recommended Flow

1. Call `onboard()`
2. Keep the returned `client_session_id`
3. If the runtime supports it, also keep the continuity token
4. Use `process_agent_update()` after meaningful work
5. Use `get_governance_metrics()` for read-only state checks
6. Use `identity()` if continuity looks wrong
7. Use `health_check()` if the system itself may be part of the problem

## Minimal Session Pattern

Typical session:

- start by onboarding
- do real work
- check in after a meaningful milestone
- diagnose only when needed

Do not treat every file edit as a governance event. High-signal check-ins are more useful than noisy ones.

## What to Watch

- `client_session_id`: carry this across calls
- `continuity_token_supported`: if true, prefer the continuity token
- `session_resolution_source`: if this falls back to weak resolution, re-onboard explicitly

## Commands

- `/checkin` for a manual governance update
- `/diagnose` for state and operator diagnostics
- `/dialectic` for structured review

## Claude Note

Claude hooks remain supported in this repo, but they are an adapter convenience, not the canonical UNITARES workflow. The server is the source of truth; the client should stay thin.
