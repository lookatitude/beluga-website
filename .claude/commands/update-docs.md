---
name: update-docs
description: Fetch the latest framework docs bundle and run a content-needs analysis against the current website content.
---

Update docs from the latest framework release.

## Workflow

### Step 1 — Fetch the docs bundle
Run `scripts/fetch-docs-bundle.sh` (no arguments = latest release, or pass a specific tag). This pulls `docs-bundle.tar.gz` from the framework release, installs godoc HTML into `public/godoc/`, and splices raw report bodies into the project-report stubs.

If the script soft-fails (no release found, asset missing), report the warning and stop — there's nothing new to sync.

### Step 2 — Detect changes
`@agent-docs-sync` runs its detection workflow:
- Diffs the CHANGELOG between previous and current release
- Compares godoc structure (if previous build is available)
- Cross-references existing website content for gaps

### Step 3 — Report
The docs-sync agent produces a structured content-needs report:
- New content needed (blog posts, tutorials, guides)
- Existing content to update (stale references, deprecated APIs)
- No-action items (bug fixes, chores with no content impact)
- Unable-to-determine items (need manual review)

Report is saved to `src/content/docs/blog/_sync-reports/<tag>.md` and printed to stdout.

### Step 4 — Next steps (manual)
Review the report. For each actionable item:
- Blog post → run `/blog <topic>`
- Tutorial → run `/tutorial <feature>`
- Guide → run `/guide <task>`
- Release announcement → run `/announce-release <tag>`
- Existing content update → edit the file directly or assign to `content-writer`

This command does NOT automatically create content — it detects what's needed and produces a checklist for human review.
