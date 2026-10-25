---
name: blog
description: Write a technical blog post about a feature, release, or topic.
---

Write a blog post on: $ARGUMENTS

$ARGUMENTS may be a free-form topic OR a Linear sub-issue ID. If it matches `^LOO-\d+$`, run the Linear pre-flight (fetch sub-issue + parent + brief + merged framework PR; retry-twice fallback — see `/tutorial` for the full pattern). Otherwise skip to Step 1.

## Invocation notes

- **Voice:** Calibrate to `.guild/wiki/style-guide.md`. Current models can read terse by default; add warmth only where the style guide does, not as generic padding.
- **Security claims:** Use defensive phrasing for threat content; avoid exploit walkthrough tone that can trip refusals or read as offensive.

### 1b. Validate content-type label (A3)

After fetching the sub-issue, check its labels. If it has a `content:*` label, verify it's `content:blog`:

- Mismatch with `content:tutorial`, `content:guide`, `content:reference`, or `content:landing` → warn and suggest the corresponding command. The drafter is configured for blog structure and voice, not the other content types. User may choose to continue anyway.
- Missing `content:*` label (predates A3 or created via A1's simpler /plan-content) → proceed as generic blog post; do not block.
- Matching `content:blog` → proceed normally.

Use the same warning template as `/tutorial`:

```
Sub-issue <LOO-NN> is labeled content:<actual-type>, but you invoked /blog.
Content types have different templates and voice targets.

Did you mean to run /<actual-type> <LOO-NN>?

Proceed anyway? (no — stop and re-run; yes — continue as blog ignoring the label)
```

## Workflow

### Step 1 — Source material
Identify what you're writing from. Typically one of:
- A recent framework release (read the `CHANGELOG.md` body from the docs bundle, the release notes, the associated PRs in `lookatitude/beluga-ai`)
- A feature brief from the workspace (`../research/` when running inside the multi-repo workspace)
- An existing tutorial, guide, or recipe in `src/content/docs/docs/` that needs a short-form companion

If you need original research (competitive analysis, benchmarks, user surveys, community sentiment), STOP and file a research brief upward — the workspace researcher handles investigation. Do not try to do it here.

### Step 2 — Draft
`@agent-content-writer` writes the blog post:
- 800–1200 words
- Hook / problem / solution / code / takeaway structure
- Full compiling Go examples with full imports (`github.com/lookatitude/beluga-ai/v2/...`)
- Link to a runnable example in `lookatitude/beluga-examples` if one exists
- Cite the source material explicitly


### Step 3 — Technical sanity check
Cite the source material the post is based on (release tag, PR, brief). If any technical claim cannot be sourced, either cut it or (coordinator) file an issue in `lookatitude/beluga-ai` asking for review before publishing. Do NOT invent API details.

### Step 4 — Companion social posts
`@agent-marketeer` writes short-form companion posts (LinkedIn, X, Bluesky) that link to the blog. Save as separate files alongside the MDX — do not embed social copy in the blog itself.

### Step 4a — Code check and adversarial review (pre-merge)
Run the Go snippet check locally: `scripts/snippets/check.sh ../framework <out-dir>` (needs Go 1.26+ and a framework checkout at the released tag; same script as the advisory `Go snippets` job in `.github/workflows/pr.yml`). Complete programs must compile; partial snippets may fail the compile step but must pass the API lint (no nonexistent packages or symbols). Then, before the PR opens, the coordinator runs `/codex:adversarial-review` on the branch (Codex is the cross-family reviewer; if it is unavailable, say so in the PR description, and don't present a same-family review as an equivalent pass).

### Step 4b — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward`. It returns an advisory comment body (the coordinator posts it on the PR) on tone / vocabulary / reading level / cross-content consistency. Do not block — human approves final merge regardless of findings.

### Step 5 — Output
Save the draft to `src/content/docs/blog/<slug>.mdx` (current convention — may be formalized as its own Astro content collection later). Save companion social posts to `src/content/docs/blog/_social/_<slug>-{x,linkedin,bluesky}.md`. The leading `_` on each filename is required: starlight's docs loader uses the pattern `**/[^_]*.{md,mdx}`, which excludes filenames starting with `_` from the content collection. Without the prefix the social files fail the docs schema's `title: required` check at build time. Commit on a branch (never `main`); the coordinator pushes and opens the PR against `main`. Include `LOO-NN` in the PR title if a Linear sub-issue was used so Linear auto-links. `yarn build` and `python3 scripts/check-links.py dist` must pass locally first (they are the blocking PR checks).

## Coordinator handoff

This command runs in the coordinator (main session) when you invoke it directly. Subagents it dispatches (`content-writer`, `marketeer`, `seo-meta`, `voice-steward`, …) write files and return; they never push, open PRs, post comments or file issues. If you are yourself a teammate running this command for a coordinator, stop after the local commit on your branch and hand back the PR title, body, voice-steward review and any proposed issues; the coordinator runs `/codex:adversarial-review`, pushes, opens the PR and posts the comments.

