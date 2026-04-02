# UNITARES Governance

Governance client for UNITARES. This repo provides agent-facing skills, commands, and client adapters for connecting coding agents to a running UNITARES governance server.

## Purpose

This repo is not the governance engine itself. It is the client and integration layer.

Use it to:

- onboard agents into UNITARES
- inspect governance state and operator diagnostics
- request dialectic review
- work with the knowledge graph
- adapt UNITARES workflows to Codex, ChatGPT, Claude, and other clients

## What Lives Elsewhere

- `governance-mcp-v1` contains the runtime, MCP server, storage, health checks, and governance logic
- `unitares-governance` contains the agent-facing plugin and integration layer
- optional bridges like Discord can remain separate integrations

This repo should not duplicate server business logic or become the source of truth for thresholds that already live in the runtime.

## Current Adapters

- Codex/ChatGPT adapter: plugin packaging plus shared skills and commands
- Claude adapter: hooks, session helpers, and command docs

The shared value in this repo is the workflow guidance and client integration surface, not a second copy of the governance model.

## Start Here

If you are using ChatGPT or Codex, start with [CODEX_START.md](./CODEX_START.md).

That path is now the preferred default. Claude hook automation remains supported, but it is no longer the canonical mental model for UNITARES usage.

## Core Workflow

The intended workflow is:

1. `onboard()`
2. preserve `client_session_id` and `continuity_token` when available
3. call `process_agent_update()` after meaningful work
4. call `get_governance_metrics()` for read-only state
5. call `identity()` and `health_check()` when diagnosis is needed

The principle is simple: prefer high-signal governance over high-frequency governance. Meaningful check-ins beat noisy check-ins.

## Commands

| Command | Description |
|---------|-------------|
| `/checkin` | Manual check-in after meaningful work |
| `/diagnose` | Show current governance state plus identity/health diagnostics when needed |
| `/dialectic` | Request a dialectic review |

## Skills

| Skill | When to Use |
|-------|-------------|
| `unitares-governance:governance-fundamentals` | Understanding EISV, coherence, verdicts, and calibration |
| `unitares-governance:governance-lifecycle` | Onboarding, continuity, check-ins, and recovery |
| `unitares-governance:dialectic-reasoning` | Participating in dialectic sessions |
| `unitares-governance:knowledge-graph` | Searching and contributing to shared memory |
| `unitares-governance:discord-bridge` | Operating the Discord integration |

## Prerequisites

1. A running UNITARES governance server
2. The governance MCP endpoint reachable by the client

Example local endpoint:

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

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `UNITARES_SERVER_URL` | `http://localhost:8767` | Governance server base URL |
| `UNITARES_AGENT_PREFIX` | `claude` | Prefix for generated client-side names in Claude hooks |

## Adapter Notes

### Claude

The current Claude adapter includes session-start and post-edit hooks. Those hooks should be treated as an adapter convenience, not the canonical governance policy. In particular, frequent file writes should not automatically be interpreted as meaningful governance events.

### Codex

Codex and ChatGPT support should stay minimal and explicit:

- package shared skills through `.codex-plugin/plugin.json`
- expose manual commands
- avoid client-specific auto-checkin behavior until there is a Codex-native reason to add it

## Non-Goals

This repo should not:

- redefine the governance math
- duplicate server-side threshold logic
- auto-checkin every trivial file write by default
- override runtime verdicts locally

## Development Workflow

Use a lightweight branch and PR flow for normal changes:

1. create a short-lived branch
2. keep the change focused
3. push the branch
4. open a PR
5. merge after review or self-review

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the repo convention.

## License

MIT
