---
type: concept
title: "Architecture map (stub)"
description: "Cheap-scan architecture stub for website. Confidence-tagged candidate; the deep knowledge graph is deferred."
owner: orchestrator
confidence: medium
trust_tier: synthesized
status: candidate
importance: low
source_refs: [codebase-map]
created_at: 2026-10-25
updated_at: 2026-10-25
expires_at: null
supersedes: null
sensitivity: internal
generated_from_commit: 1cebeb9c09add9838b901416af193d09f2b60cb7
recall_importance: 3
---
# Architecture map (stub)

Built from the cheap scan (codebase map, a derived cache outside the repo; 556 files at
commit `1cebeb9c`; languages: css, javascript, json, markdown, shell, typescript, yaml; frameworks: react) plus this repo's
`CLAUDE.md`. Candidate page: every line carries a confidence tag. The deep knowledge
graph and onboarding tour were **not** built at init; run `/guild:learn` to build them.

## What this repo is

- **[high]** `beluga-website`: the public docs and marketing site, Astro 5 + Starlight + React 19 + Tailwind v4, deployed to GitHub Pages at `beluga-ai.org`. The communication layer of the Beluga project. Source: `CLAUDE.md` §What this is.
- **[high]** Split out of the framework repo with `git filter-repo --subdirectory-filter docs/website`; history preserved. Source: `CLAUDE.md`.

## Structure

- **[high]** `astro.config.mjs` wires Starlight, React, sitemap, view transitions, a custom `rehype-mermaid` plugin, Tailwind via `@tailwindcss/vite`, and permanent redirects for the IA cutover.
- **[high]** Content collections (`src/content.config.ts`): `docs` (Starlight pages), `i18n` (en/fr UI strings), `ctaSection` (marketing CTA blocks).
- **[high]** Starlight overrides live in `src/components/override-components/`; marketing primitives in `src/components/marketing/`; pages outside the docs tree in `src/pages/`.
- **[high]** Build-time helpers in `src/lib/`: Mermaid rendering, OG images (satori + resvg), provider catalog parsed from the framework.

## Build and deploy

- **[high]** `yarn` (not npm), Node 22. `yarn build` → `dist/`.
- **[high]** `.github/workflows/deploy.yml` deploys on push to `main`, on `repository_dispatch: framework-release`, and on manual dispatch. `scripts/fetch-docs-bundle.sh` splices the framework's `docs-bundle.tar.gz` (godoc HTML + reports) and soft-fails when it is missing.
- **[medium]** A scheduled remote agent drafts release announcements every 4h (`/announce-release`). Its definition lives outside this repo.

## Modules by size (from the scan)

| Path | Files |
|---|---|
| `src` | 522 |
| `.claude` | 17 |
| `public` | 4 |
| `.wiki` | 3 |
| `.sitepins` | 2 |
| `.github` | 1 |
| `.yarnrc.yml` | 1 |
| `CLAUDE.md` | 1 |
| `README.md` | 1 |
| `astro.config.mjs` | 1 |
| `package.json` | 1 |
| `scripts` | 1 |

## Knowledge that stays where it is

- **[high]** This repo's own `.wiki/` (notably `.wiki/style-guide.md`, enforced by `voice-steward`) remains the source for content agents. It was not migrated into `.guild/wiki/` at init.
