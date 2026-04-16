---
name: notion-publish
description: Publish framework documentation to Notion as a third channel alongside the docs site.
---

Publish framework docs to Notion.

## Workflow

### Step 1 — Pre-check
Confirm `framework/docs/` is reachable (either `framework/docs/` from the workspace root or `../framework/docs/` from this repo). If not, skip gracefully and report.

### Step 2 — Publish
`@agent-notion-publisher` runs the framework docs sync (see the agent's Task section). The agent mirrors `framework/docs/` to Notion pages under the "Beluga AI · Framework Docs" parent.

### Step 3 — Report
- Pages created (with Notion URLs)
- Pages updated
- Pages skipped (with reason)
- Sync failures and causes

This command does NOT touch research briefs or the project tracking dashboard — those are workspace-level (see workspace `/notion-sync`).
