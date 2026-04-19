---
title: Install and use the beluga CLI
description: "Install the beluga CLI from v2.10.1, inspect its version and providers, and gate a CI check on provider availability using JSON output."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, CLI, beluga command, version, providers, JSON output, CI gate, tutorial"
---

The `beluga` command-line tool ships with the framework as of v2.10.1. You install it with `go install`, inspect the framework version with `beluga version`, list the providers compiled into your binary with `beluga providers`, and parse that list with `beluga providers --output json` when you need machine-readable output. This guide walks through each of those steps and ends with a portable CI shell script you can drop into any pipeline that depends on Beluga.

## What you will build

A shell-based workflow that installs the CLI from a pinned framework version, inspects the release, and fails a CI check when a required provider is missing.

## Prerequisites

- Go 1.23 or later (`go version` should print `go1.23` or higher).
- [`jq`](https://jqlang.github.io/jq/) available on your `PATH` — the CI gate uses it to parse JSON.
- A working `$GOPATH/bin` or `$GOBIN` on your shell's `PATH`, so that binaries from `go install` are discoverable.

You do not need Docker, Kubernetes, any cloud account, or an API key for any step in this guide. Every command runs locally against a binary compiled on your machine.

## Step 1: Install the CLI

Install the CLI from a pinned framework version. Pinning is important because the provider list you see is a property of the binary you compiled, not of the module proxy — a binary built against v2.10.1 reports only the providers blank-imported by that release.

```bash
go install github.com/lookatitude/beluga-ai/v2/cmd/beluga@v2.10.1
```

**Checkpoint.** The binary is on your `PATH`, and `beluga --help` lists the available subcommands.

```console
$ which beluga
/home/you/go/bin/beluga
$ beluga --help
beluga is the official command-line tool for the Beluga AI framework.

Usage:
  beluga [command]

Available Commands:
  completion  Generate the autocompletion script for the specified shell
  deploy      Generate deployment artifacts
  dev         Start development server
  help        Help about any command
  init        Initialize a new Beluga AI project
  providers   List providers compiled into this binary
  test        Run agent tests
  version     Print framework version, Go runtime, and provider counts

Flags:
  -h, --help               help for beluga
      --log-level string   log level (debug, info, warn, error) — written to stderr (default "info")
  -o, --output string      output format for machine-readable commands (e.g. "json")

Use "beluga [command] --help" for more information about a command.
```

If `which beluga` returns nothing, your Go bin directory is missing from your shell's `PATH`. Add `export PATH="${GOBIN:-$(go env GOPATH)/bin}:$PATH"` to your shell profile and re-source it.

## Step 2: Inspect the framework version

Run `beluga version`. It prints three lines to stdout: the framework version it was compiled against, the Go toolchain that produced the binary, and a one-line summary of the providers registered at link time.

```bash
beluga version
```

**Checkpoint.** You see the framework version, the Go runtime, and a non-zero count for each provider category.

```console
$ beluga version
beluga v2.10.1
go1.23.x
providers: llm=3 embedding=2 vectorstore=1 memory=5
```

Your second line shows whichever Go toolchain produced the binary; any `go1.23+` release is fine. Each line has a job. The first line is what you assert on in a release test: the leading `beluga ` makes it trivial to cut with `awk '{print $2}'`. The second line is the Go toolchain, which matters when you are debugging a binary built in CI against one you compiled locally. The third line is a quick sanity check that the providers you expect to be compiled in actually are. If you expected `llm=5` and see `llm=3`, something in your release pipeline dropped two blank imports.

`beluga version` does not take `--output json`. The three-line format is stable, and `awk` is all you need to extract any of the three values. Scripts that need structured data should call `beluga providers --output json` instead, which is the focus of the next two steps.

## Step 3: List providers in tabular form

`beluga providers` prints every provider registered with the CLI binary, one per line, grouped by category. The default output is tab-separated, which reads well in a terminal and pipes into `cut`, `awk`, and `grep` without quoting surprises.

```bash
beluga providers
```

**Checkpoint.** You see a row per `(category, provider)` pair. The v2.10.1 binary ships eleven rows across four categories.

```console
$ beluga providers
llm          anthropic
llm          ollama
llm          openai
embedding    ollama
embedding    openai
vectorstore  inmemory
memory       archival
memory       composite
memory       core
memory       inmemory
memory       recall
```

The registry is populated at link time by the blank imports in [`cmd/beluga/providers/providers.go`](https://github.com/lookatitude/beluga-ai/blob/v2.10.1/cmd/beluga/providers/providers.go). If you add a provider to your own build by forking the CLI and adding an import, that provider appears here. If you strip one out with build tags, it disappears. The list is a direct reflection of what is linked into this specific binary.

## Step 4: Parse providers with `--output json`

The same command with `--output json` emits an indented JSON array. This is the format you reach for in scripts, CI gates, and anywhere else you want to ask structured questions like "is `vectorstore=pgvector` available?" without writing a parser.

```bash
beluga providers --output json
```

**Checkpoint.** The output is a JSON array of `{category, providers}` objects.

```console
$ beluga providers --output json
[
  {
    "category": "llm",
    "providers": [
      "anthropic",
      "ollama",
      "openai"
    ]
  },
  {
    "category": "embedding",
    "providers": [
      "ollama",
      "openai"
    ]
  },
  {
    "category": "vectorstore",
    "providers": [
      "inmemory"
    ]
  },
  {
    "category": "memory",
    "providers": [
      "archival",
      "composite",
      "core",
      "inmemory",
      "recall"
    ]
  }
]
```

The JSON goes to stdout and nothing else does, so `beluga providers --output json | jq .` is safe to redirect into a file or a pipe without any risk of diagnostic output contaminating the stream.

Ask a specific question with `jq`. For example, to check that the `openai` LLM provider is available:

```console
$ beluga providers --output json \
  | jq '.[] | select(.category == "llm") | .providers | contains(["openai"])'
true
```

`jq` returns `true` or `false`, which is exactly the shape a CI gate needs.

## Step 5: Gate a CI check on provider availability

Combine the pieces into a small shell script. The script asserts the framework version, confirms the LLM provider your deployment requires is linked into the binary, and exits non-zero when either check fails. Drop it into `ci/check-beluga.sh` and wire it into your pipeline ahead of the stages that actually use Beluga.

```bash
#!/usr/bin/env bash
set -euo pipefail

EXPECTED_VERSION="v2.10.1"
REQUIRED_LLM="openai"

ACTUAL_VERSION="$(beluga version | head -n1 | awk '{print $2}')"
if [[ "${ACTUAL_VERSION}" != "${EXPECTED_VERSION}" ]]; then
  echo "version mismatch: expected ${EXPECTED_VERSION}, got ${ACTUAL_VERSION}" >&2
  exit 1
fi

HAS_LLM="$(beluga providers --output json \
  | jq -r --arg p "${REQUIRED_LLM}" \
      '.[] | select(.category == "llm") | .providers | contains([$p])')"
if [[ "${HAS_LLM}" != "true" ]]; then
  echo "required LLM provider '${REQUIRED_LLM}' not linked into binary" >&2
  exit 1
fi

echo "beluga ${ACTUAL_VERSION} OK: ${REQUIRED_LLM} LLM provider available"
```

**Checkpoint.** Run the script against your installed binary. It exits with status `0` and prints the confirmation line.

```console
$ bash ci/check-beluga.sh
beluga v2.10.1 OK: openai LLM provider available
$ echo $?
0
```

The `| head -n1 | awk '{print $2}'` pattern pulls the version token out of the first line of `beluga version` without touching the Go-toolchain line or the provider summary. The `jq -r ... contains([$p])` pattern asks a single boolean question of the JSON output: no grepping, no regex, and no parser changes when a new category is added to the binary.

To confirm the gate really does fail, set `REQUIRED_LLM=does-not-exist` at the top of the script and re-run it. The script exits with status `1` and writes `required LLM provider 'does-not-exist' not linked into binary` to stderr, leaving stdout clean for a downstream consumer.

## What you built

You now have a repeatable, pinned workflow for CLI-driven Beluga checks:

- Install from a specific framework version with `go install .../cmd/beluga@v2.10.1`.
- Assert the version and provider counts with `beluga version`.
- Inspect providers in a human-readable table with `beluga providers`.
- Consume the same list programmatically with `beluga providers --output json | jq`.
- Combine the two into a CI gate that fails when your deployment's required provider is missing.

Because every command writes machine output to stdout and writes nothing to stderr on the success path, the gate stays stable under `set -euo pipefail` and composes with standard shell tooling.

## Next steps

- Read the [v2.10.1 release notes on GitHub](https://github.com/lookatitude/beluga-ai/releases/tag/v2.10.1) for the full shipping scope and what is deliberately deferred.
- Consult the [framework CLI reference](https://github.com/lookatitude/beluga-ai/blob/v2.10.1/docs/reference/cli.md) for every flag, exit code, and subcommand.
- Move from command-line inspection to building an agent with the same providers in the [Building Your First Agent](/docs/guides/foundations/first-agent/) guide.
