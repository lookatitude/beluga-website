# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Public documentation and marketing site for the Beluga AI framework. Astro + Starlight + React + Tailwind v4. Deployed via Netlify.

This repo was split out of `beluga-ai` (framework) in 2026 — history was preserved with `git filter-repo --subdirectory-filter docs/website`, so every commit here originated in the framework repo's `docs/website/` tree.

## Common commands

```bash
yarn install          # install deps (yarn, not npm — yarn.lock is the source of truth)
yarn dev              # astro dev server
yarn build            # production build → dist/
yarn preview          # serve the built dist/ locally
```

Node 20+ (matches `netlify.toml`).

## Architecture notes

- **Astro config**: `astro.config.mjs` wires Starlight, React, sitemap, view transitions, a custom `rehype-mermaid` pipeline, and Tailwind via `@tailwindcss/vite`. Site config / social / locales / sidebar live in `src/config/*.json` and are imported at build time.
- **Content**: `src/content/` (managed by Astro content collections, schema in `src/content.config.ts`).
- **Overrides**: `src/components/override-components/` replaces specific Starlight internals (Search, Sidebar, TOC, ThemeSwitch). Touch carefully — upstream Starlight updates may require refreshing these.
- **Docs bundle from framework**: `scripts/fetch-docs-bundle.sh` downloads `docs-bundle.tar.gz` from the `lookatitude/beluga-ai` repo's latest (or a specific) release and splices it into the tree:
  - `public/godoc/` — pre-generated Go API reference HTML. Gitignored; regenerated each build.
  - `src/content/docs/docs/contributing/project-reports/{changelog,security,code-quality}.md` — these stubs are **tracked** (they own the Starlight frontmatter), and the fetch script rewrites only their body from the raw CHANGELOG/SECURITY/CODE-QUALITY reports in the bundle. Expect local `git status` noise after a build.
  - Requires `gh` CLI authenticated with read access to `lookatitude/beluga-ai`.
  - Locally, running without the fetch is fine — godoc pages will 404 and report pages will show the placeholder body.
- **Mermaid**: diagrams are rendered at build time via `src/lib/rehype-mermaid.mjs`.

## Deploy

Netlify builds `main` using `netlify.toml` (`yarn build`, publishes `dist/`). The godoc-fetch step runs in a GitHub Action before Netlify picks up the build — see `.github/workflows/`.

## Related repos

- `beluga-ai` (framework) — source of godoc artifact. API changes that require doc updates usually need coordinated PRs.
- `beluga-examples` — linked from the docs; keep cross-repo links in mind when renaming pages.
