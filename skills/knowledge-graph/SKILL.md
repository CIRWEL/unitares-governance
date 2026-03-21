---
name: knowledge-graph
description: >
  Use when an agent needs to search the shared knowledge graph, contribute a discovery,
  or update existing entries. Covers search, tagging, discovery types, and status lifecycle.
last_verified: "2026-03-20"
freshness_days: 14
source_files:
  - governance-mcp-v1/src/mcp_handlers/knowledge.py
  - governance-mcp-v1/src/knowledge_graph.py
---

# Knowledge Graph

## What It Is

The knowledge graph is shared institutional memory across all agents. It is backed by PostgreSQL with Apache AGE for graph queries. Every agent can search, contribute, and update entries. Discoveries persist across sessions and are available to all agents in the system.

## Search Before Creating

Always search before adding new entries:

```
search_knowledge_graph(
  query: "description of what you're looking for",
  tags: ["relevant", "tags"],
  limit: 10,
  min_similarity: 0.5
)
```

This uses semantic search (embeddings) plus tag matching. Duplicate entries fragment knowledge and make search less effective.

## Quick Contribution

For low-friction contributions, use `leave_note()`:

```
leave_note(
  note: "What you discovered or observed",
  tags: ["domain", "type", "context"]
)
```

Notes are automatically shared with all agents. Use this when you find something useful, spot a bug, or have an insight that others should know about.

## Full CRUD Operations

For more control, use the `knowledge()` tool with an action parameter:

| Action | Purpose |
|--------|---------|
| `store` | Create a new discovery with full metadata |
| `search` | Search by query, tags, or both |
| `get` | Retrieve a specific discovery by ID |
| `list` | List discoveries with filters |
| `update` | Modify an existing discovery (status, content, tags) |
| `details` | Get full details including graph relationships |
| `note` | Same as `leave_note()` but through the unified interface |
| `cleanup` | Mark stale entries for review |
| `stats` | Get knowledge graph statistics |

## Discovery Types

When storing a discovery, classify it:

| Type | When to Use |
|------|-------------|
| `note` | General observation, context, or reminder |
| `insight` | Understanding gained from analysis or pattern recognition |
| `bug_found` | A bug or defect you identified |
| `improvement` | A suggestion for how something could be better |
| `analysis` | Detailed examination of a system, pattern, or behavior |
| `pattern` | A recurring pattern you noticed across multiple instances |

## Status Lifecycle

Every discovery has a status:

```
open  -->  resolved    (problem solved, finding addressed)
  \-->  archived     (no longer relevant, superseded)
```

- **open**: Active, still relevant, may need attention
- **resolved**: The issue or finding has been addressed
- **archived**: No longer relevant (outdated, superseded, or duplicate)

## Tagging Best Practices

Tags are how future agents find your contributions. Be intentional:

- **Include the domain**: `identity`, `database`, `performance`, `deployment`, `testing`
- **Include the type**: `bug`, `insight`, `pattern`, `config`, `dependency`
- **Include context**: `postgres`, `eisv`, `dialectic`, `discord-bridge`
- **Be specific**: `pool-connection-leak` is more useful than `bug`
- **Be consistent**: Check existing tags before inventing new ones

## Closing the Loop

The graph accumulates knowledge well but does not close loops automatically. This is a known gap that every agent should help address:

- **When you resolve something, update its status.** Do not leave it as `open`.
- **When you find a duplicate, archive the less complete one** and reference the better entry.
- **When a finding is outdated, archive it** with a note about what superseded it.
- **Periodically check for stale entries** in your domain using `knowledge(action="cleanup")`.

Unresolved entries create noise. Closed loops create trust in the graph.
