---
title: Filesystem Prompt Templates
description: "Manage Beluga AI prompt templates as versioned JSON files with the filesystem PromptManager and Git version control."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "prompt templates, filesystem store, Beluga AI, template caching, hot-reload prompts, Git versioned prompts, Go prompt management"
---

Prompt engineering is iterative. Embedding prompts as string literals in Go code means every change requires a code review, recompilation, and redeployment. Filesystem-based templates externalize prompts as files that can be version-controlled in Git, reviewed by non-developers (product managers, domain experts), and rolled out by version. Beluga AI ships a filesystem-backed `prompt.PromptManager` in `prompt/providers/file` that loads versioned templates from a directory of JSON files.

## Overview

`file.FileManager` provides:

- One JSON file per template version, kept in Git alongside your code
- Multiple versions per template name; `Get(name, "")` returns the latest
- Go `text/template` rendering with per-template default variables
- Validation of every template when the directory is loaded
- `List()` to discover available templates and versions
- Optional OpenTelemetry tracing via `prompt.WithTracing()` middleware

## Prerequisites

- Go 1.26 or later
- Beluga AI framework installed
- Familiarity with Go's `text/template` syntax

## Setup

### Directory Structure

Create a directory to hold your prompt templates:

```bash
mkdir -p prompts/templates
```

Each file is a JSON-encoded `prompt.Template`. Create `prompts/templates/rag-1.0.0.json`:

```json
{
  "name": "rag",
  "version": "1.0.0",
  "content": "Use the following pieces of context to answer the question at the end.\nIf you don't know the answer, just say that you don't know, don't try to make up an answer.\n\nContext: {{.context}}\n\nQuestion: {{.question}}\n\nAnswer:",
  "variables": {
    "context": "No context available."
  },
  "metadata": {
    "owner": "search-team"
  }
}
```

The file name does not matter; only files ending in `.json` are read, and the `name` and `version` fields identify the template. `variables` holds default values used when the caller does not supply a key.

## Usage

### Loading and Rendering Templates

```go
package main

import (
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/prompt"
    "github.com/lookatitude/beluga-ai/v2/prompt/providers/file"
)

func main() {
    fm, err := file.NewFileManager("prompts/templates")
    if err != nil {
        log.Fatalf("load templates: %v", err)
    }

    // Wrap with OTel tracing (one span per Get/Render/List call).
    mgr := prompt.ApplyMiddleware(fm, prompt.WithTracing())

    // Discover available templates.
    for _, info := range mgr.List() {
        fmt.Printf("%s@%s\n", info.Name, info.Version)
    }

    // Get a specific version and render it to a string.
    tmpl, err := mgr.Get("rag", "1.0.0")
    if err != nil {
        log.Fatalf("get template: %v", err)
    }
    text, err := tmpl.Render(map[string]any{
        "context":  "Machine learning is a subset of AI.",
        "question": "What is ML?",
    })
    if err != nil {
        log.Fatalf("render: %v", err)
    }
    fmt.Printf("Formatted prompt:\n%s\n", text)

    // Or render the latest version straight into messages.
    msgs, err := mgr.Render("rag", map[string]any{"question": "What is AI?"})
    if err != nil {
        log.Fatalf("render messages: %v", err)
    }
    fmt.Printf("rendered %d message(s)\n", len(msgs))
}
```

`Render` returns the rendered text as a single system message (`schema.NewSystemMessage`). Use `Get` plus `Template.Render` when you need the raw string, for example to build a human message instead.

### Versioning

Add `prompts/templates/rag-1.1.0.json` with `"version": "1.1.0"` and `Get("rag", "")` and `Render("rag", ...)` will pick it up the next time the manager is created. Versions are compared as strings (lexicographically), so keep them zero-padded or strictly semver with single-digit components to get the expected ordering. Pin `Get("rag", "1.0.0")` in code paths that must not change behaviour during a rollout.

### Reloading

`NewFileManager` reads the directory once. To pick up edits without restarting, create a new manager (for example on `SIGHUP` or from a file-watcher) and swap it in behind your own `sync.RWMutex` or `atomic.Pointer`. Creation fails if any file is invalid, so a bad edit leaves the previous manager in place.

## Troubleshooting

### Template not found

`NewFileManager` only reads `.json` files directly inside the directory (not subdirectories). Check that the file's `name` field matches the name you pass to `Get` or `Render`:

```bash
ls prompts/templates/
```

### Invalid template syntax

Template variables must use Go's `text/template` syntax with the dot prefix:

```text
Context: {{.context}}
Question: {{.question}}
```

`NewFileManager` validates every file and returns an error naming the file that failed to parse, so syntax errors surface at startup rather than at render time.

## Production Considerations

- **Version control** prompt files in Git alongside your application code
- **Load once at startup**; `FileManager` keeps all templates in memory
- **Rebuild the manager** on change during development for hot-reload without restarts
- **Validate templates in CI** by calling `file.NewFileManager` on the prompts directory in a test
- **Restrict file access** permissions to prevent unauthorized template modification

## Related Resources

- [LangChain Hub Loading](/docs/guides/production/integrations/langchain-hub) -- Load community prompts from LangChain Hub
- [Prompt Package Reference](/docs/reference/api/prompt) -- Prompt management API
