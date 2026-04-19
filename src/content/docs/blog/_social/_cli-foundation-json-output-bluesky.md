---
platform: bluesky
tag: v2.10.1
date: 2026-04-19
---

1/3
Beluga v2.10.1 ships a CLI. One binary, `beluga version` + `beluga providers`, and `--output json` on the command that needs to be machine-readable. Structured output by default, not as an afterthought.

2/3
Install: go install github.com/lookatitude/beluga-ai/v2/cmd/beluga@v2.10.1. Pin the tag on release day — the module proxy can lag behind @latest for minutes to hours.

3/3
Stdout is machine output, stderr carries diagnostics, JSON is the contract for `providers`. Safe to put in a CI gate.
Full post: https://beluga-ai.org/blog/cli-foundation-json-output/
