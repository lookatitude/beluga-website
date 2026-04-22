# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Public documentation and marketing site for the Beluga AI framework. Astro 5 + Starlight + React 19 + Tailwind v4. Deployed to GitHub Pages at `https://beluga-ai.org` (custom domain set via `public/CNAME`).

This repo was split out of `beluga-ai` (framework) in 2026 — history was preserved with `git filter-repo --subdirectory-filter docs/website`, so every commit here originated in the framework repo's `docs/website/` tree.

## Project scope

This repo owns the **communication layer** of the Beluga project: blog posts, tutorials, guides, marketing pages, and the docs site that wraps framework godocs and reports. It does **not** own framework code, Go patterns, or runnable example programs — those live in `beluga-ai` (framework) and `beluga-examples` (examples) respectively.

When working on cross-repo concerns (a release flow incident, coordinating a framework API change with content updates, shared branch discipline), consult the **workspace wiki** at `../.wiki/index.md` and the workspace `CLAUDE.md` at `../CLAUDE.md` — they are only visible when this repo is checked out inside the multi-repo Beluga workspace. Anything site-specific (Astro config, Starlight overrides, content voice, design system) stays here, in this repo's `.wiki/`.

## Wiki

`.wiki/` holds website-specific knowledge: Starlight override conventions, content voice/style, design-system tokens, and any website-local corrections. The authoritative content voice reference lives at `.wiki/style-guide.md` — read it before drafting any blog / tutorial / guide / announcement; the `voice-steward` agent enforces it on content PRs. `.wiki/index.md` is the meta-router; most Go-side knowledge still lives in the framework wiki.

## Voice steward and style guide (A2)

Every content PR invokes `voice-steward` (`.claude/agents/voice-steward.md`) as a pre-merge advisory gate — it reads `.wiki/style-guide.md` and posts a structured review comment covering tone, vocabulary, reading level, and cross-content consistency. It never blocks; the human approves the final merge. Update voice rules via normal PR to `.wiki/style-guide.md` (versioned in the file header). `voice-steward` is wired into `/tutorial`, `/guide`, `/blog`, and `/announce-release` automatically; it can also be invoked manually via `@agent-voice-steward` on any content diff.

## Claude 4.x and content agents

Content and marketing agents (see `.claude/agents/`) include a **Prompting baseline (Claude 4.x)**. Newer models can read as more direct; the `voice-steward` and long-form agents are instructed to **steer copy toward** `.wiki/style-guide.md` (warmth, clarity) without padding. If a draft is for **sensitive security** topics, favor defensive framing so content stays teachable and policy-safe. **Vision / screenshots** in content: high-res images can consume more tokens in current models—keep assets only as large as needed for the layout.

## Release announcement automation (C2)

A scheduled remote agent (`trig_01KTj6rE8aPCCKkyuM6JmDbc`, cron `0 */4 * * *`) polls the latest framework release every 4h. If no blog file under `src/content/docs/blog/` references the latest tag, the agent invokes `/announce-release <tag>` — which drafts blog + social companions + SEO meta + (optional) landing-page edits, runs voice-steward advisory, and opens a PR against `main`. **Human approves + merges.** Catch-up policy: announce only the latest missed tag; prior missed releases are covered via the changelog section in the blog body. Silent retry on failure (next 4h cycle). Manual `/announce-release <tag>` remains available.

## Common commands

```bash
yarn install          # install deps (yarn, not npm — yarn.lock is the source of truth)
yarn dev              # astro dev server
yarn build            # production build → dist/
yarn preview          # serve the built dist/ locally
```

Node 22 (matches `.github/workflows/deploy.yml`).

## Deploy

GitHub Pages, via `.github/workflows/deploy.yml`. Three triggers:

| Trigger | Use case | Docs bundle source |
|---|---|---|
| `push` to `main` | Content edits (blog posts, feature pages, config) | Latest `lookatitude/beluga-ai` release (looked up at build time) |
| `repository_dispatch: framework-release` | Sent automatically when a new framework release ships | Tag from `client_payload.tag` |
| `workflow_dispatch` (manual) | Rebuild against a pinned tag, or force a rebuild | `inputs.framework_tag` if set, else latest release |

All three converge on the same `build` job, so content-only deploys and framework-release deploys are interchangeable.

The `repository_dispatch` from the framework repo is sent by `framework/.github/workflows/release.yml`'s `dispatch-website` job using a PAT in the framework repo's `WEBSITE_DISPATCH_TOKEN` secret. If that token expires or loses access to `lookatitude/beluga-website`, framework releases will still publish but the website won't auto-rebuild — fix it by repasting a fresh PAT (fine-grained: `Contents: write` on this repo) into the framework repo secret.

## Architecture notes

- **Astro config** (`astro.config.mjs`) wires Starlight, React, sitemap, view transitions (`astro-vtbot`), a custom `rehype-mermaid` markdown plugin, Tailwind via `@tailwindcss/vite`, and a large block of permanent redirects for the IA cutover. Site config / social / locales / menu (en+fr) / sidebar / theme live in `src/config/*.json` and are imported at build time.
- **Content collections** (`src/content.config.ts`):
  - `docs` — Starlight docs pages.
  - `i18n` — Starlight UI translations (en/fr).
  - `ctaSection` — marketing CTA blocks under `src/content/sections/`, used by marketing pages.
- **Starlight overrides** (`src/components/override-components/`) replace Starlight internals. The set wired in `astro.config.mjs` is: `Head`, `Search`, `Header`, `Hero`, `PageFrame`, `PageSidebar`, `TwoColumnContent`, `ContentPanel`, `Pagination`, `Sidebar`. Other `.astro` files in the same directory exist but are not currently wired — adding a new override means registering it in `astro.config.mjs`. Touch carefully — upstream Starlight updates may require refreshing these.
- **Marketing layer** (`src/components/marketing/`) holds the marketing-page primitives (`MarketingHeader`, `MarketingFooter`, `Hero`, `CTA`, `Section`, etc.) used by `src/pages/` outside the Starlight docs tree.
- **Mermaid** diagrams are rendered at build time via `src/lib/rehype-mermaid.mjs`.
- **OG images** are generated via `src/lib/og-image.ts` (satori + resvg) and emitted under `public/og/`.
- **Provider catalog** (`src/lib/provider-catalog.ts`) parses the framework's provider list for marketing/docs use.
- **Disabled 404** — Starlight's built-in 404 is disabled (`disable404Route: true`); the marketing-layout `/404` lives at `src/pages/404.astro` so error pages keep the same chrome.

## Docs bundle from framework

`scripts/fetch-docs-bundle.sh` downloads `docs-bundle.tar.gz` from a `lookatitude/beluga-ai` release and splices it into the tree:

- `public/godoc/` — pre-generated Go API reference HTML. Gitignored; regenerated each build.
- `src/content/docs/docs/contributing/project-reports/{changelog,security,code-quality}.md` — these stubs are **tracked** (they own the Starlight frontmatter), and the fetch script rewrites only their body from the raw report files in the bundle. Expect local `git status` noise after a build.

Requirements: `gh` CLI authenticated with read access to `lookatitude/beluga-ai`; `awk`, `tar`, `sha256sum`.

The script defaults to the latest release; pass a tag to pin (`scripts/fetch-docs-bundle.sh v2.8.5`).

**Failure mode worth knowing:** the script runs with `set -euo pipefail`. If the latest framework release exists but is missing `docs-bundle.tar.gz` (e.g. a release where goreleaser succeeded but the docs-bundle job failed mid-flight), the script aborts and the whole website build fails — even for content-only changes. The remediation is to repair the framework release (re-run the failed `docs-bundle` job to attach the asset) or pin to the previous release manually via `workflow_dispatch` with `framework_tag`.

Locally, running without the fetch is fine — godoc pages will 404 and report pages will show the placeholder body.

## Related repos

- `beluga-ai` (framework) — source of the `docs-bundle.tar.gz` artifact and the `framework-release` dispatch. API changes that need doc updates usually need coordinated PRs.
- `beluga-examples` — linked from the docs; keep cross-repo links in mind when renaming pages.
