# UNITARES Governance Plugin Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the UNITARES governance client plugin from the main unitares repo into its own standalone repo (`CIRWEL/unitares-governance-plugin`), synced with all evolved code, and make it the single source of truth for client-side hooks and skills.

**Architecture:** The plugin repo is the distributable client artifact — hooks, skills, commands, helper scripts. The main repo keeps the MCP server, agents (watcher/sentinel/vigil), and infrastructure. Global hooks in `~/.claude/settings.json` reference the plugin repo's helpers. The stop-checkin hook uses the plugin's `session_cache.py` instead of hardcoding a path to the main repo.

**Tech Stack:** Bash hooks, Python helper scripts (stdlib only, no deps), Claude Code plugin system (`.claude-plugin/plugin.json`, `hooks/hooks.json`)

---

### Task 1: Rename GitHub repo to include "plugin"

**Files:**
- Modify: `README.md` (update repo URL references)
- Modify: `.claude-plugin/plugin.json` (update source URL)
- Modify: `.codex-plugin/plugin.json` (update source URL)

- [ ] **Step 1: Rename the repo on GitHub**

```bash
gh repo rename unitares-governance-plugin --repo CIRWEL/unitares-governance --yes
```

- [ ] **Step 2: Update local remote URL**

```bash
cd ~/projects/unitares-governance-plugin
git remote set-url origin https://github.com/CIRWEL/unitares-governance-plugin.git
```

- [ ] **Step 3: Verify remote**

Run: `git remote -v`
Expected: `origin https://github.com/CIRWEL/unitares-governance-plugin.git`

---

### Task 2: Sync session-start hook with main repo's evolved version

The main repo's `hooks/session-start` has critical improvements over the standalone plugin's version:
- `onboard_helper.py` flow (cache-read → onboard → trajectory retry → cache-write)
- Session slot resolution for parallel Claude processes
- Auth token support (`UNITARES_HTTP_API_TOKEN`)
- Multi-layout path resolution (works in both plugin and monorepo layouts)

**Files:**
- Overwrite: `hooks/session-start` — copy from `/Users/cirwel/projects/unitares/hooks/session-start`
- Create: `scripts/onboard_helper.py` — copy from `/Users/cirwel/projects/unitares/scripts/client/onboard_helper.py`

- [ ] **Step 1: Copy the evolved session-start hook**

```bash
cp /Users/cirwel/projects/unitares/hooks/session-start \
   ~/projects/unitares-governance-plugin/hooks/session-start
```

- [ ] **Step 2: Copy onboard_helper.py**

```bash
cp /Users/cirwel/projects/unitares/scripts/client/onboard_helper.py \
   ~/projects/unitares-governance-plugin/scripts/onboard_helper.py
```

- [ ] **Step 3: Verify session-start resolves helpers in plugin layout**

The session-start hook already has multi-layout path resolution (lines 16-46) that checks both `scripts/onboard_helper.py` and `scripts/client/onboard_helper.py`. Confirm `onboard_helper.py` is found:

```bash
cd ~/projects/unitares-governance-plugin
# Simulate the path resolution
for candidate in scripts/onboard_helper.py scripts/client/onboard_helper.py; do
  [[ -f "$candidate" ]] && echo "FOUND: $candidate" && break
done
```

Expected: `FOUND: scripts/onboard_helper.py`

- [ ] **Step 4: Commit**

```bash
cd ~/projects/unitares-governance-plugin
git add hooks/session-start scripts/onboard_helper.py
git commit -m "sync: session-start hook with slot resolution and onboard_helper"
```

---

### Task 3: Sync post-edit hook with main repo's evolved version

The main repo's `hooks/post-edit` added:
- Multi-layout path resolution for session_cache.py
- Watcher fan-out (triggers workspace-local watcher if present)

**Files:**
- Overwrite: `hooks/post-edit` — copy from `/Users/cirwel/projects/unitares/hooks/post-edit`

- [ ] **Step 1: Copy the evolved post-edit hook**

```bash
cp /Users/cirwel/projects/unitares/hooks/post-edit \
   ~/projects/unitares-governance-plugin/hooks/post-edit
```

- [ ] **Step 2: Verify it's executable**

```bash
chmod +x ~/projects/unitares-governance-plugin/hooks/post-edit
```

- [ ] **Step 3: Commit**

```bash
cd ~/projects/unitares-governance-plugin
git add hooks/post-edit
git commit -m "sync: post-edit hook with watcher fan-out and multi-layout resolution"
```

---

### Task 4: Add umbrella skill

The main repo added `skills/unitares-governance/SKILL.md` as a backward-compatible entrypoint. The standalone plugin doesn't have it.

**Files:**
- Create: `skills/unitares-governance/SKILL.md` — copy from main repo

- [ ] **Step 1: Copy the umbrella skill**

```bash
mkdir -p ~/projects/unitares-governance-plugin/skills/unitares-governance
cp /Users/cirwel/projects/unitares/skills/unitares-governance/SKILL.md \
   ~/projects/unitares-governance-plugin/skills/unitares-governance/SKILL.md
```

- [ ] **Step 2: Update source_files paths in the skill frontmatter**

The main repo's skill references `unitares/src/...` paths. In the plugin these should reference the governance server generically since the plugin doesn't contain server source.

Edit `skills/unitares-governance/SKILL.md` frontmatter `source_files` to remove repo-specific paths (they're not in the plugin repo).

- [ ] **Step 3: Commit**

```bash
cd ~/projects/unitares-governance-plugin
git add skills/unitares-governance/SKILL.md
git commit -m "add umbrella governance skill for backward compatibility"
```

---

### Task 5: Update global stop-checkin hook to use plugin path

The current `~/.claude/hooks/stop-checkin.sh` hardcodes:
```
SESSION_HELPER="/Users/cirwel/projects/unitares/scripts/client/session_cache.py"
```

This should point to the plugin's copy instead.

**Files:**
- Modify: `/Users/cirwel/.claude/hooks/stop-checkin.sh:11` — update SESSION_HELPER path

- [ ] **Step 1: Update the hardcoded path**

Change line 11 of `/Users/cirwel/.claude/hooks/stop-checkin.sh` from:
```bash
SESSION_HELPER="/Users/cirwel/projects/unitares/scripts/client/session_cache.py"
```
to:
```bash
SESSION_HELPER="/Users/cirwel/projects/unitares-governance-plugin/scripts/session_cache.py"
```

- [ ] **Step 2: Verify the file exists at new path**

```bash
ls -la /Users/cirwel/projects/unitares-governance-plugin/scripts/session_cache.py
```

Expected: file exists, readable

---

### Task 6: Update plugin registration in settings.json

The current `enabledPlugins` key is `"unitares-governance@unitares-governance": true`. Need to verify the plugin is loaded from the standalone repo, not the main repo.

**Files:**
- Possibly modify: `/Users/cirwel/.claude/settings.json` — update plugin path if needed

- [ ] **Step 1: Check where Claude Code resolves the plugin**

Claude Code resolves plugins by looking for `.claude-plugin/plugin.json` in enabled plugin directories. Check if there's a plugin registry that maps `unitares-governance@unitares-governance` to a path:

```bash
# Check if there's a plugin config mapping
grep -r "unitares-governance" ~/.claude/ --include="*.json" -l 2>/dev/null
cat ~/.claude/plugins.json 2>/dev/null || echo "no plugins.json"
```

- [ ] **Step 2: If the main repo's `.claude-plugin/` is being used, update the plugin path**

The plugin may need re-registration. If Claude Code uses the working directory's `.claude-plugin/`, then when working in the unitares project it loads from there — but that means the plugin doesn't load in other projects.

For global availability, the plugin should be installable as a Claude Code plugin by URL:
```bash
claude plugin add CIRWEL/unitares-governance-plugin
```

Or confirm the current mechanism loads it correctly.

- [ ] **Step 3: Remove `.claude-plugin/` and `.codex-plugin/` from the main unitares repo**

Once the standalone plugin is the source of truth, the main repo should not also declare itself as a plugin:

```bash
cd ~/projects/unitares
git rm -r .claude-plugin .codex-plugin
git commit -m "remove plugin manifests — extracted to CIRWEL/unitares-governance-plugin"
```

---

### Task 7: Update README and metadata

**Files:**
- Modify: `README.md` — update clone URL, add install instructions
- Modify: `.claude-plugin/plugin.json` — bump version to 0.2.0
- Modify: `.claude-plugin/marketplace.json` — update repo URL
- Modify: `.codex-plugin/plugin.json` — bump version, update URL

- [ ] **Step 1: Update README repo references**

Replace all occurrences of `CIRWEL/unitares-governance` with `CIRWEL/unitares-governance-plugin` in README.md.

- [ ] **Step 2: Bump plugin version in `.claude-plugin/plugin.json`**

Bump version from `0.1.0` to `0.2.0` to reflect the sync.

- [ ] **Step 3: Bump `.codex-plugin/plugin.json` version**

Update from `0.2.2` to `0.3.0`.

- [ ] **Step 4: Update marketplace.json repo URL**

Update the `repository` field in `.claude-plugin/marketplace.json`.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/unitares-governance-plugin
git add README.md .claude-plugin/ .codex-plugin/
git commit -m "update repo name, bump versions, refresh metadata"
```

---

### Task 8: Clean up and push

- [ ] **Step 1: Remove stale files that don't belong in the plugin**

Check for any files that reference server-side code or aren't needed:
```bash
cd ~/projects/unitares-governance-plugin
# The detect-corrections.py and check-skill-freshness.sh are client utilities — keep them
# config/defaults.env is needed — keep it
```

- [ ] **Step 2: Run a smoke test**

Simulate the session-start hook to verify it can reach the governance server:
```bash
cd /tmp
echo '{"session_id": "test-smoke"}' | /Users/cirwel/projects/unitares-governance-plugin/hooks/session-start
```

Expected: JSON output with `additional_context` containing EISV values (if server is running) or OFFLINE message.

- [ ] **Step 3: Push to GitHub**

```bash
cd ~/projects/unitares-governance-plugin
git push origin main
```

- [ ] **Step 4: Update memory**

Update the MEMORY.md project paths entry to include the plugin repo location.
