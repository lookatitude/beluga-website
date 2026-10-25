---
name: notion-publish
description: Publish framework documentation to Notion as a third channel alongside the docs site.
---

Publish framework docs to Notion.

## Workflow

### Step 1 — Pre-check
Confirm `framework/docs/` is reachable (either `framework/docs/` from the workspace root or `../framework/docs/` from this repo). If not, skip gracefully and report. Resolve the framework HEAD SHA (`git -C ../framework rev-parse HEAD`, or `git -C framework …` from the workspace root) and pass it to the agent; it has no Bash and uses the SHA for the "Source commit" property.

### Step 2 — Publish
`@agent-notion-publisher` runs the framework docs sync (see the agent's Task section). The agent mirrors `framework/docs/` to Notion pages under the "Beluga AI · Framework Docs" parent.

### Step 3 — Report
- Pages created (with Notion URLs)
- Pages updated
- Pages skipped (with reason)
- Sync failures and causes

This command does NOT touch research briefs or the project tracking dashboard — those are workspace-level (see workspace `/notion-sync`).

Notion is an outward channel, so run this command from the coordinator (main session) only, never inside a feature team. If `.claude/state/notion-pages.json` changed, commit it on a branch (never `main`) and open a PR from the coordinator.
