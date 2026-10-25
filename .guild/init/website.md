---
schema_version: guild.init_record.v1
slug: website
run_id: run-20261025-043828-init
mode: brownfield
repo_kind: regular
created_at: 2026-10-25
generated_from_commit: 1cebeb9c09add9838b901416af193d09f2b60cb7
guild_version: 3.1.0
storage_layout_version: 2
---
# Init record: website

## Detection
- `workspace-detect`: **regular** (no immediate child with `.git/` or `.guild/`).
  Registered as a sub-guild of the Beluga workspace (`../.guild/workspace.json`).

## Scan (cheap tier = Init-DONE)
- `learn-scan` → codebase map (derived cache under `~/.cache/guild/roots/`, not committed; rebuild with `/guild:learn map`): 556 files; languages css, javascript, json, markdown, shell, typescript, yaml.
- `wiki/concepts/architecture-map.md`: confidence-tagged stub, status candidate.
  Grounded in the scan plus `CLAUDE.md`.
- **Deferred, not produced:** `knowledge-graph.json`, `onboarding-tour.md`. Run
  `/guild:learn` to build them.

## Existing knowledge
- The legacy `.wiki/` was moved into `.guild/wiki/` on 2026-10-25 with its structure
  kept. Raw captures with sha256 live under `.guild/knowledge/sources/wiki-*/`; this
  repo's agents and commands now read `.guild/wiki/`.

## Reviews
- G-init cross-host review: **skipped** by policy (`review: local`).
