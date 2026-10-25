---
derived_from_template: guild.skill_template.v1
name: voice-steward-content-review
description: "Procedure and comment format for an advisory voice review of Beluga website content against .guild/wiki/style-guide.md — tone, vocabulary (preferred and banned phrases), reading level, rhythm, content-type fit and cross-content consistency, with each finding quoting the passage and citing the rule. Returns a comment body; never edits, never blocks. Pulled by voice-steward. TRIGGER for \"voice review this PR\", \"check this post against the style guide\", \"is the tone right for a tutorial\", \"flag banned phrases in this draft\", \"is this guide consistent with how the blog describes the feature\". DO NOT TRIGGER for: rewriting the draft (content-writer / marketing); factual or code correctness (snippet check and Codex adversarial review); SEO meta (seo); editing the style guide itself (normal PR by a human)."
when_to_use: "Pulled by the voice-steward specialist for every pre-merge content review and manual voice checks."
type: specialist
---

# voice-steward-content-review

Evidence is a comment where every finding carries an exact quote, a style-guide rule, and a proposed rewording.

## What you do

1. Read `.guild/wiki/style-guide.md` fully; note its version/updated header.
2. Get the diff (`git diff main...HEAD` or `gh pr diff <n>`); identify content type from path and state the inference.
3. Read the draft fully, then 1–2 published pieces of the same type for consistency.
4. Write findings. No rule covers it → propose a rule, don't critique.

## Output shape

```markdown
## Voice review

**Content type detected:** <type>
**Style guide version:** <from header>

### Voice consistency
### Tone
### Vocabulary
- "<exact quote>" — consider <alternative> (style guide: <rule>)
### Reading level
### Cross-content consistency
### Suggested edits (optional, 3–5)

---
*Advisory review by voice-steward. Not blocking. Human approves final merge.*
```

Return this body. The coordinator posts it with `gh pr comment <n> --body-file …`.

## Anti-patterns

- "The voice feels off" with no quote.
- Proposing a full rewrite.
- Posting the comment or editing the draft yourself.
- Requesting changes or otherwise blocking.

## Handoff

Return the body plus proposed style-guide rules (as `followups:`, owner: human) to the `voice-steward` specialist. This skill does not dispatch.
