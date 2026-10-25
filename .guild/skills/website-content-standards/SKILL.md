---
derived_from_template: guild.skill_template.v1
name: website-content-standards
description: "House rules for content files in the Beluga AI website — content types and their output paths under src/content/docs/, required frontmatter, the leading-underscore filename rule for draft-only files (social companions, sync reports), Go snippet rules (full github.com/lookatitude/beluga-ai/v2 imports, explicit errors, registry construction) and how to run scripts/snippets/check.sh like the advisory CI job. Pulled by content-writer, marketing and seo. TRIGGER for \"where does a tutorial go\", \"save the social companions\", \"does this Go snippet meet our rules\", \"run the snippet check\", \"why did my _social file publish as a page\", \"what frontmatter does a blog post need\". DO NOT TRIGGER for: site components, overrides or astro.config.mjs (website-development); voice and tone (voice-steward-content-review); release diff detection (docs-sync-content-gap-report); Notion mirroring; framework Go code."
when_to_use: "Pulled by content-writer, marketing and seo whenever a lane creates or edits a file under src/content/docs/ or includes Go code in content."
type: specialist
---

# website-content-standards

Evidence is the file at the right path with valid frontmatter, plus the snippet-check summary when the content has Go code.

## What you do

**Paths by content type**

| Type | Path |
|---|---|
| Blog post | `src/content/docs/blog/<slug>.mdx` |
| Release announcement post | `src/content/docs/blog/<tag>-release.mdx` |
| Social companion (draft only) | `src/content/docs/blog/_social/_<slug>-{x,linkedin,bluesky}.md` |
| Tutorial / substantial how-to | `src/content/docs/docs/guides/<slug>.mdx` |
| Short recipe | `src/content/docs/docs/recipes/<slug>.mdx` |
| Release note | `src/content/docs/releases/<tag>.mdx` (directory not created yet; adds a new route) |
| docs-sync report (draft only) | `src/content/docs/blog/_sync-reports/_<tag>.md` |

**Underscore rule (W-011).** Starlight's docs loader skips only files whose *filename* starts with `_`. A `_social/` or `_sync-reports/` directory does not protect its files. Every draft-only file needs the `_` on the filename.

**Frontmatter.** `title` (required by the docs schema; ≤ 60 chars for SEO) and `description` (≤ 155 chars). Match an existing file of the same type for the rest.

**Go snippets.**
- Full imports: `github.com/lookatitude/beluga-ai/v2/...`. The PR workflow rejects pre-v2 module paths.
- Explicit `if err != nil`; never `_` for an error.
- Registry construction (`llm.New("anthropic", cfg)`), not struct literals of providers.
- API keys via `os.Getenv(...)`.
- Check: `scripts/snippets/check.sh <framework-checkout> <out-dir>` (Go 1.26+, framework at the released tag). It lints every block for nonexistent packages/symbols, then compiles blocks with a `package` clause. CI runs it as the advisory `Go snippets` job. Complete programs must compile; partial snippets may fail compile but must pass the lint.

**Never** commit the spliced bodies of `src/content/docs/docs/contributing/project-reports/{changelog,security,code-quality}.md`, and never write about unreleased features.

## Output shape

The content file(s) at the paths above, plus an evidence block: snippet-check summary (lint + compile counts), `yarn build` result, and sources cited per technical claim.

## Anti-patterns

- `_social/<slug>-x.md` without the file prefix.
- Abbreviated imports or `_` error returns "for brevity".
- Treating the advisory snippet job as permission to ship a complete program that doesn't compile.
- Hardcoded provider counts or benchmarks without a source file.

## Handoff

Return the evidence block to the invoking specialist. Missing companion examples or framework docs gaps go to `followups:` for the coordinator to file. This skill does not dispatch.
