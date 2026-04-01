description: "Manual UNITARES governance check-in after meaningful work"
---

Call `process_agent_update` for the current agent after a meaningful unit of work.

Inputs:

- `response_text`: concise summary of what was actually accomplished
- `complexity`: estimate `0.0-1.0`
- `confidence`: honest estimate `0.0-1.0`
- include `client_session_id` or `continuity_token` when available

Guidelines:

- Do not check in after every trivial edit.
- Prefer one check-in per meaningful milestone, completed step, or decision point.
- If recent local edit context exists, use it to improve the summary, but do not report raw file churn as if it were real progress.

After the call:

- report the verdict
- report any guidance briefly
- if verdict is `pause` or `reject`, recommend `request_dialectic_review`
- if verdict is `guide`, summarize the guidance and adjust behavior
