---
description: Website content and design rules. Applies when editing anything in this repo.
globs: "**/*"
alwaysApply: true
---

# Website Rules (Astro + Starlight)

## Stack

- Astro 7 + Starlight 0.42 (see `AGENTS.md` for the full override list and architecture notes)
- React 19 for interactive components
- Tailwind v4 via `@tailwindcss/vite`
- MDX for documentation pages
- Node 22.23.4 or later (`package.json` `engines`; `.github/workflows/{pr,deploy}.yml` pin `NODE_VERSION: "22.23.4"`). Use yarn, not npm.
- `astro.config.mjs` sets `compressHTML: false` on purpose: Astro 7's compression drops the whitespace before inline elements on hand-written `.astro` pages and glues words together. Don't turn it back on.
- Go API reference comes from the pre-built `docs-bundle.tar.gz` attached to each framework release — never run gomarkdoc/pkgsite from this repo. See `scripts/fetch-docs-bundle.sh` and `AGENTS.md`.

## Content rules

- All Go code examples in blog posts, tutorials, and guides must compile. Verify with `go build` in a throwaway directory, or run `scripts/snippets/check.sh <framework-checkout> <out-dir>`, before committing.
- Examples include full imports (`github.com/lookatitude/beluga-ai/v2/...`), never abbreviated or assumed. The PR workflow rejects pre-v2 module imports.
- Errors in examples must be handled explicitly — never `_` for error returns.
- No placeholder Lorem ipsum — real content only.
- Link to runnable examples (`lookatitude/beluga-examples`) whenever a tutorial or guide would benefit from a working companion.
- Draft-only files under `src/content/docs/` (social companions, sync reports) need a leading `_` on the **filename**, not just the directory; Starlight's loader only skips underscore-prefixed files (workspace correction W-011).
- Never commit the spliced bodies of `src/content/docs/docs/contributing/project-reports/{changelog,security,code-quality}.md`; they regenerate on every build.

## Design rules

- Responsive at 320px / 768px / 1024px / 1440px. Test at all four breakpoints.
- WCAG AA accessibility — color contrast, keyboard navigation, semantic HTML, alt text.
- Reuse existing component patterns under `src/components/` — don't invent new primitives without a documented reason.
- Starlight overrides live in `src/components/override-components/` and are wired via `astro.config.mjs`. Only overrides listed in `astro.config.mjs` are active — see `AGENTS.md` for the full list and the "exists-but-unwired" gotcha.
- Design tokens, typography, and color come from the global styles under `src/styles/`. Match the existing type scale and spacing.

## Before editing

- Read `AGENTS.md` for the deploy model, three triggers, override list, and `fetch-docs-bundle.sh` failure modes. (`CLAUDE.md` only imports `AGENTS.md`.)
- Read `.guild/wiki/index.md` — currently a scoped stub, but it tells you what knowledge lives where (website vs framework vs workspace).
- Explore the current `src/` tree — match existing conventions before adding anything new.

## Before handing back (CI parity)

`.github/workflows/pr.yml` is what CI runs on every PR. Match it locally:

1. `yarn install --frozen-lockfile && yarn build` (blocking).
2. `python3 scripts/check-links.py dist` (blocking; fails on any broken internal link).
3. For content with Go code: `scripts/snippets/check.sh <framework-checkout> <out-dir>`. CI runs this as an **advisory** job (`Go snippets (advisory)`) against the latest framework release with `GO_VERSION: "1.26.x"` and `GOTOOLCHAIN=local`. It reports in the run summary and never fails the PR, because intentionally partial snippets don't compile. Complete programs must still compile, and every snippet must pass the API lint.

Never claim a step passed if you could not run it locally; say which step you skipped and why.

## Branches, review, and who pushes

- Never commit to `main`. Work on a `<type>/<short-desc>` branch (`fix`, `feat`, `refactor`, `docs`, `chore`); verify `git branch --show-current` first. The `/announce-release` branch name `docs/announce-<tag>` is fixed because its dedupe check looks for it.
- The main session is the **coordinator**. Teammates and subagents commit locally and hand back. Only the coordinator pushes, opens or merges PRs, posts PR comments, files GitHub issues, and writes to Linear/Sonar/Notion (see the workspace `AGENTS.md` § "Teammate dispatch").
- **Codex is the adversarial reviewer.** Before a PR opens, the coordinator runs `/codex:adversarial-review` on the branch. Guild runs do the same through `.guild/settings.json` (`review: cross`, `adversarial_review_provider: codex-plugin`). If Codex is unavailable, record that in the PR description; a same-family review is not an equivalent pass.
- `voice-steward` is advisory on every content PR; it returns a comment body and the coordinator posts it.

## Anti-rationalization

| Excuse | Counter |
|---|---|
| "The example is obvious, no imports needed" | Full imports every time. Copy-paste ready. |
| "I'll test responsive later" | Test at all four breakpoints now. |
| "This new component is just for this page" | Reuse existing patterns unless there's a documented reason to add a new primitive. |
| "gomarkdoc/pkgsite would be faster than the bundle" | No. The bundle is the contract with the framework repo — never regenerate godocs locally. |
| "The snippet job is advisory, so compile failures don't matter" | It is advisory only because partial snippets are expected to fail. A complete program that doesn't compile is a bug. |
| "I'll just push the branch myself, it's faster" | Teammates hand back. The coordinator pushes after the Codex review. |
