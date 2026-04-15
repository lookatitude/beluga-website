# Beluga Website Wiki

**Scope: website-local.** This wiki holds knowledge specific to the documentation and marketing site — Starlight override conventions, content voice and style, design system tokens, SEO/meta patterns, and website-local corrections. It does **not** hold framework patterns (those are in `../framework/.wiki/`) or cross-repo coordination material (that is in the workspace wiki at `../.wiki/`, visible when the repo is checked out inside the multi-repo Beluga workspace).

## What lives here (and when)

| Topic | Status |
|---|---|
| Starlight override conventions — which components are wired, how they compose | *pending — Phase 3* |
| Content voice, tone, and style guide | *pending — Phase 3* |
| Design system tokens, color palette, type scale | *pending — Phase 3* |
| Blog post / tutorial / guide structural templates | *pending — Phase 3* |
| SEO / OG image / meta-tag conventions | *pending — Phase 3* |
| Website-local corrections (e.g. upstream Starlight quirks, build issues) | *pending — on-demand* |

## Where everything else lives

- **Framework Go patterns, APIs, architecture** → `../framework/.wiki/`
- **Release flow, dispatch chains, cross-repo incidents** → workspace `../.wiki/` *(visible inside the multi-repo workspace)*
- **Runnable code examples** → `../examples/.wiki/` *(pending — Phase 5)*

## Populate this wiki when

- A Starlight override has a non-obvious constraint that would confuse a future agent.
- Content voice has been decided and should be enforced across all new posts.
- A design token has a specific meaning or must not drift from the system.
- A cross-repo incident had a website-specific root cause (record here; reference from workspace incidents log).
