---
name: guide
description: Write a focused how-to guide for a specific task (e.g., "configure rate limiting", "add a custom provider").
---

Write a how-to guide on: $ARGUMENTS

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

### Step 4 — Output
Save to `src/content/docs/docs/guides/<slug>.mdx` (for substantial how-tos) or `src/content/docs/docs/recipes/<slug>.mdx` (for short, focused recipes). Open a PR against `main` per branch discipline.
