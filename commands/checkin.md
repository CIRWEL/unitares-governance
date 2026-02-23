---
description: "Manual governance check-in — report what you did, complexity, and confidence to UNITARES"
---

Call the UNITARES `process_agent_update` tool with:
- `response_text`: A brief summary of what was just accomplished (derive from recent context or ask the user)
- `complexity`: Estimate 0.0-1.0 of how difficult the work was
- `confidence`: Estimate 0.0-1.0 of how confident you are in the output (be honest — overconfidence is tracked by calibration)

Report the verdict and any guidance back to the user. If the verdict is "guide", read and follow the guidance text. If "pause", stop current work and consider requesting a dialectic review.
