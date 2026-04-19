# Website Corrections

On-demand log of content, voice, and build-system corrections specific to the
website repo. Populated by `voice-steward`, `seo-meta`, `developer-web`, and
human edits as patterns emerge. Entries are append-only and dated.

## 2026-04-19 — Announcement-register pronoun drift

**Context:** voice-steward review of `cli-foundation-json-output.mdx` (LOO-143).

**Observation:** the style guide (`style-guide.md` v0.1) says "third person for
reference and announcements" but does not cover three recurring edge cases
that content drafters hit in practice:

1. **Hook sentences with imperatives.** `"Install it, run it, and a shell
   script can parse the answer."` reads naturally as an opener even though
   it's second-person-imperative in tense.
2. **Closing calls-to-action.** `"use it as a gate the next time a build
   surprises you"` — the trailing "you" breaks third person mid-sentence.
3. **Social companions.** LinkedIn posts read more naturally in second
   person than strict announcement register allows; the guide is silent on
   whether social companions inherit the parent content's register or the
   platform's native register.

**Pattern to apply until the guide is updated:**

- Opening imperatives are acceptable (treat as idiomatic hook).
- Closing CTAs should stay in third person: prefer "when a build reports the
  wrong version" over "the next time a build surprises you".
- X and Bluesky companions inherit announcement register. LinkedIn companions
  may relax to second person for platform fit, but flag the choice
  explicitly in the front matter or PR description.

**Proposed style-guide update:** add an "Announcement pronoun rules"
subsection under "Voice preferences" covering these three cases.

## 2026-04-19 — Product name in titles

**Context:** voice-steward review of `cli-foundation-json-output.mdx` (LOO-143).

**Observation:** prior blog `v2.9.1-release.mdx` uses `"Beluga AI v2.9.1"` in
its title. New blog `cli-foundation-json-output.mdx` uses `"Beluga"` alone.
The style guide rule `"Generic 'the framework' when 'Beluga' is meant — use
the name"` covers body prose but is silent on whether titles should use
`"Beluga"` or `"Beluga AI"`.

**Pattern to apply until the guide is updated:** match the register of
adjacent recently published posts for consistency. For v2.x release
announcements specifically, the prior convention is `"Beluga AI vX.Y.Z"`;
for feature-shipped posts where a version is not the headline,
`"Beluga"` alone is acceptable.

**Proposed style-guide update:** add a one-line rule under "Cross-content
consistency rules" stating the title convention for release announcements
vs feature announcements.
