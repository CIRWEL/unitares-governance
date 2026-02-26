# UNITARES Governance Plugin

Thermodynamic governance for AI agents. This Claude Code plugin automatically enrolls agents in the UNITARES governance framework — tracking energy, entropy, coherence, and drift through a continuous ODE model.

## What It Does

- **Auto-onboard**: SessionStart hook registers your agent with the governance server
- **Auto-checkin**: PostToolUse hook reports every code edit to governance
- **EISV monitoring**: Energy, Information Integrity, Entropy, Void tracked continuously
- **Dialectic resolution**: Structured thesis/antithesis/synthesis for governance disputes
- **Knowledge graph**: Shared institutional memory across all agents
- **Discord bridge**: Optional live Discord server surfacing all governance activity

## Prerequisites

1. A running UNITARES governance MCP server
2. MCP server configured in `~/.claude.json`:
   ```json
   {
     "mcpServers": {
       "unitares-governance": {
         "type": "url",
         "url": "http://localhost:8767/mcp/"
       }
     }
   }
   ```

## Installation

```bash
# Clone the plugin
git clone https://github.com/CIRWEL/unitares-governance.git

# Install in Claude Code (from the repo directory)
# Or symlink into ~/.claude/plugins/
```

## Configuration

Set environment variables (in your shell profile or project `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `UNITARES_SERVER_URL` | `http://localhost:8767` | Governance MCP server URL |
| `UNITARES_AGENT_PREFIX` | `claude` | Prefix for auto-generated agent names |

## Usage

Once installed, governance is automatic:

1. **Start a session** — the plugin onboards your agent and shows current EISV
2. **Write code** — every edit auto-checks-in with governance
3. **Get verdicts** — proceed, guide, pause, or reject based on your state

### Commands

| Command | Description |
|---------|-------------|
| `/checkin` | Manual check-in with summary, complexity, confidence |
| `/diagnose` | Show current EISV, coherence, risk, verdict |
| `/dialectic` | Request a dialectic review |

### Skills

| Skill | When to Use |
|-------|-------------|
| `unitares-governance:governance-fundamentals` | Understanding EISV, basins, verdicts |
| `unitares-governance:governance-lifecycle` | Onboarding, check-ins, recovery |
| `unitares-governance:dialectic-reasoning` | Participating in dialectic sessions |
| `unitares-governance:knowledge-graph` | Searching and contributing to shared knowledge |
| `unitares-governance:discord-bridge` | Setting up the Discord integration |

## Architecture

The plugin connects to a UNITARES governance MCP server via HTTP. The server runs the thermodynamic ODE model and maintains state. This plugin is the client — it reports work and receives verdicts. It never modifies governance parameters directly.

```
Agent (Claude Code)
  ├── SessionStart hook → onboard() → get EISV context
  ├── PostToolUse hook  → process_agent_update() → receive verdict
  ├── Skills            → reference material for agents
  ├── Commands          → manual governance interactions
  └── Agent             → governance-reviewer for health assessment
          │
          ▼
   Governance MCP Server (localhost:8767)
   ├── ODE solver (EISV dynamics)
   ├── Knowledge graph (PostgreSQL + AGE)
   ├── Dialectic engine
   └── Calibration tracker
```

## License

MIT
