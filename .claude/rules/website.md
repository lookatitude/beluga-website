---
description: Website content and design rules. Applies when editing anything in this repo.
globs: "**/*"
alwaysApply: true
---

# Website Rules (Astro + Starlight)

## Stack

- Astro 5 + Starlight (see `CLAUDE.md` for the full override list and architecture notes)
- React 19 for interactive components
- Tailwind v4 via `@tailwindcss/vite`
- MDX for documentation pages
- Go API reference comes from the pre-built `docs-bundle.tar.gz` attached to each framework release — never run gomarkdoc/pkgsite from this repo. See `scripts/fetch-docs-bundle.sh` and `CLAUDE.md`.

## Content rules

- All Go code examples in blog posts, tutorials, and guides must compile. Verify with `go build` in a throwaway directory before committing.
- Examples include full imports (`github.com/lookatitude/beluga-ai/...`), never abbreviated or assumed.
- Errors in examples must be handled explicitly — never `_` for error returns.
- No placeholder Lorem ipsum — real content only.
- Link to runnable examples (`lookatitude/beluga-examples`) whenever a tutorial or guide would benefit from a working companion.

## Design rules

- Responsive at 320px / 768px / 1024px / 1440px. Test at all four breakpoints.
- WCAG AA accessibility — color contrast, keyboard navigation, semantic HTML, alt text.
- Reuse existing component patterns under `src/components/` — don't invent new primitives without a documented reason.
- Starlight overrides live in `src/components/override-components/` and are wired via `astro.config.mjs`. Only overrides listed in `astro.config.mjs` are active — see `CLAUDE.md` for the full list and the "exists-but-unwired" gotcha.
- Design tokens, typography, and color come from the global styles under `src/styles/`. Match the existing type scale and spacing.

## Before editing

- Read `CLAUDE.md` for the deploy model, three triggers, override list, and `fetch-docs-bundle.sh` failure modes.
- Read `.wiki/index.md` — currently a scoped stub, but it tells you what knowledge lives where (website vs framework vs workspace).
- Explore the current `src/` tree — match existing conventions before adding anything new.

## Anti-rationalization

| Excuse | Counter |
|---|---|
| "The example is obvious, no imports needed" | Full imports every time. Copy-paste ready. |
| "I'll test responsive later" | Test at all four breakpoints now. |
| "This new component is just for this page" | Reuse existing patterns unless there's a documented reason to add a new primitive. |
| "gomarkdoc/pkgsite would be faster than the bundle" | No. The bundle is the contract with the framework repo — never regenerate godocs locally. |
