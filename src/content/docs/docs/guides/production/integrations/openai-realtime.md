---
title: OpenAI Realtime Voice API
description: "Integrate OpenAI Realtime API for sub-second speech-to-speech conversations with tool calling in Beluga AI voice pipelines."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "OpenAI Realtime, speech-to-speech, low-latency voice, Beluga AI, GPT-4o voice, WebSocket audio, Go S2S provider"
---

OpenAI Realtime is the lowest-latency option for speech-to-speech conversations that also need tool calling and reasoning capabilities. Because the model processes audio natively rather than transcribing first, it preserves tone and nuance while delivering sub-second response times. Choose this provider when conversational quality and built-in function calling matter more than infrastructure lock-in. This guide covers integrating the OpenAI Realtime S2S provider with Beluga AI for end-to-end voice interactions.

## Overview

The OpenAI Realtime integration uses the `voice/s2s` package to enable bidirectional audio streaming over WebSocket. The provider lives in `voice/s2s/providers/openai` and registers itself as `"openai_realtime"`. It supports configurable voices and models, instructions, tool calls, and server-side VAD for turn detection.

## Prerequisites

- Go 1.26 or later
- OpenAI API key with Realtime API access
- Understanding of WebSocket streaming concepts

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Set your API key:

```bash
export OPENAI_API_KEY="sk-..."
```

## Configuration

Create an OpenAI Realtime engine through the `s2s` registry and start a session:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/s2s"
    _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
)

func main() {
    ctx := context.Background()

    engine, err := s2s.New("openai_realtime", s2s.Config{
        Model:        "gpt-4o-realtime-preview",
        Voice:        "alloy",
        Instructions: "You are a helpful assistant.",
        Extra:        map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
    })
    if err != nil {
        log.Fatalf("Failed to create provider: %v", err)
    }

    session, err := engine.Start(ctx)
    if err != nil {
        log.Fatalf("Failed to start session: %v", err)
    }
    defer session.Close()

    fmt.Println("Realtime session started")
}
```

## Usage

### Bidirectional Audio Streaming

Send PCM16 audio with `SendAudio` and consume `s2s.SessionEvent` values from `Recv`. Tool calls arrive as `EventToolCall`; answer them with `SendToolResult`:

```go
func handleSession(ctx context.Context, session s2s.Session, audioIn <-chan []byte, play func([]byte)) error {
    go func() {
        for audio := range audioIn {
            if err := session.SendAudio(ctx, audio); err != nil {
                log.Printf("Send error: %v", err)
                return
            }
        }
    }()

    for event, err := range session.Recv(ctx) {
        if err != nil {
            return err
        }
        switch event.Type {
        case s2s.EventAudioOutput:
            play(event.Audio)
        case s2s.EventToolCall:
            result := schema.ToolResult{CallID: event.ToolCall.ID, Content: []schema.ContentPart{schema.TextPart{Text: "42"}}}
            if err := session.SendToolResult(ctx, result); err != nil {
                return err
            }
        case s2s.EventError:
            return event.Error
        }
    }
    return nil
}
```

To use the engine as a stage in a voice pipeline, wrap it with `s2s.AsFrameProcessor(engine)`.

### Observability

Add OpenTelemetry tracing:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

tracer := otel.Tracer("beluga.voice.s2s.openai_realtime")
ctx, span := tracer.Start(ctx, "openai_realtime.start",
    trace.WithAttributes(
        attribute.String("model", "gpt-4o-realtime-preview"),
        attribute.String("voice", "alloy"),
    ),
)
defer span.End()
```

## Configuration Reference

| Field               | Description               | Default                              | Required |
|---------------------|---------------------------|--------------------------------------|----------|
| `Extra["api_key"]`  | OpenAI API key            | -                                    | Yes      |
| `Extra["base_url"]` | Custom WebSocket endpoint | `wss://api.openai.com/v1/realtime`   | No       |
| `Model`             | Realtime model            | `gpt-4o-realtime-preview`            | No       |
| `Voice`             | Voice selection           | `alloy`                              | No       |
| `Instructions`      | System instructions       | -                                    | No       |
| `Tools`             | `[]schema.ToolDefinition` | -                                    | No       |

## Troubleshooting

### API key invalid

Verify your API key has Realtime API access enabled. Standard API keys may not include Realtime capabilities.

### WebSocket connection failed

Check network connectivity and firewall rules. The Realtime API uses WebSocket connections that some corporate firewalls may block.

## Advanced Topics

### Production Deployment

- Optimize audio settings for your latency requirements
- Monitor API usage through the OpenAI dashboard for cost management
- Implement reconnection logic for WebSocket drops
- Configure appropriate context timeouts for streaming sessions
- Use streaming mode for all real-time conversation scenarios

## Related Resources

- [Amazon Nova Bedrock Streaming](/docs/guides/production/integrations/nova-bedrock-streaming)
- [Voice Services Overview](/docs/guides/production/integrations/voice-services)
