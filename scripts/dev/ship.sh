#!/usr/bin/env bash
# ship.sh — agent-friendly commit-and-deliver
#
# Routes changes to the right delivery path based on what they touch:
#   - Runtime code (hooks/, check-in helper scripts, plugin manifest) →
#     feature branch + PR + auto-merge-on-green.
#   - Everything else (docs, skills/, commands/, tests) → direct commit +
#     push on the current branch.
#
# This plugin runs inside every Claude Code session via hooks; a change
# to hooks/ or the check-in pipeline can brick onboarding for the whole
# fleet. Skills and docs are safe to land directly.
#
# Usage:
#   ./scripts/dev/ship.sh "commit message"
#   ./scripts/dev/ship.sh --classify          # just print "runtime" or "other"
#
# Requirements: staged changes (git add already done), gh CLI authed.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

RUNTIME_PATTERNS=(
    '^hooks/'
    '^scripts/checkin\.py$'
    '^scripts/_redact\.py$'
    '^scripts/auto_checkin_decision\.py$'
    '^scripts/_session_lookup\.py$'
    '^scripts/session_cache\.py$'
    '^\.claude-plugin/plugin\.json$'
    '^\.claude-plugin/marketplace\.json$'
)

classify() {
    local files; files=$(git diff --cached --name-only)
    if [[ -z "$files" ]]; then
        echo "empty"; return
    fi
    while IFS= read -r f; do
        for pat in "${RUNTIME_PATTERNS[@]}"; do
            if [[ "$f" =~ $pat ]]; then
                echo "runtime"; return
            fi
        done
    done <<< "$files"
    echo "other"
}

if [[ "${1:-}" == "--classify" ]]; then
    classify
    exit 0
fi

MESSAGE="${1:-}"
if [[ -z "$MESSAGE" ]]; then
    echo "usage: ship.sh \"commit message\"" >&2
    exit 2
fi

KIND=$(classify)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

case "$KIND" in
    empty)
        echo "nothing staged — stage files with 'git add' first" >&2
        exit 2 ;;
    runtime)
        SLUG=$(printf '%s' "$MESSAGE" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-40)
        NEW_BRANCH="codex/auto/$(date +%Y%m%d-%H%M%S)-${SLUG}"
        echo "[ship] runtime path → $NEW_BRANCH (PR + auto-merge)"
        git checkout -b "$NEW_BRANCH"
        git commit -m "$MESSAGE"
        git push -u origin "$NEW_BRANCH"
        PR_URL=$(gh pr create --title "$MESSAGE" --body "Auto-shipped by ship.sh — runtime path. Auto-merge is enabled; CI gate applies.")
        echo "$PR_URL"
        gh pr merge --auto --squash "$PR_URL" || \
            echo "[ship] auto-merge not enabled (branch protection may require manual setup); PR is open"
        ;;
    other)
        echo "[ship] non-runtime → direct commit + push on $BRANCH"
        git commit -m "$MESSAGE"
        # Push to the same-name branch on origin, not whatever upstream tracks
        # (a feature branch may track master and would otherwise push ambiguously).
        git push origin "HEAD:$BRANCH"
        ;;
esac
