---
platform: linkedin
tag: v2.10.1
date: 2026-04-19
---

Beluga v2.10.1 ships with a CLI for the first time. One binary, two read-only subcommands, and a JSON output contract where scripts need it.

Until this release, Beluga was import-only. Anyone who wanted to know which framework version a program would build against had to read go.mod. Anyone who wanted to know which providers were registered had to read source. Neither answer survives a CI pipeline where the container running the check is different from the container running the build.

A CLI changes the question from "what does the code say" to "what does the toolchain report at this exact version." That is the right question for reproducibility, and the first question framework evaluators ask.

What v2.10.1 adds:

`beluga version` — prints the framework version, the Go toolchain that built the binary, and a one-line provider-count summary. CI can parse any of the three fields directly.

`beluga providers` — lists every registered provider grouped by category. A human-readable table by default, a structured sorted array when invoked with `--output json`.

`--output json` — a persistent flag on the root command. Honoured by `providers` in this release and by future subcommands as they land.

Stdout is machine output. Stderr carries diagnostics. Exit codes reflect the operation, not the formatting. That separation is what makes this CLI safe to put in a pipeline.

Install with:
go install github.com/lookatitude/beluga-ai/v2/cmd/beluga@v2.10.1

Full post: https://beluga-ai.org/blog/cli-foundation-json-output/
