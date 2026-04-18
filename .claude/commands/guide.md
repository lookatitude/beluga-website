---
name: guide
description: Write a focused how-to guide for a specific task (e.g., "configure rate limiting", "add a custom provider").
---

Write a how-to guide on: $ARGUMENTS

$ARGUMENTS may be a free-form topic OR a Linear sub-issue ID. If it matches `^LOO-\d+$`, run the same Linear pre-flight as `/tutorial` (fetch sub-issue + parent + brief + merged framework PR; retry-twice fallback). Otherwise skip to Step 1.

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

### Step 3a — Code-reviewer (pre-merge, A1)
Invoke `@agent-pr-review-toolkit:code-reviewer` on the draft. Addresses quality findings before PR open.

### Step 3b — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward`. Advisory comment on tone / vocabulary / consistency. Do not block.

### Step 4 — Output
Save to `src/content/docs/docs/guides/<slug>.mdx` (for substantial how-tos) or `src/content/docs/docs/recipes/<slug>.mdx` (for short, focused recipes). Open a PR against `main` per branch discipline. Include `LOO-NN` in the PR title if a Linear sub-issue was used.
