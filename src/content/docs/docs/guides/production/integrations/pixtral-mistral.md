---
title: Pixtral Vision (Mistral AI)
description: "Integrate Pixtral, Mistral AI's vision-language model, with Beluga AI for image analysis, visual Q&A, and multimodal understanding in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Pixtral, Mistral AI vision, multimodal LLM, image analysis Go, visual question answering, Beluga AI, vision-language model"
---

Many AI applications need to process visual content -- extracting data from screenshots, analyzing product images, reading documents, or understanding diagrams. Pixtral is Mistral AI's vision-language model that handles these tasks through the same API used for text-only Mistral models, making it straightforward to add visual understanding to existing Mistral-based workflows.

Choose Pixtral when you need vision capabilities from a European-hosted provider (relevant for GDPR compliance) or when you are already using Mistral for text generation and want to keep your provider stack consistent.

## Overview

Pixtral provides vision-language capabilities through the Mistral AI API. When integrated with Beluga AI, it enables:

- **Visual question answering** -- ask questions about image content
- **Image captioning** -- generate descriptions from images
- **Scene analysis** -- detailed analysis of complex visual scenes
- **Document understanding** -- extract information from documents and screenshots

Pixtral uses the same Mistral API as other Mistral models, with multimodal input supplied as content parts.

:::caution[Use the OpenAI-compatible provider for images]
Beluga's native `mistral` provider (`llm/providers/mistral`) is text-only today: it sends only the text of each message and drops `schema.ImagePart` values. To send images to Pixtral, use the `openai` provider pointed at Mistral's OpenAI-compatible chat completions endpoint (`https://api.mistral.ai/v1`), which converts `schema.ImagePart` into `image_url` content (inline bytes are sent as a base64 data URI). The examples below do this.
:::

## Prerequisites

- Go 1.26 or later
- A Mistral AI API key (obtain from [mistral.ai](https://mistral.ai))
- Beluga AI framework installed

## Installation

The `openai` provider used below is included in Beluga AI. No additional dependencies are required beyond the framework itself.

Set your API key:

```bash
export MISTRAL_API_KEY="your-api-key"
```

## Configuration

### Basic Setup

Create an `openai` provider that targets Mistral's endpoint and the Pixtral model:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func main() {
    ctx := context.Background()

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey:  os.Getenv("MISTRAL_API_KEY"),
        BaseURL: "https://api.mistral.ai/v1",
        Model:   "pixtral-12b-2409",
    })
    if err != nil {
        log.Fatalf("failed to create Pixtral model: %v", err)
    }

    imageData, err := os.ReadFile("image.png")
    if err != nil {
        log.Fatalf("failed to read image: %v", err)
    }

    messages := []schema.Message{
        &schema.HumanMessage{
            Parts: []schema.ContentPart{
                schema.TextPart{Text: "What is in this image?"},
                schema.ImagePart{Data: imageData, MimeType: "image/png"},
            },
        },
    }

    response, err := model.Generate(ctx, messages)
    if err != nil {
        log.Fatalf("generation failed: %v", err)
    }

    fmt.Printf("Response: %s\n", response.Text())
}
```

Verify the setup:

```bash
export MISTRAL_API_KEY="your-api-key"
go run main.go
```

### Configuration Reference

`config.ProviderConfig` fields used with the `openai` provider:

| Field | Description | Default | Required |
|--------|-------------|---------|----------|
| `APIKey` | Mistral AI API key | - | Yes |
| `BaseURL` | Mistral's OpenAI-compatible endpoint, `https://api.mistral.ai/v1` | OpenAI's endpoint | Yes (for Mistral) |
| `Model` | Pixtral model name (e.g. `pixtral-12b-2409`, `pixtral-large-latest`) | - | Yes |
| `Timeout` | Per-request timeout | none (use a context deadline) | No |

## Usage

### Vision-Language Tasks

Pixtral supports several vision-language task patterns:

```go
import "github.com/lookatitude/beluga-ai/v2/schema"

// Image captioning (image only, no text prompt)
messages := []schema.Message{
    &schema.HumanMessage{
        Parts: []schema.ContentPart{
            schema.ImagePart{Data: imageData, MimeType: "image/png"},
        },
    },
}

// Visual question answering
messages = []schema.Message{
    &schema.HumanMessage{
        Parts: []schema.ContentPart{
            schema.TextPart{Text: "What color is the car in this image?"},
            schema.ImagePart{Data: imageData, MimeType: "image/jpeg"},
        },
    },
}

// Detailed scene analysis
messages = []schema.Message{
    &schema.HumanMessage{
        Parts: []schema.ContentPart{
            schema.TextPart{Text: "Analyze this image and describe the scene in detail."},
            schema.ImagePart{Data: imageData, MimeType: "image/png"},
        },
    },
}
```

### Using Pixtral with Agents

Use Pixtral as the backing model for a Beluga AI agent. Note that `agent.BaseAgent.Invoke` takes a text input; image inputs go through `model.Generate` directly:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/agent"
    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
)

func main() {
    ctx := context.Background()

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey:  os.Getenv("MISTRAL_API_KEY"),
        BaseURL: "https://api.mistral.ai/v1",
        Model:   "pixtral-12b-2409",
    })
    if err != nil {
        log.Fatalf("failed to create model: %v", err)
    }

    a := agent.New("vision-agent",
        agent.WithLLM(model),
        agent.WithPersona(agent.Persona{
            Role: "image analysis assistant",
            Goal: "describe and answer questions about images accurately",
        }),
    )

    // Agent.Invoke takes a text input. To send images, call model.Generate
    // with schema.ImagePart content parts as shown above.
    answer, err := a.Invoke(ctx, "Which image formats can you analyze?")
    if err != nil {
        log.Fatalf("agent failed: %v", err)
    }
    fmt.Println(answer)
}
```

## Advanced Topics

### OpenTelemetry Instrumentation

Add tracing to Pixtral calls:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"
    "time"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/schema"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

func main() {
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    cfg := config.ProviderConfig{
        APIKey:  os.Getenv("MISTRAL_API_KEY"),
        BaseURL: "https://api.mistral.ai/v1",
        Model:   "pixtral-12b-2409",
    }

    tracer := otel.Tracer("beluga.llm.pixtral")
    ctx, span := tracer.Start(ctx, "pixtral.generate",
        trace.WithAttributes(
            attribute.String("gen_ai.system", "mistral"),
            attribute.String("gen_ai.request.model", cfg.Model),
        ),
    )
    defer span.End()

    provider, err := llm.New("openai", cfg)
    if err != nil {
        span.RecordError(err)
        log.Fatalf("failed to create provider: %v", err)
    }

    messages := []schema.Message{
        &schema.HumanMessage{
            Parts: []schema.ContentPart{
                schema.TextPart{Text: "Describe this image in detail."},
                schema.ImagePart{Data: loadImage("image.png"), MimeType: "image/png"},
            },
        },
    }

    response, err := provider.Generate(ctx, messages)
    if err != nil {
        span.RecordError(err)
        log.Fatalf("generation failed: %v", err)
    }

    span.SetAttributes(
        attribute.Int("gen_ai.response.input_tokens", response.Usage.InputTokens),
        attribute.Int("gen_ai.response.output_tokens", response.Usage.OutputTokens),
    )

    fmt.Printf("Response: %s\n", response.Text())
}

func loadImage(path string) []byte {
    data, err := os.ReadFile(path)
    if err != nil {
        log.Fatalf("failed to load image: %v", err)
    }
    return data
}
```

### Production Considerations

When deploying Pixtral integrations to production:

- **Image optimization**: Resize and compress images before sending to reduce latency and cost. Pixtral supports PNG, JPEG, and WebP formats.
- **Cost management**: Monitor API usage through the Mistral AI dashboard. Image inputs consume more tokens than text.
- **Size limits**: Check Mistral's current per-image size limit and validate image size client-side before sending requests; Beluga does not enforce one.
- **Format validation**: Verify image format compatibility before sending. Unsupported formats return errors.
- **Error handling**: Use Beluga AI's `resilience` package for automatic retry on transient API failures.

## Troubleshooting

### "API key invalid"

The API key is incorrect or has been revoked.

```bash
# Verify the key is set
echo $MISTRAL_API_KEY

# Re-set from the Mistral AI dashboard
export MISTRAL_API_KEY="your-new-api-key"
```

### "Image format not supported"

The provided image format is not recognized by Pixtral. Supported formats are PNG, JPEG, and WebP. Convert the image before sending:

```go
// Ensure images are in a supported format before creating the content part
// Supported: image/png, image/jpeg, image/webp
```

## Related Resources

- [Google Vertex AI Vision](/docs/guides/production/integrations/vertex-ai-vision) -- Google Vertex AI multimodal integration
- [LLM Providers](/docs/reference/providers/llm/) -- All supported LLM providers
- [Monitoring](/docs/guides/production/monitoring-dashboards/) -- Observability and tracing setup
