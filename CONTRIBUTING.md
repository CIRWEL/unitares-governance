# Contributing

This repo is small, but it now has enough moving parts that direct pushes to `master` should be the exception rather than the default.

## Preferred Workflow

Use a lightweight branch and pull request flow:

1. Create a short-lived branch for each change
2. Keep the branch focused on one topic
3. Push the branch to GitHub
4. Open a PR
5. Merge after review or self-review

Recommended branch prefixes:

- `codex/` for Codex-authored changes
- `claude/` for Claude-authored changes
- `ops/` for operational changes
- `docs/` for documentation-only changes

Examples:

- `codex/codex-plugin-manifest`
- `docs/skill-refresh`
- `ops/session-start-hardening`

## What Belongs Together

Good PR scope:

- one plugin packaging change
- one skill refresh batch
- one hook behavior change
- one README or docs cleanup pass

Bad PR scope:

- hooks + skills + Discord bridge + repo restructuring all mixed together

If a change touches both behavior and docs, keep them together only if the docs explain that exact behavior change.

## Practical Review Standard

Before opening or merging a PR, check:

- the README still matches the runtime story
- commands match current UNITARES semantics
- skills do not point at stale server paths
- hooks do not create noisy or misleading governance behavior

## Current Principle

Prefer:

- meaningful check-ins over per-edit check-ins
- live runtime diagnostics over hardcoded thresholds
- adapter-specific behavior in adapter files
- shared guidance in shared skills and commands

## When Direct Push Is Fine

Direct push to `master` is still acceptable for:

- tiny typo fixes
- clearly mechanical path/reference corrections
- emergency fixes where speed matters more than review overhead

Everything else should prefer a branch and PR.
