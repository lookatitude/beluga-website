---
title: Google Vertex AI Multimodal
description: "Call Gemini models on Vertex AI from Beluga AI through Vertex AI's OpenAI-compatible endpoint, with text and image inputs in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Vertex AI, Google Gemini, multimodal AI Go, enterprise LLM, Beluga AI, Google Cloud AI, VPC Service Controls"
---

Organizations already invested in Google Cloud often need their AI workloads to run within the same security perimeter -- VPC Service Controls, IAM policies, audit logging, and CMEK encryption. Vertex AI provides Gemini model access through Google Cloud's managed platform, giving you enterprise controls that the public Gemini API does not offer.

Choose Vertex AI over the public Gemini API when you need data residency guarantees, network isolation via VPC, or when your security team requires IAM-based access control rather than API keys.

## Overview

Vertex AI is Google Cloud's managed AI platform. Beluga AI reaches Gemini models on Vertex AI as follows:

- **Vertex AI**: through Vertex AI's OpenAI-compatible Chat Completions endpoint, using Beluga's `openai` provider with a custom `BaseURL` and a Google Cloud OAuth access token.
- **Public Gemini API**: through Beluga's native `google` provider (`llm/providers/google`), which uses an API key.

:::caution[Current limitations]
- Beluga's `google` provider talks to the public **Gemini API** only (it always uses the Gemini API backend of the `genai` SDK). It has no Vertex AI mode, project ID, or location settings.
- Both paths send **text and image** content parts. `schema.AudioPart` and `schema.VideoPart` are currently dropped by both providers, so audio and video inputs are not supported through Beluga today.
:::

What Vertex AI adds on top of the model itself:

- **Enterprise controls** including VPC Service Controls, CMEK, audit logging, and IAM-based access
- **Regional endpoints** for data residency and latency requirements

## Prerequisites

- Go 1.26 or later
- A Google Cloud project with the Vertex AI API enabled
- The `gcloud` CLI, with credentials that have the `roles/aiplatform.user` role
- Beluga AI framework installed

## Installation

No extra Go dependencies are needed beyond the framework:

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Vertex AI's OpenAI-compatible endpoint authenticates with an OAuth access token:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
export VERTEX_ACCESS_TOKEN="$(gcloud auth print-access-token)"
```

## Configuration

### Basic Setup

Create an `openai` provider pointed at your project's Vertex AI endpoint:

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

    project := os.Getenv("GOOGLE_CLOUD_PROJECT")
    location := os.Getenv("GOOGLE_CLOUD_LOCATION")

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("VERTEX_ACCESS_TOKEN"),
        BaseURL: fmt.Sprintf(
            "https://%s-aiplatform.googleapis.com/v1/projects/%s/locations/%s/endpoints/openapi",
            location, project, location,
        ),
        Model: "google/gemini-2.0-flash-001",
    })
    if err != nil {
        log.Fatalf("failed to create Vertex AI model: %v", err)
    }

    resp, err := model.Generate(ctx, []schema.Message{
        schema.NewHumanMessage("Say hello from Vertex AI."),
    })
    if err != nil {
        log.Fatalf("generation failed: %v", err)
    }
    fmt.Println(resp.Text())
}
```

Verify the setup:

```bash
go run main.go
```

### Configuration Reference

`config.ProviderConfig` fields used with the `openai` provider:

| Field | Description | Required |
|--------|-------------|----------|
| `APIKey` | Google Cloud OAuth access token (sent as a Bearer token) | Yes |
| `BaseURL` | `https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints/openapi` | Yes |
| `Model` | Vertex AI model ID, prefixed with `google/` (e.g. `google/gemini-2.0-flash-001`) | Yes |
| `Timeout` | Per-request timeout | No |

To use the public Gemini API instead, use the native provider: `llm.New("google", config.ProviderConfig{APIKey: os.Getenv("GEMINI_API_KEY"), Model: "gemini-2.5-flash"})` with `_ "github.com/lookatitude/beluga-ai/v2/llm/providers/google"`.

## Usage

### Image Inputs

Build multimodal messages with `schema.HumanMessage` and content parts. Inline image bytes are sent as a base64 data URI; a `URL` is passed through:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/schema"
)

// Text + inline image
msg := &schema.HumanMessage{
    Parts: []schema.ContentPart{
        schema.TextPart{Text: "Analyze this image"},
        schema.ImagePart{Data: imageData, MimeType: "image/png"},
    },
}

// Text + image by URL
msg = &schema.HumanMessage{
    Parts: []schema.ContentPart{
        schema.TextPart{Text: "What does this chart show?"},
        schema.ImagePart{URL: "https://example.com/chart.png"},
    },
}
```

### Enterprise Features

Requests go to your project's regional Vertex AI endpoint, so VPC Service Controls, audit logging, and organization-level policies configured for Vertex AI in that project apply to them. Choose the region in `BaseURL` to match your data residency requirements.

## Advanced Topics

### OpenTelemetry Instrumentation

Add tracing to Vertex AI calls:

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

    project := os.Getenv("GOOGLE_CLOUD_PROJECT")
    location := os.Getenv("GOOGLE_CLOUD_LOCATION")
    cfg := config.ProviderConfig{
        APIKey: os.Getenv("VERTEX_ACCESS_TOKEN"),
        BaseURL: fmt.Sprintf(
            "https://%s-aiplatform.googleapis.com/v1/projects/%s/locations/%s/endpoints/openapi",
            location, project, location,
        ),
        Model: "google/gemini-2.0-flash-001",
    }

    tracer := otel.Tracer("beluga.multimodal.vertex_ai")
    ctx, span := tracer.Start(ctx, "vertex_ai.process",
        trace.WithAttributes(
            attribute.String("gen_ai.system", "vertex_ai"),
            attribute.String("gen_ai.request.model", cfg.Model),
            attribute.String("gcp.project_id", project),
        ),
    )
    defer span.End()

    model, err := llm.New("openai", cfg)
    if err != nil {
        span.RecordError(err)
        log.Fatalf("failed to create model: %v", err)
    }

    image, err := os.ReadFile("image.png")
    if err != nil {
        span.RecordError(err)
        log.Fatalf("failed to load image: %v", err)
    }

    messages := []schema.Message{
        &schema.HumanMessage{
            Parts: []schema.ContentPart{
                schema.TextPart{Text: "Describe this image in detail."},
                schema.ImagePart{Data: image, MimeType: "image/png"},
            },
        },
    }

    response, err := model.Generate(ctx, messages)
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
```

### Production Considerations

When deploying Vertex AI integrations to production:

- **IAM roles**: Use dedicated service accounts with the `roles/aiplatform.user` role. Avoid using owner or editor roles.
- **Regional deployment**: Choose a region that matches your data residency requirements and provides acceptable latency.
- **Cost optimization**: Monitor usage through Cloud Billing. Use Gemini Flash models for latency-sensitive or cost-sensitive workloads.
- **Token refresh**: OAuth access tokens expire (typically after one hour). Rebuild the model with a fresh token before expiry, or front Vertex AI with a gateway that handles Google auth.
- **VPC Service Controls**: Configure a service perimeter around your Vertex AI resources to prevent data exfiltration.
- **Error handling**: Handle quota errors (HTTP 429) with exponential backoff using Beluga AI's `resilience` package.

## Troubleshooting

### "Project not found"

The Google Cloud project ID is incorrect or the Vertex AI API is not enabled.

```bash
# Verify the project exists and you have access
gcloud projects describe your-project-id

# Enable the Vertex AI API
gcloud services enable aiplatform.googleapis.com --project=your-project-id
```

### "Authentication failed" (HTTP 401)

The access token is missing, invalid, or expired. Access tokens are short-lived; fetch a new one with `gcloud auth print-access-token`.

```bash
# Check current credentials
gcloud auth application-default print-access-token

# Re-authenticate
gcloud auth application-default login
```

## Related Resources

- [Pixtral (Mistral) Integration](/docs/guides/production/integrations/pixtral-mistral) -- Mistral AI vision-language integration
- [LLM Providers](/docs/reference/providers/llm/) -- All supported LLM providers
- [Monitoring](/docs/guides/production/monitoring-dashboards/) -- Observability and tracing setup
