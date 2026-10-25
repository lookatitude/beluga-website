---
title: Azure Speech TTS Integration
description: "Integrate Azure Cognitive Services Speech for neural TTS with 400+ voices, SSML support, and 140 languages in Beluga AI."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Azure Speech, neural TTS, SSML, Beluga AI, Azure Cognitive Services, text-to-speech Go, enterprise voice"
---

Azure Cognitive Services Speech is the strongest TTS option for enterprises already invested in the Microsoft ecosystem. It offers the widest selection of neural voices (400+ across 140 languages), full SSML support for fine-grained prosody control, and deployment within Azure's compliance boundary. Choose Azure Speech when you need enterprise-grade voice synthesis with SSML customization or when regulatory requirements demand that audio processing stays within Azure. This guide shows how to plug Azure Speech into Beluga AI as a custom TTS provider.

## Overview

Beluga AI does not ship an Azure Speech provider. The `voice/tts` package is an open registry, though: any type that implements the `tts.TTS` interface (`Synthesize` and `SynthesizeStream`) can be registered under a name with `tts.Register` and then created with `tts.New`, exactly like the built-in providers (`elevenlabs`, `cartesia`, `playht`, and others). This guide shows a small custom provider backed by the Azure Speech REST API, which accepts SSML and returns audio in the format you request.

## Prerequisites

- Go 1.26 or later
- Azure account with a Speech Services resource
- Azure subscription key and region

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Set environment variables:

```bash
export AZURE_SPEECH_KEY="your-key"
export AZURE_SPEECH_REGION="eastus"
```

## Configuration

The provider below reads its key and region from `tts.Config.Extra`, uses `tts.Config.Voice` for the voice name, and registers itself as `"azure"`:

```go
package main

import (
    "bytes"
    "context"
    "fmt"
    "html"
    "io"
    "iter"
    "log"
    "net/http"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/tts"
)

// AzureTTS implements tts.TTS using the Azure Speech REST API.
type AzureTTS struct {
    key, region string
    cfg         tts.Config
}

var _ tts.TTS = (*AzureTTS)(nil)

func init() {
    tts.Register("azure", func(cfg tts.Config) (tts.TTS, error) {
        key, _ := cfg.Extra["api_key"].(string)
        region, _ := cfg.Extra["region"].(string)
        if key == "" || region == "" {
            return nil, fmt.Errorf("azure tts: api_key and region are required in Extra")
        }
        if cfg.Voice == "" {
            cfg.Voice = "en-US-JennyNeural"
        }
        return &AzureTTS{key: key, region: region, cfg: cfg}, nil
    })
}

// Synthesize wraps plain text in SSML and sends it to Azure.
func (a *AzureTTS) Synthesize(ctx context.Context, text string, opts ...tts.Option) ([]byte, error) {
    cfg := a.cfg
    for _, opt := range opts {
        opt(&cfg)
    }
    ssml := fmt.Sprintf(`<speak version="1.0" xml:lang="en-US"><voice name="%s">%s</voice></speak>`,
        cfg.Voice, html.EscapeString(text))
    return a.SynthesizeSSML(ctx, ssml)
}

// SynthesizeSSML sends a complete SSML document to Azure.
func (a *AzureTTS) SynthesizeSSML(ctx context.Context, ssml string) ([]byte, error) {
    url := fmt.Sprintf("https://%s.tts.speech.microsoft.com/cognitiveservices/v1", a.region)
    req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewBufferString(ssml))
    if err != nil {
        return nil, fmt.Errorf("azure tts: create request: %w", err)
    }
    req.Header.Set("Ocp-Apim-Subscription-Key", a.key)
    req.Header.Set("Content-Type", "application/ssml+xml")
    req.Header.Set("X-Microsoft-OutputFormat", "raw-16khz-16bit-mono-pcm")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("azure tts: request failed: %w", err)
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("azure tts: read response: %w", err)
    }
    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("azure tts: status %d: %s", resp.StatusCode, body)
    }
    return body, nil
}

// SynthesizeStream synthesizes each incoming text chunk in turn.
func (a *AzureTTS) SynthesizeStream(ctx context.Context, textStream iter.Seq2[string, error], opts ...tts.Option) iter.Seq2[[]byte, error] {
    return func(yield func([]byte, error) bool) {
        for text, err := range textStream {
            if err != nil {
                yield(nil, err)
                return
            }
            if text == "" {
                continue
            }
            audio, err := a.Synthesize(ctx, text, opts...)
            if !yield(audio, err) || err != nil {
                return
            }
        }
    }
}

func main() {
    ctx := context.Background()

    engine, err := tts.New("azure", tts.Config{
        Voice: "en-US-JennyNeural",
        Extra: map[string]any{
            "api_key": os.Getenv("AZURE_SPEECH_KEY"),
            "region":  os.Getenv("AZURE_SPEECH_REGION"),
        },
    })
    if err != nil {
        log.Fatalf("Failed to create provider: %v", err)
    }

    audio, err := engine.Synthesize(ctx, "Hello from Azure Cognitive Services.")
    if err != nil {
        log.Fatalf("Speech generation failed: %v", err)
    }

    fmt.Printf("Generated %d bytes of audio\n", len(audio))
}
```

Because the provider is registered, it plugs into the voice pipeline like any other engine: `voice.WithTTS(tts.AsFrameProcessor(engine, 16000))`.

## Usage

### SSML Support

`SynthesizeSSML` is a method of the custom type, not part of the `tts.TTS` interface, so type-assert to reach it:

```go
ssml := `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="en-US-JennyNeural">
        <prosody rate="fast" pitch="high">
            Hello, this is SSML text-to-speech.
        </prosody>
    </voice>
</speak>`

azure, ok := engine.(*AzureTTS)
if !ok {
    log.Fatal("engine is not an *AzureTTS")
}
audio, err := azure.SynthesizeSSML(ctx, ssml)
if err != nil {
    log.Fatalf("SSML generation failed: %v", err)
}
```

### Observability

Add OpenTelemetry tracing around calls:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

tracer := otel.Tracer("beluga.voice.tts.azure")
ctx, span := tracer.Start(ctx, "azure.generate",
    trace.WithAttributes(
        attribute.String("voice", "en-US-JennyNeural"),
        attribute.String("region", os.Getenv("AZURE_SPEECH_REGION")),
    ),
)
defer span.End()
```

## Configuration Reference

| Field             | Description                   | Default              | Required |
|-------------------|-------------------------------|----------------------|----------|
| `Extra["api_key"]`| Azure Speech subscription key | -                    | Yes      |
| `Extra["region"]` | Azure region (e.g. `eastus`)  | -                    | Yes      |
| `Voice`           | Neural voice name             | `en-US-JennyNeural`  | No       |

## Troubleshooting

### Invalid subscription key

Verify the key in the Azure portal under your Speech Services resource. Ensure the key matches the configured region.

### Region not found

Use a valid Azure region such as `eastus`, `westus2`, or `westeurope`. The region must match the region where your Speech Services resource was created.

## Advanced Topics

### Production Deployment

- Use neural voices for the best audio quality
- Leverage SSML for fine-grained prosody and style control
- Monitor usage through the Azure portal for cost management
- Deploy the Speech Services resource in a region close to your users
- Implement retry logic for transient Azure API failures

## Related Resources

- [ElevenLabs Streaming API](/docs/guides/production/integrations/elevenlabs-streaming)
- [Voice Services Overview](/docs/reference/providers/voice/)
