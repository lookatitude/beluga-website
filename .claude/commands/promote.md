---
name: promote
description: Coordinate full marketing rollout for a feature or release — blog post + companion social + release note + landing page refresh, cross-referenced to competitor positioning.
---

Promote: $ARGUMENTS

## When to use this

For a **full release or major feature launch** where multiple pieces of content need to ship together. For a single standalone blog post, use `/blog` instead — this command calls `/blog` as one of its steps.

## Workflow

### Step 1 — Competitive context
Read `../framework/.wiki/competitors/*.md` when running inside the multi-repo workspace (those files live in the framework repo). If the workspace isn't available, note which comparisons need the file and cut them from the promo copy rather than inventing claims.

If deeper competitive research is needed (new competitor, new benchmark, market shift), STOP and file a research brief upward to the workspace researcher. Do not attempt competitive research here.

### Step 2 — Long-form content
Invoke `/blog` for the main blog post on $ARGUMENTS. Output: `src/content/docs/blog/<slug>.mdx` plus companion social under `_social/`.

### Step 3 — Release note
`@agent-marketeer` writes the release note:
- What changed and why it matters (not a raw CHANGELOG dump)
- Breaking changes + migration steps
- Link to the full CHANGELOG page on the site
- Output: `src/content/docs/releases/<tag>.mdx` (current convention — may be formalized as its own content collection later)

If `marketeer` does not yet exist or lives in a different repo, write the release note yourself using the tone from existing release notes.

### Step 4 — Landing page refresh
If the release introduces user-visible changes worth highlighting on the landing page or `src/content/docs/docs/start/`, propose edits to those pages in the same PR. Do NOT rewrite marketing copy wholesale — reuse existing hero/CTA/feature-card components.

### Step 5 — Competitor positioning
If any claim in the content depends on `framework/.wiki/competitors/`, cite the exact file and the date of its last update. If a cited claim is older than 6 months, flag it in the PR description so the reviewer can decide whether to re-verify before publishing.

### Step 6 — Output and PR
Everything lands in a single PR against `main` per branch discipline:
- `src/content/docs/blog/<slug>.mdx` + `_social/<slug>.md`
- `src/content/docs/releases/<tag>.mdx`
- Any landing-page or docs edits

Do NOT commit directly to main. Do NOT split this into multiple PRs — the campaign is one coordinated change.
