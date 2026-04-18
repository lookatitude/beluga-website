---
name: announce-release
description: Draft a release announcement from the CHANGELOG and docs bundle when a new framework version ships. Coordinates content-writer (blog), marketeer (social), and seo-meta (tags).
---

Announce release: $ARGUMENTS

$ARGUMENTS should be a framework release tag (e.g., `v2.8.5`). If omitted, uses the latest framework release.

## Workflow

### Step 1 — Fetch the docs bundle (if not already current)
Run `scripts/fetch-docs-bundle.sh $ARGUMENTS` to ensure the latest docs bundle is installed. If the bundle is already current for this tag, skip.

### Step 2 — Detect changes
Run `/update-docs` (invokes `@agent-docs-sync`). Review the content-needs report to understand the scope of changes in this release.

### Step 3 — Draft blog post
`@agent-content-writer` writes a release announcement blog post:
- Title: "Beluga AI $ARGUMENTS: <headline feature>"
- 800–1200 words
- Structure: what shipped → highlights (2–3 features with code) → breaking changes (if any) → migration steps (if any) → what's next
- Link to the full CHANGELOG on the site
- Link to runnable examples in `lookatitude/beluga-examples` where they exist
- Source: CHANGELOG body at `src/content/docs/docs/contributing/project-reports/changelog.md`
- Output: `src/content/docs/blog/<tag>-release.mdx`

### Step 4 — Draft companion social posts
`@agent-marketeer` writes short-form posts:
- X thread: 5–7 posts, hook first
- LinkedIn: 150–200 words
- Bluesky: 1–3 posts
- All link to the blog post
- Output: `src/content/docs/blog/_social/<tag>-*.md`

### Step 5 — SEO check
`@agent-seo-meta` reviews the new blog post's frontmatter: title ≤60 chars, description ≤155 chars, OG image fields present, structured data ready for `Article` schema.

### Step 6 — Landing page refresh
If any change in the release is user-visible enough to warrant a landing page update (new provider category, new deployment mode, new major feature), `@agent-developer-web` proposes edits to the relevant marketing page or `src/content/docs/docs/start/` page. Keep edits minimal — reuse existing component patterns.

### Step 6a — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward` on the complete announcement bundle (blog + social + any landing-page edits). Advisory comment on tone / voice / cross-content consistency. Do not block — release announcements are time-sensitive; proceed to PR regardless of voice-steward findings, but capture suggestions inline.

### Step 7 — Output and PR
Everything lands in a single PR against `main` per branch discipline:
- `src/content/docs/blog/<tag>-release.mdx`
- `src/content/docs/blog/_social/<tag>-*.md`
- Any landing-page or docs-start edits
- Frontmatter fixes from SEO check

Do NOT commit directly to main. Do NOT split into multiple PRs — the release announcement is one coordinated unit.
