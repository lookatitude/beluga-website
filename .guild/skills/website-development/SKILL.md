---
derived_from_template: guild.skill_template.v1
name: website-development
description: "Site-mechanics knowledge for the Beluga AI website (Astro 7, Starlight 0.42, React 19, Tailwind v4, Vite 8, Node 22.23.4+) — directory layout, which Starlight overrides are wired in astro.config.mjs, config JSON files, path aliases, the compressHTML: false gotcha, the docs-bundle contract, and the CI-parity checks. Pulled by the frontend specialist. TRIGGER for \"add or change an Astro component\", \"fix a Starlight override\", \"where does the sidebar config live\", \"why are words glued together after the Astro upgrade\", \"the site build fails\", \"add a marketing page under src/pages\". DO NOT TRIGGER for: writing MDX body copy, blog posts, tutorials or guides (website-content-standards via content-writer); meta and structured data (seo skills); voice review (voice-steward-content-review); release diff reports (docs-sync-content-gap-report); framework Go code."
when_to_use: "The frontend specialist pulls this skill for any lane that touches src/components, src/layouts, src/pages, src/styles, src/lib, src/config, astro.config.mjs or package.json in the website repo."
type: specialist
---

# website-development

Evidence is a green `yarn build` plus a clean `python3 scripts/check-links.py dist`, with the breakpoints and a11y checks you ran listed.

## What you do

**Read the full reference first:** `.claude/skills/website-development/SKILL.md`. It is the single long-form copy of this repo's site-development patterns (stack, project tree, component/styling rules, path aliases, override wiring, config files, docs-bundle rules, don'ts). Plain Claude Code loads it directly; Guild lanes load it through this pointer. Don't duplicate its body here.

Then apply these rules on every lane:

- Astro components by default; React 19 only where a `client:*` directive is needed.
- A new Starlight override is live only once registered under `starlight({ components: { … } })` in `astro.config.mjs`.
- Keep `compressHTML: false` in `astro.config.mjs`. Astro 7's compression drops whitespace before inline elements on hand-written `.astro` pages.
- Use `@/` or `~/` aliases (both map to `src/`).
- Test at 320 / 768 / 1024 / 1440 px; WCAG AA.
- yarn, never npm; Node 22.23.4 or later.

## Output shape

1. The code diff.
2. Evidence block: `yarn install --frozen-lockfile && yarn build` result, `python3 scripts/check-links.py dist` result, breakpoints checked, a11y notes (tab order, contrast, semantics), notable `dist/` size change.
3. `followups:` for copy problems (content-writer), meta problems (seo), workflow changes (coordinator).

## Anti-patterns

- Regenerating godocs locally instead of using `scripts/fetch-docs-bundle.sh`.
- Committing spliced project-report bodies, `public/godoc/`, `dist/`.
- Editing body copy under `src/content/docs/**`.
- Turning `compressHTML` back on to "fix" a size regression.
- Claiming CI-green for a step you didn't run.

## Handoff

Return the evidence block to the invoking `frontend` specialist for its `guild.handoff.v2` receipt. This skill does not dispatch.
