---
name: tutorial
description: Write a step-by-step tutorial for a framework feature, with a companion runnable example.
---

Write a tutorial on: $ARGUMENTS

$ARGUMENTS may be a free-form topic OR a Linear sub-issue ID (e.g., `LOO-47`) labeled `layer:website`. If it matches `^LOO-\d+$` (case-insensitive), run the Linear pre-flight below first; otherwise skip to Step 1.

## Pre-flight (Linear-integrated, A1)

1. Fetch the sub-issue and parent via Linear MCP (`mcp__claude_ai_Linear__get_issue`). Capture titles, descriptions, labels.
2. From the parent's description, read the workspace brief at `../research/briefs/<slug>.md`.
3. Find the linked merged framework PR and read it: `gh pr view <num> --repo lookatitude/beluga-ai --json title,body,files`. The merged diff is canonical for API shape in the tutorial.
4. On Linear MCP failure: retry twice, then proceed with brief + PR context only; flag the gap in the PR description. Do not silently skip.

### 1b. Validate content-type label (A3)

After fetching the sub-issue, check its labels. If it has a `content:*` label, verify it matches this command:

- `/tutorial` expects `content:tutorial`
- If the sub-issue has `content:blog` instead: warn and suggest running `/blog <LOO-NN>` instead. Do not proceed silently — the drafter is configured for tutorial structure, not blog structure. User may choose to continue anyway.
- If the sub-issue has `content:guide`, `content:reference`, or `content:landing`: warn and suggest the corresponding command.
- If the sub-issue has no `content:*` label (predates A3 or created via A1's simpler /plan-content): proceed as generic tutorial; do not block.

Warning message template:

```
Sub-issue <LOO-NN> is labeled content:<actual-type>, but you invoked /tutorial.
Content types have different templates and voice targets.

Did you mean to run /<actual-type> <LOO-NN>?

Proceed anyway? (no — stop and re-run; yes — continue as tutorial ignoring the label)
```

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

### Step 4a — Code-reviewer (pre-merge, A1)
Invoke `@agent-pr-review-toolkit:code-reviewer` on the draft. Verifies imports complete, errors handled, links accurate. Address high-confidence findings before opening the PR.

### Step 4b — Voice-steward (pre-merge, A2)
Invoke `@agent-voice-steward` on the draft. Reads `.wiki/style-guide.md`, posts a review comment on tone / vocabulary / reading level / cross-content consistency. **Advisory only** — do not block on findings; continue to Step 5. Human decides what to act on.

### Step 5 — Output
Save to `src/content/docs/docs/guides/<slug>.mdx`. Open a PR against `main` per branch discipline. If a Linear sub-issue ID was used, include `LOO-NN` in the PR title so Linear auto-links.

Link to the companion example prominently (or to the pending issue if the example doesn't exist yet).
