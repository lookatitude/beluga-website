---
title: Deepgram Live Streaming STT
description: "Integrate Deepgram Nova-2 for sub-300ms real-time speech-to-text with WebSocket streaming and diarization in Beluga AI."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Deepgram, speech-to-text, live streaming, WebSocket STT, Beluga AI, Nova-2, real-time transcription Go"
---

Deepgram is the default STT choice for real-time voice applications that prioritize low latency. Its Nova-2 model consistently delivers sub-300ms transcription with high accuracy, and interim results let your agent begin processing before the speaker finishes. Deepgram also supports punctuation, speaker diarization, and 36+ languages out of the box. This guide covers integrating the Deepgram STT provider with Beluga AI for live transcription.

## Overview

The Deepgram integration uses the `voice/stt` package to connect to Deepgram's streaming API. It supports multiple models (Nova-2 for accuracy, Base for speed), punctuation, speaker diarization, and interim results.

## Prerequisites

- Go 1.26 or later
- Deepgram API key (from [deepgram.com](https://deepgram.com))

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Set your API key:

```bash
export DEEPGRAM_API_KEY="your-api-key"
```

## Configuration

The Deepgram provider registers itself as `"deepgram"` with the `stt` registry when you blank-import it. The API key goes in `stt.Config.Extra`:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
)

func main() {
    ctx := context.Background()

    engine, err := stt.New("deepgram", stt.Config{
        Language:    "en",
        Model:       "nova-2",
        Punctuation: true,
        Extra:       map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
    })
    if err != nil {
        log.Fatalf("Failed to create provider: %v", err)
    }

    audio, err := os.ReadFile("sample.wav")
    if err != nil {
        log.Fatalf("Failed to read audio: %v", err)
    }

    transcript, err := engine.Transcribe(ctx, audio)
    if err != nil {
        log.Fatalf("Transcription failed: %v", err)
    }

    fmt.Printf("Transcript: %s\n", transcript)
}
```

## Usage

### Streaming Transcription

`TranscribeStream` uses Deepgram's WebSocket API. It takes an `iter.Seq2[[]byte, error]` of audio chunks and yields `stt.TranscriptEvent` values; interim results have `IsFinal == false`:

```go
func streamTranscription(ctx context.Context, engine stt.STT, audio iter.Seq2[[]byte, error]) error {
    for event, err := range engine.TranscribeStream(ctx, audio, stt.WithSampleRate(16000), stt.WithEncoding("linear16")) {
        if err != nil {
            return fmt.Errorf("stream: %w", err)
        }
        if event.IsFinal {
            fmt.Printf("final: %s (%.2f)\n", event.Text, event.Confidence)
        } else {
            fmt.Printf("interim: %s\n", event.Text)
        }
    }
    return nil
}
```

### Voice Pipeline Integration

Wrap the engine with `stt.AsFrameProcessor` to use it as the STT stage of a `voice.VoicePipeline`:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
)

engine, err := stt.New("deepgram", stt.Config{
    Model: "nova-2",
    Extra: map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
})
if err != nil {
    log.Fatalf("Failed to create STT provider: %v", err)
}

pipe := voice.NewPipeline(
    voice.WithTransport(transport), // your voice.Transport
    voice.WithVAD(voice.NewEnergyVAD(voice.EnergyVADConfig{Threshold: 1000})),
    voice.WithSTT(stt.AsFrameProcessor(engine)),
    voice.WithLLM(llmStage), // your text-to-text voice.FrameProcessor
    voice.WithTTS(ttsStage),
)
if err := pipe.Run(ctx); err != nil {
    log.Fatalf("pipeline: %v", err)
}
```

### Observability

Add OpenTelemetry tracing:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

tracer := otel.Tracer("beluga.voice.stt.deepgram")
ctx, span := tracer.Start(ctx, "deepgram.transcribe",
    trace.WithAttributes(
        attribute.String("model", "nova-2"),
    ),
)
defer span.End()
```

## Configuration Reference

| Field                | Description           | Default  | Required |
|----------------------|-----------------------|----------|----------|
| `Extra["api_key"]`   | Deepgram API key      | -        | Yes      |
| `Extra["base_url"]`  | Custom REST base URL  | -        | No       |
| `Extra["ws_url"]`    | Custom WebSocket URL  | -        | No       |
| `Model`              | Deepgram model        | `nova-2` | No       |
| `Language`           | Language code         | -        | No       |
| `Punctuation`        | Add punctuation       | `false`  | No       |
| `Diarization`        | Speaker diarization   | `false`  | No       |

## Troubleshooting

### API key invalid

Verify your API key is correct and active in the Deepgram dashboard.

### WebSocket connection failed

Check network connectivity and firewall rules. Deepgram uses WebSocket connections that may be blocked by corporate firewalls.

## Advanced Topics

### Production Deployment

- Use WebSocket streaming for all real-time use cases
- Select the appropriate model: `nova-2` for accuracy, `base` for speed
- Monitor API usage through the Deepgram dashboard
- Implement reconnection logic for connection drops
- Optimize chunk size and frequency for your latency requirements

## Related Resources

- [Amazon Transcribe WebSockets](/docs/guides/production/integrations/transcribe-websockets)
- [Voice Services Overview](/docs/reference/providers/voice/)
