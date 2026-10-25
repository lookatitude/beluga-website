---
title: "Beluga Website Wiki"
description: "Wiki router and catalog for this repo (legacy .wiki index, migrated)."
recall_importance: 2
---
# Beluga Website Wiki

> Migrated from `.wiki/index.md` on 2026-10-25 (Guild 3.x; structure kept). Verbatim original: `.guild/knowledge/sources/wiki-index/original.md` (sha256 `782a59ff16f8…`).

**Scope: website-local.** This wiki holds knowledge specific to the documentation and marketing site — Starlight override conventions, content voice and style, design system tokens, SEO/meta patterns, and website-local corrections. It does **not** hold framework patterns (those are in `../../../framework/.guild/wiki/`) or cross-repo coordination material (that is in the workspace wiki at `../../../.guild/wiki/`, visible when the repo is checked out inside the multi-repo Beluga workspace).

## What lives here (and when)

| Topic | Status |
|---|---|
| Starlight override conventions — which components are wired, how they compose | *pending — Phase 3* |
| Content voice, tone, and style guide | `style-guide.md` (A2) — enforced by `voice-steward` |
| Design system tokens, color palette, type scale | *pending* |
| Blog post / tutorial / guide structural templates | `style-guide.md` — content-type templates section |
| SEO / OG image / meta-tag conventions | owned by `seo-meta` agent (Phase 3) |
| Website-local corrections (e.g. upstream Starlight quirks, build issues) | `corrections.md` — append-only, on-demand |

## Where everything else lives

- **Framework Go patterns, APIs, architecture** → `../../../framework/.guild/wiki/`
- **Release flow, dispatch chains, cross-repo incidents** → workspace `../../../.guild/wiki/` *(visible inside the multi-repo workspace)*
- **Runnable code examples** → `../../../examples/.guild/wiki/`

## Populate this wiki when

- A Starlight override has a non-obvious constraint that would confuse a future agent.
- Content voice has been decided and should be enforced across all new posts.
- A design token has a specific meaning or must not drift from the system.
- A cross-repo incident had a website-specific root cause (record here; reference from workspace incidents log).

## Guild pages

- [Architecture map (stub)](concepts/architecture-map.md): cheap-scan, confidence-tagged map of this repo.
- [Glossary](glossary.md): Guild operating terms, plus project terms.
