---
name: tutorial
description: Write a step-by-step tutorial for a framework feature, with a companion runnable example.
---

Write a tutorial on: $ARGUMENTS

## Workflow

### Step 1 — Source material
Identify the framework feature being taught. Read:
- The relevant framework docs (`../framework/docs/architecture/` or `../framework/docs/guides/`) when the workspace is available.
- The relevant package code if the docs are thin — `../framework/<package>/`.
- Any existing content in `src/content/docs/docs/` that covers adjacent topics (avoid duplication).

If the feature isn't documented in framework docs, STOP and file an issue in `lookatitude/beluga-ai` asking for documentation first. Don't write a tutorial from undocumented code.

### Step 2 — Companion example check
Check whether a runnable example exists in `lookatitude/beluga-examples` for this feature:
- If yes: the tutorial will link to it. Read the example to understand its scope.
- If no: file an issue in `lookatitude/beluga-examples` requesting a companion example. Include the tutorial title, the feature being taught, and the expected imports. Continue writing the tutorial; link to the issue as "companion example in progress".

### Step 3 — Draft
`@agent-content-writer` writes the tutorial:
- 1500–3000 words
- Structure: what you'll build → prerequisites → step-by-step → complete code → next steps
- Every step builds on the previous one
- The "complete code" section is a single copy-paste-runnable program
- Full Go imports, explicit error handling, registry pattern usage

### Step 4 — Code verification
Every Go code snippet in the tutorial must compile. Run `go build` on the complete code section at minimum. If individual steps are meant to be runnable independently, verify each one.

### Step 5 — Output
Save to `src/content/docs/docs/guides/<slug>.mdx`. Open a PR against `main` per branch discipline.

Link to the companion example prominently (or to the pending issue if the example doesn't exist yet).
