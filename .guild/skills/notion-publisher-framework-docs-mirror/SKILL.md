---
derived_from_template: guild.skill_template.v1
name: notion-publisher-framework-docs-mirror
description: "Per-file workflow for mirroring framework/docs/**/*.md into private Notion pages under \"Beluga AI · Framework Docs\" — look up .claude/state/notion-pages.json, update mapped pages only when content changed, create and map new pages, convert markdown to Notion blocks, stamp Last synced / Source / Source commit, preserve user comments. Pulled by notion-publisher. TRIGGER for \"publish the framework docs to Notion\", \"mirror framework/docs to Notion\", \"the architecture doc in Notion is stale\", \"why is framework/docs/packages missing from Notion\". DO NOT TRIGGER for: research briefs, the project dashboard or the \"Beluga AI · Research\" parent (workspace notion-syncer skills); editing framework docs; website pages; Linear updates."
when_to_use: "Pulled by the notion-publisher specialist when the coordinator runs /notion-publish or asks to mirror or diagnose one framework doc in Notion."
type: specialist
---

# notion-publisher-framework-docs-mirror

Evidence is the mapping file plus a per-file report: every source file ends mapped to a live Notion URL or listed as skipped with a reason.

## What you do

- Confirm `../framework/docs/` (or `framework/docs/` from the workspace root) exists; if not, report and stop.
- For each `framework/docs/**/*.md`, look up `.claude/state/notion-pages.json` → `pages["framework/docs/<path>"]`.
  - **Mapped:** fetch the page, diff, update only if changed.
  - **Unmapped:** search first for an existing unmapped page; else create under "Beluga AI · Framework Docs"; write the mapping (`title`, `notion_id`, `url`, `created`) immediately.
- Convert headings, code, tables and lists to Notion blocks.
- Set "Last synced" (UTC), "Source" (framework path), "Source commit" (SHA from the dispatch prompt; if absent, leave unchanged and report).
- On an MCP failure, log and continue with the next file.

## Output shape

1. Updated Notion pages.
2. Updated `.claude/state/notion-pages.json`.
3. Report: created (path → URL), updated (path → change summary), skipped (path → reason), failures (path → cause).

## Anti-patterns

- Recreating a page that already has a mapping.
- Deleting or archiving pages, or overwriting user comments, without explicit confirmation.
- Touching "Beluga AI · Research" or the dashboard.
- Skipping the mapping write for "just one page".

## Handoff

Return the report and mapping diff to the `notion-publisher` specialist for its `guild.handoff.v2` receipt (`status: partial` if any file failed). The coordinator commits the mapping file on a branch. This skill does not dispatch.
