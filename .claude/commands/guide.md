---
name: guide
description: Write a focused how-to guide for a specific task (e.g., "configure rate limiting", "add a custom provider").
---

Write a how-to guide on: $ARGUMENTS

$ARGUMENTS may be a free-form topic OR a Linear sub-issue ID. If it matches `^LOO-\d+$`, run the same Linear pre-flight as `/tutorial` (fetch sub-issue + parent + brief + merged framework PR; retry-twice fallback). Otherwise skip to Step 1.

## Invocation notes

- **Task focus:** One job per guide; list prerequisites and “Out of scope” so steps are not read as open-ended.
- **Linking:** If a tutorial or example is the natural next step, name the path or URL—do not assume the reader will discover it.

### 1b. Validate content-type label (A3)

After fetching the sub-issue, check its labels. Expect `content:guide`:

- Mismatch with `content:tutorial`, `content:blog`, `content:reference`, or `content:landing` → warn and suggest the corresponding command. The drafter is configured for task-oriented how-to structure, not the other content types. User may choose to continue anyway.
- Missing `content:*` label (predates A3 or created via A1's simpler /plan-content) → proceed as generic guide; do not block.
- Matching `content:guide` → proceed normally.

Use the same warning template as `/tutorial`:

```
Sub-issue <LOO-NN> is labeled content:<actual-type>, but you invoked /guide.
Content types have different templates and voice targets.

Did you mean to run /<actual-type> <LOO-NN>?

Proceed anyway? (no — stop and re-run; yes — continue as guide ignoring the label)
```

## Workflow

### Step 1 — Source material
Identify the specific task. Read:
- The relevant framework docs or pattern files (`../framework/docs/patterns/`, `../framework/docs/guides/`).
- Any existing guides in `src/content/docs/docs/guides/` or recipes in `src/content/docs/docs/recipes/` to avoid overlap.

If there's a tutorial on the same topic, the guide should be complementary (task-focused, shorter) not duplicative.

### Step 2 — Draft
`@agent-content-writer` writes the guide:
- 500–1500 words
- Structure: goal → approach → code → gotchas → related
- One task, one guide. Don't try to cover everything.
- Full Go imports, explicit error handling.

### Step 3 — Code verification
All Go code snippets must compile. Verify with `go build`.

### Step 3a — Code check and adversarial review (pre-merge)
Run the Go snippet check locally: `scripts/snippets/check.sh ../framework <out-dir>` (needs Go 1.26+ and a framework checkout at the released tag; same script as the advisory `Go snippets` job in `.github/workflows/pr.yml`). Complete programs must compile; partial snippets may fail the compile step but must pass the API lint (no nonexistent packages or symbols). Then, before the PR opens, the coordinator runs `/codex:adversarial-review` on the branch (Codex is the cross-family reviewer; if it is unavailable, say so in the PR description, and don't present a same-family review as an equivalent pass).

### Step 3b — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward`. It returns an advisory comment body (the coordinator posts it on the PR) on tone / vocabulary / consistency. Do not block.

### Step 4 — Output
Save to `src/content/docs/docs/guides/<slug>.mdx` (for substantial how-tos) or `src/content/docs/docs/recipes/<slug>.mdx` (for short, focused recipes). Commit on a branch (never `main`); the coordinator pushes and opens the PR against `main`. Include `LOO-NN` in the PR title if a Linear sub-issue was used. `yarn build` and `python3 scripts/check-links.py dist` must pass locally first.

## Coordinator handoff

This command runs in the coordinator (main session) when you invoke it directly. Subagents it dispatches (`content-writer`, `marketeer`, `seo-meta`, `voice-steward`, …) write files and return; they never push, open PRs, post comments or file issues. If you are yourself a teammate running this command for a coordinator, stop after the local commit on your branch and hand back the PR title, body, voice-steward review and any proposed issues; the coordinator runs `/codex:adversarial-review`, pushes, opens the PR and posts the comments.

