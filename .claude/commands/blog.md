---
name: blog
description: Write a technical blog post about a feature, release, or topic.
---

Write a blog post on: $ARGUMENTS

$ARGUMENTS may be a free-form topic OR a Linear sub-issue ID. If it matches `^LOO-\d+$`, run the Linear pre-flight (fetch sub-issue + parent + brief + merged framework PR; retry-twice fallback — see `/tutorial` for the full pattern). Otherwise skip to Step 1.

## Workflow

### Step 1 — Source material
Identify what you're writing from. Typically one of:
- A recent framework release (read the `CHANGELOG.md` body from the docs bundle, the release notes, the associated PRs in `lookatitude/beluga-ai`)
- A feature brief from the workspace (`../research/` or `../.wiki/briefs/` when running inside the multi-repo workspace)
- An existing tutorial, guide, or recipe in `src/content/docs/docs/` that needs a short-form companion

If you need original research (competitive analysis, benchmarks, user surveys, community sentiment), STOP and file a research brief upward — the workspace researcher handles investigation. Do not try to do it here.

### Step 2 — Draft
`@agent-content-writer` writes the blog post:
- 800–1200 words
- Hook / problem / solution / code / takeaway structure
- Full compiling Go examples with full imports (`github.com/lookatitude/beluga-ai/...`)
- Link to a runnable example in `lookatitude/beluga-examples` if one exists
- Cite the source material explicitly

If `content-writer` does not yet exist in this repo (pending Phase 3), write the draft yourself and note that Phase 3 will formalize the agent.

### Step 3 — Technical sanity check
Cite the source material the post is based on (release tag, PR, brief). If any technical claim cannot be sourced, either cut it or file an issue in `lookatitude/beluga-ai` asking for review before publishing. Do NOT invent API details.

### Step 4 — Companion social posts
`@agent-marketeer` writes short-form companion posts (LinkedIn, X, Bluesky) that link to the blog. Save as separate files alongside the MDX — do not embed social copy in the blog itself.

If `marketeer` does not yet exist or lives in a different repo, write a single short companion post yourself.

### Step 4a — Code-reviewer (pre-merge, A1)
Invoke `@agent-pr-review-toolkit:code-reviewer`. Verifies example code compiles, imports complete, errors handled, links accurate.

### Step 4b — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward`. Advisory comment on tone / vocabulary / reading level / cross-content consistency. Do not block — human approves final merge regardless of findings.

### Step 5 — Output
Save the draft to `src/content/docs/blog/<slug>.mdx` (current convention — may be formalized as its own Astro content collection later). Save companion social posts to `src/content/docs/blog/_social/<slug>.md`. Open a PR against `main` per branch discipline; never commit directly. Include `LOO-NN` in the PR title if a Linear sub-issue was used so Linear auto-links.
