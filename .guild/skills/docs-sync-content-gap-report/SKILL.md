---
derived_from_template: guild.skill_template.v1
name: docs-sync-content-gap-report
description: "Detection workflow for what a Beluga framework release means for website content — determine previous and current tags, categorize CHANGELOG entries (feature, breaking change, provider, deprecation, fix, performance), diff the public/godoc/ package tree when a previous copy exists, grep existing blog, guides and recipes for affected APIs, and write a content-needs report with proposed issues. Pulled by docs-sync. TRIGGER for \"content-needs report for v2.14.0\", \"what does this release mean for the docs\", \"which guides mention the deprecated API\", \"is the site current with the latest release\", \"run the docs-sync workflow\". DO NOT TRIGGER for: writing the content that fills a gap (content-writer / marketing); debugging fetch-docs-bundle.sh or the deploy workflow; Notion publishing; release notes themselves (marketing)."
when_to_use: "Pulled by docs-sync after a docs bundle fetch for a new tag, for /update-docs, step 2 of /announce-release, or a manual freshness audit."
type: specialist
---

# docs-sync-content-gap-report

Evidence is a report where every item cites the CHANGELOG entry, godoc path or content file:line it came from.

## What you do

1. **Tags.** Current = the bundle just fetched; previous = one release back (`git -C ../framework tag --sort=-v:refname` or `gh release list --repo lookatitude/beluga-ai`).
2. **CHANGELOG.** Read `src/content/docs/docs/contributing/project-reports/changelog.md`; take entries between the two tags; categorize each.
3. **Godoc.** Compare package directories in `public/godoc/` against the previous copy if one was saved aside. Gitignored, so no git history; else write "godoc diff unavailable — manual review recommended".
4. **Cross-reference.** Grep `src/content/docs/` (blog, `docs/guides/`, `docs/recipes/`, `docs/start/`) for each affected package/API.
5. **Report** to `src/content/docs/blog/_sync-reports/_<tag>.md` (file `_` prefix, W-011) and stdout. Don't commit it unless asked.

## Output shape

```markdown
## Docs Sync Report — vX.Y.Z
### New content needed
- [ ] <type>: <topic> — source: <CHANGELOG entry>
### Existing content to update
- [ ] `<path>` — mentions <old API>; framework changed to <new API>
### No action needed
### Unable to determine
### Proposed issues (coordinator files)
```

Empty CHANGELOG range or soft-failed bundle → "no changes detected", exit cleanly.

## Anti-patterns

- Fixing "just one sentence" in a guide.
- Dropping small items; report everything and let the human prioritize.
- Inferring a change from a package name instead of reading the entry.
- Filing issues yourself.

## Handoff

Return the report path and one `followups:` entry per actionable item (owner: content-writer, marketing or coordinator) to the `docs-sync` specialist. This skill does not dispatch.
