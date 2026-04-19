---
platform: x
tag: v2.10.1
date: 2026-04-19
---

1/6
Beluga v2.10.1 ships a CLI. One binary, two read-only subcommands, and a JSON output contract where scripts need it. Built for CI, not just humans.

2/6
Install it the Go way:
go install github.com/lookatitude/beluga-ai/v2/cmd/beluga@v2.10.1

Pin the tag on release day — module proxy indexing can lag behind by minutes to hours.

3/6
`beluga version` prints the framework version, the Go toolchain, and a provider-count summary — one field per line. Parseable by `awk` or `head` in CI gates.

4/6
`beluga providers` lists every registered provider grouped by category. `--output json` emits a sorted, structured array. Stdout stays clean, diagnostics go to stderr, a pipeline can actually parse it.

5/6
The decision that matters: `--output json` is a persistent flag on the root command. Future subcommands inherit it as they land. Structured output is the contract, not a feature.

6/6
Full post: https://beluga-ai.org/blog/cli-foundation-json-output/
Tutorial: https://beluga-ai.org/docs/guides/install-beluga-cli/
