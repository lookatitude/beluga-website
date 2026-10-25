---
title: LangSmith LLM Debugging
description: "Integrate LangSmith with Beluga AI to trace and debug LLM calls with full prompt visibility, response analysis, and token tracking."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "LangSmith, LLM debugging, Beluga AI, prompt tracing, AI observability, LLM analytics Go, response analysis"
---

## Overview

General-purpose APM tools show you that an LLM call took 800ms, but LangSmith shows you the exact prompt that was sent, the full model response, and how both changed across iterations. This level of detail is essential during development when you are iterating on prompts, debugging unexpected agent behavior, or evaluating response quality. This guide shows how to integrate LangSmith with Beluga AI to capture detailed traces of every LLM call, including input prompts, model responses, latency, and token usage.

## Prerequisites

- Go 1.26 or later
- A Beluga AI application
- A LangSmith account and API key (from [smith.langchain.com](https://smith.langchain.com))

## Installation

Beluga AI ships a LangSmith exporter in `o11y/providers/langsmith`. It talks to the LangSmith runs API over HTTP, so no extra SDK is needed:

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Set the required environment variables:

```bash
export LANGSMITH_API_KEY="your-api-key"
export LANGSMITH_PROJECT="beluga-ai"  # optional, defaults to "default"
```

## Configuration

The exporter is configured with functional options. The environment variables above are read by your application code, not by the exporter itself.

| Option | Description | Default | Required |
|----------|-------------|---------|----------|
| `langsmith.WithAPIKey` | LangSmith API key | - | Yes |
| `langsmith.WithProject` | Project name for organizing traces | `default` | No |
| `langsmith.WithBaseURL` | LangSmith API endpoint | `https://api.smith.langchain.com` | No |
| `langsmith.WithTimeout` | HTTP client timeout | `10s` | No |

## Usage

### Create a LangSmith Exporter

`langsmith.New` returns an `*langsmith.Exporter` that implements `o11y.TraceExporter`. Each `ExportLLMCall` call posts one `llm` run to LangSmith:

```go
import (
	"os"

	"github.com/lookatitude/beluga-ai/v2/o11y/providers/langsmith"
)

exporter, err := langsmith.New(
	langsmith.WithAPIKey(os.Getenv("LANGSMITH_API_KEY")),
	langsmith.WithProject(os.Getenv("LANGSMITH_PROJECT")),
)
if err != nil {
	return fmt.Errorf("create LangSmith exporter: %w", err)
}
```

### Trace Every LLM Call

Wrap a Beluga AI `ChatModel` so every `Generate` call is exported as an `o11y.LLMCallData` record, including the prompt, response, latency, and token usage. The wrapper implements `llm.ChatModel`, so it can be used anywhere a model is expected:

```go
package main

import (
	"context"
	"fmt"
	"iter"
	"log"
	"os"
	"time"

	"github.com/lookatitude/beluga-ai/v2/config"
	"github.com/lookatitude/beluga-ai/v2/llm"
	_ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
	"github.com/lookatitude/beluga-ai/v2/o11y"
	"github.com/lookatitude/beluga-ai/v2/o11y/providers/langsmith"
	"github.com/lookatitude/beluga-ai/v2/schema"
)

// TracedChatModel wraps a ChatModel and exports each call to a TraceExporter.
type TracedChatModel struct {
	model    llm.ChatModel
	provider string
	exporter o11y.TraceExporter
}

func NewTracedChatModel(model llm.ChatModel, provider string, exporter o11y.TraceExporter) *TracedChatModel {
	return &TracedChatModel{model: model, provider: provider, exporter: exporter}
}

func (t *TracedChatModel) Generate(ctx context.Context, msgs []schema.Message, opts ...llm.GenerateOption) (*schema.AIMessage, error) {
	start := time.Now()
	resp, genErr := t.model.Generate(ctx, msgs, opts...)

	data := o11y.LLMCallData{
		Model:    t.model.ModelID(),
		Provider: t.provider,
		Duration: time.Since(start),
		Messages: toMaps(msgs),
	}
	if genErr != nil {
		data.Error = genErr.Error()
	} else {
		data.InputTokens = resp.Usage.InputTokens
		data.OutputTokens = resp.Usage.OutputTokens
		data.Response = map[string]any{"content": resp.Text()}
	}

	// Tracing failures must not break the request path.
	if err := t.exporter.ExportLLMCall(ctx, data); err != nil {
		log.Printf("langsmith export failed: %v", err)
	}
	return resp, genErr
}

func (t *TracedChatModel) Stream(ctx context.Context, msgs []schema.Message, opts ...llm.GenerateOption) iter.Seq2[schema.StreamChunk, error] {
	return t.model.Stream(ctx, msgs, opts...)
}

func (t *TracedChatModel) BindTools(tools []schema.ToolDefinition) llm.ChatModel {
	return &TracedChatModel{model: t.model.BindTools(tools), provider: t.provider, exporter: t.exporter}
}

func (t *TracedChatModel) ModelID() string { return t.model.ModelID() }

// toMaps serialises messages into the generic form LLMCallData expects.
func toMaps(msgs []schema.Message) []map[string]any {
	out := make([]map[string]any, 0, len(msgs))
	for _, m := range msgs {
		var text string
		for _, p := range m.GetContent() {
			if tp, ok := p.(schema.TextPart); ok {
				text += tp.Text
			}
		}
		out = append(out, map[string]any{"role": string(m.GetRole()), "content": text})
	}
	return out
}

func main() {
	ctx := context.Background()

	exporter, err := langsmith.New(
		langsmith.WithAPIKey(os.Getenv("LANGSMITH_API_KEY")),
		langsmith.WithProject(os.Getenv("LANGSMITH_PROJECT")),
	)
	if err != nil {
		log.Fatalf("failed to create exporter: %v", err)
	}

	model, err := llm.New("openai", config.ProviderConfig{
		APIKey: os.Getenv("OPENAI_API_KEY"),
		Model:  "gpt-4o",
	})
	if err != nil {
		log.Fatalf("failed to create model: %v", err)
	}

	traced := NewTracedChatModel(model, "openai", exporter)

	response, err := traced.Generate(ctx, []schema.Message{
		schema.NewHumanMessage("What is the capital of France?"),
	})
	if err != nil {
		log.Fatalf("generation failed: %v", err)
	}

	fmt.Printf("Response: %s\n", response.Text())
	fmt.Println("View the trace at https://smith.langchain.com")
}
```

To send the same records to several backends, combine exporters with `o11y.NewMultiExporter(exporterA, exporterB)`; the result also implements `o11y.TraceExporter`.

## Advanced Topics

### Trace Sampling

In production, tracing every LLM call can generate significant volume. Implement sampling to trace a percentage of calls:

```go
import "math/rand"

func (t *TracedChatModel) shouldTrace() bool {
	return rand.Float64() < 0.1 // Trace 10% of calls
}
```

### Sensitive Data Filtering

Remove personally identifiable information (PII) from traces before sending them to LangSmith. Redact message content in `toMaps` (and the `Response` map) before calling `ExportLLMCall`.

### Project Organization

Use separate LangSmith projects for different environments:

```bash
# Development
export LANGSMITH_PROJECT="beluga-ai-dev"

# Staging
export LANGSMITH_PROJECT="beluga-ai-staging"

# Production
export LANGSMITH_PROJECT="beluga-ai-prod"
```

### Combining with OpenTelemetry

LangSmith tracing complements Beluga AI's built-in OpenTelemetry instrumentation. Use LangSmith for detailed LLM-specific debugging and Datadog or another backend for infrastructure-level observability. Both can run simultaneously without conflict.

## Troubleshooting

### "API key not found"

Verify that `LANGSMITH_API_KEY` is set in the environment. API keys are available from the [LangSmith Settings](https://smith.langchain.com/settings) page.

### Traces not appearing

Check that the API key is valid and the endpoint is reachable, and check the error returned by `ExportLLMCall`. If you use a self-hosted or regional endpoint, pass it with `langsmith.WithBaseURL`.

## Related Resources

- [Datadog Dashboards](/docs/guides/production/integrations/datadog-dashboards) -- Metrics and dashboard monitoring
- [Observability and Tracing](/docs/guides/production/otel-tracing/) -- Beluga AI observability setup
- [LLM Providers](/docs/reference/providers/llm/openai) -- Configuring LLM providers
