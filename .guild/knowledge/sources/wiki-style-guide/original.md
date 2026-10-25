# Beluga Content Style Guide

**Purpose:** define the voice, tone, and structural conventions for all public Beluga content (blog, tutorials, guides, reference pages, announcements). The `voice-steward` agent checks every content PR against this file.

**Last updated:** 2026-04-18
**Version:** 0.1 (initial scaffolding — calibrate through first real content PRs)

## Target audience

**Primary:** Go developers evaluating or adopting Beluga for production agent work. Senior enough to care about observability, layered architecture, and security; not assumed to be familiar with agent-specific jargon (ReAct, tool-calling, handoffs).

**Secondary:** architects at organizations evaluating agent frameworks; technical decision-makers.

**Not the target:** pure beginners ("what is an LLM?"); marketing-only audiences.

## Reading level

Target: Flesch reading ease **50-60** (fairly difficult, accessible to technical readers). Sentences average 15-20 words. Paragraphs 2-5 sentences.

## Tone traits

- **Precise:** "The registry holds factories indexed by name" — not "We store things in a map-like structure."
- **Sourced:** every strong claim has a concrete anchor (code reference, benchmark, external source).
- **Direct:** "Use `llm.New()`." — not "It may be advisable to consider using `llm.New()`."
- **Self-aware without false modesty:** state what Beluga is good at and what it isn't. Compare honestly with alternatives.
- **Free of AI slop:** no "dive into," no "let's explore," no "unleash the power of," no filler preamble. Start with the point.

## Voice anti-patterns (banned)

- **"Dive into"** — use "cover," "walk through," or drop the verb entirely.
- **"Unleash the power of"** — delete and rewrite.
- **"In today's fast-paced world"** — delete.
- **"Let's dive in"** — state what the article does instead.
- **"Revolutionary,"** **"game-changing,"** **"next-generation"** — marketing hype; use concrete claims.
- **Generic "the framework"** when "Beluga" is meant — use the name.
- **Excessive qualifiers** ("very," "really," "quite") — delete.
- **Excessive em-dashes** — use sparingly; em-dash runs are an AI-writing tell.

## Voice preferences

- **Active voice** whenever possible.
- **Second person ("you")** for tutorials and guides; **third person** for reference and announcements.
- **Present tense** for how things work; **past tense** for changelog entries and release notes.
- **Code with full imports** — no abbreviated examples; no `// ...` ellipses inside small examples.
- **Error paths shown** in every Go example that does I/O.

## Content-type templates

### Blog post

Length: 600-1200 words. Structure:

1. **Hook** — one sentence stating what shipped or what's new.
2. **Why it matters** — 1-2 paragraphs on the problem this solves.
3. **What shipped** — concrete capability, named features.
4. **Quick example** — compilable Go snippet (full imports, explicit errors).
5. **What's next** — outlook for the feature area.

Don't include: installation instructions (link to the quickstart), full reference (link to reference docs).

### Tutorial

Length: 1500-3000 words. Structure:

1. **What you'll build** — concrete artifact the reader will produce.
2. **Prerequisites** — exact versions, API keys needed.
3. **Step 1-N** — each step a compilable checkpoint.
4. **What you built** — recap with the final artifact.
5. **Next steps** — pointers to related guides and reference.

Every step must compile. Readers who copy-paste should have a working program after every step.

### Guide

Length: 500-1500 words. Structure:

1. **What problem this solves** — the user-facing question.
2. **Approach** — the conceptual answer.
3. **Implementation** — walkthrough with code examples.
4. **Tradeoffs / gotchas** — when to use this approach vs alternatives.
5. **Related** — cross-links.

### Reference

Auto-generated from godoc where possible. Curated narrative for each package explaining *why* and *when* to use it, in addition to the auto-generated API surface.

### Announcement (release notes)

Length: 200-500 words per release. Structure:

1. **Release tag + date.**
2. **Highlights** — 3-5 bullets.
3. **Breaking changes** — explicit, with migration notes.
4. **What's new** — itemized.
5. **Fixes** — itemized.
6. **Full changelog** — link.

## Cross-content consistency rules

- Describe the same feature the same way across blog / tutorial / guide / reference. Prefer reusing phrases from the reference doc.
- Use the same example scenarios (e.g., "build a customer support agent") across related content when possible.
- Version references are explicit (`vX.Y.Z`) or relative to the current latest.

## Updating this guide

Voice-steward enforces this guide but does not own it. Humans propose updates via PR, and the guide evolves as content accumulates. Version the changes in the header.

Version history:
- 0.1 (2026-04-18): initial scaffolding (A2).
