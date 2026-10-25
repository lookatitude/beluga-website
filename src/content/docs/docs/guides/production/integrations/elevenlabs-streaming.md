---
title: ElevenLabs Streaming TTS
description: "Integrate ElevenLabs for natural text-to-speech with streaming, voice cloning, and 29-language support in Beluga AI pipelines."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "ElevenLabs, text-to-speech, TTS streaming, voice cloning, Beluga AI, multilingual TTS, Go TTS provider"
---

ElevenLabs produces some of the most natural-sounding synthetic voices available, making it the go-to choice when voice quality directly affects user experience -- customer-facing phone agents, audiobook narration, or branded voice assistants. Its voice cloning capability lets you create a custom voice from a small audio sample, and multilingual support covers 29 languages with a single model. This guide covers integrating ElevenLabs as a TTS provider within Beluga AI.

## Overview

The ElevenLabs integration uses the `voice/tts` package registry to create a streaming TTS provider. It supports voice and model selection through `tts.Config`, and streaming synthesis over a stream of text chunks.

## Prerequisites

- Go 1.26 or later
- ElevenLabs API key (from [elevenlabs.io](https://elevenlabs.io))

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Set your API key:

```bash
export ELEVENLABS_API_KEY="your-api-key"
```

## Configuration

The ElevenLabs provider registers itself as `"elevenlabs"` with the `tts` registry when you blank-import it. The API key goes in `tts.Config.Extra`:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/tts"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

func main() {
    ctx := context.Background()

    engine, err := tts.New("elevenlabs", tts.Config{
        Voice: "21m00Tcm4TlvDq8ikWAM", // Rachel
        Extra: map[string]any{"api_key": os.Getenv("ELEVENLABS_API_KEY")},
    })
    if err != nil {
        log.Fatalf("Failed to create provider: %v", err)
    }

    audio, err := engine.Synthesize(ctx, "Hello, this is a test of ElevenLabs text-to-speech.")
    if err != nil {
        log.Fatalf("Generation failed: %v", err)
    }

    fmt.Printf("Generated %d bytes of audio\n", len(audio))
}
```

## Usage

### Voice and Model Selection

Set the voice and model on the config, or override them per call with options:

```go
engine, err := tts.New("elevenlabs", tts.Config{
    Voice: "your-voice-id",
    Model: "eleven_multilingual_v2",
    Extra: map[string]any{"api_key": os.Getenv("ELEVENLABS_API_KEY")},
})
if err != nil {
    log.Fatalf("Failed to create provider: %v", err)
}

audio, err := engine.Synthesize(ctx, "Hola!", tts.WithVoice("another-voice-id"))
if err != nil {
    log.Fatalf("Generation failed: %v", err)
}
```

The provider currently sends fixed voice settings (stability `0.5`, similarity boost `0.75`); they are not configurable through `tts.Config`.

### Streaming Audio Generation

`SynthesizeStream` takes an `iter.Seq2[string, error]` of text chunks (for example, sentences from an LLM stream) and yields one audio buffer per chunk, so playback can start before the full response is ready:

```go
func streamAudio(ctx context.Context, engine tts.TTS, sentences iter.Seq2[string, error], play func([]byte) error) error {
    for chunk, err := range engine.SynthesizeStream(ctx, sentences) {
        if err != nil {
            return fmt.Errorf("synthesize: %w", err)
        }
        if err := play(chunk); err != nil {
            return fmt.Errorf("play: %w", err)
        }
    }
    return nil
}
```

In a voice pipeline, use `tts.AsFrameProcessor(engine, 24000)` as the TTS stage.

### Observability

Add OpenTelemetry tracing:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

tracer := otel.Tracer("beluga.voice.tts.elevenlabs")
ctx, span := tracer.Start(ctx, "elevenlabs.generate",
    trace.WithAttributes(
        attribute.String("voice_id", "21m00Tcm4TlvDq8ikWAM"),
    ),
)
defer span.End()
```

## Configuration Reference

| Field               | Description           | Default                    | Required |
|---------------------|-----------------------|----------------------------|----------|
| `Extra["api_key"]`  | ElevenLabs API key    | -                          | Yes      |
| `Extra["base_url"]` | Custom API base URL   | `https://api.elevenlabs.io/v1` | No   |
| `Voice`             | Voice identifier      | `21m00Tcm4TlvDq8ikWAM` (Rachel) | No  |
| `Model`             | Model identifier      | `eleven_monolingual_v1`    | No       |

## Troubleshooting

### API key invalid

Verify your API key is correct and active in the ElevenLabs dashboard.

### Voice not found

Check that the voice ID exists. List available voices through the ElevenLabs API or dashboard to find valid IDs.

## Advanced Topics

### Production Deployment

- Use voice cloning for custom brand voices
- Enable streaming for low-latency audio generation
- Monitor API usage for cost management
- Implement retry logic for transient API failures

## Related Resources

- [Azure Cognitive Services Speech](/docs/guides/production/integrations/azure-speech)
- [Voice Services Overview](/docs/reference/providers/voice/)
