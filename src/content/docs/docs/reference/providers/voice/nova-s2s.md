---
title: "Amazon Nova S2S Voice Provider"
description: "Amazon Nova Sonic S2S for bidirectional audio streaming in Beluga AI. AWS Bedrock speech-to-speech with tool use and low latency in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Amazon Nova, speech-to-speech, S2S, AWS Bedrock, bidirectional audio, tool use, Go, Beluga AI"
---

Amazon Nova provides native speech-to-speech via the AWS Bedrock Runtime API with Nova Sonic. The provider calls Bedrock's `InvokeModelWithBidirectionalStream` API through `aws-sdk-go-v2` (an HTTP/2 event stream, SigV4-signed by the SDK), supporting tool calling, input transcription, and barge-in detected by Nova from the audio stream.

Choose Amazon Nova S2S when your infrastructure is AWS-native and you want speech-to-speech without leaving the AWS ecosystem. Nova Sonic uses AWS IAM authentication and connects through Bedrock Runtime, fitting naturally into existing AWS deployments. For a provider-agnostic alternative, consider [OpenAI Realtime](/docs/reference/providers/voice/openai-realtime) or [Gemini Live](/docs/reference/providers/voice/gemini-live).

## Installation

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/nova"
```

The blank import registers the `"nova"` provider with the S2S registry.

## Configuration

| Field          | Type                      | Default                      | Description                          |
|----------------|---------------------------|------------------------------|--------------------------------------|
| `Model`        | `string`                  | `"amazon.nova-sonic-v1:0"`   | Nova model identifier                |
| `Voice`        | `string`                  | `"matthew"`                  | Output voice                         |
| `SampleRate`   | `int`                     | `16000`                      | Input PCM sample rate (Hz)           |
| `Instructions` | `string`                  | —                            | System prompt for the session        |
| `Tools`        | `[]schema.ToolDefinition` | —                            | Tools available to the model         |
| `Extra`        | —                         | —                            | See below                            |

### Extra Fields

| Key                 | Type     | Required | Description                                                        |
|---------------------|----------|----------|--------------------------------------------------------------------|
| `region`            | `string` | No       | AWS region (default: `"us-east-1"`)                                |
| `access_key_id`     | `string` | No       | Static AWS access key ID (default AWS credential chain otherwise)  |
| `secret_access_key` | `string` | No       | Static AWS secret access key, used with `access_key_id`            |
| `session_token`     | `string` | No       | Optional session token for temporary static credentials            |
| `base_url`          | `string` | No       | Bedrock Runtime endpoint override; must be `http://` or `https://` |

## Authentication

Amazon Nova uses AWS IAM authentication, and every request is signed with SigV4 by `aws-sdk-go-v2`. When `Extra["access_key_id"]` is set, the provider uses those static credentials (with `secret_access_key` and the optional `session_token`). Otherwise it loads the default AWS credential chain: environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`), shared config and credentials files, or an IAM role. The region always comes from `Extra["region"]`.

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/voice/s2s"
    _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/nova"
)

func main() {
    ctx := context.Background()

    engine, err := s2s.New("nova", s2s.Config{
        Model: "amazon.nova-sonic-v1:0",
        Extra: map[string]any{"region": "us-east-1"},
    })
    if err != nil {
        log.Fatal(err)
    }

    session, err := engine.Start(ctx)
    if err != nil {
        log.Fatal(err)
    }
    defer session.Close()

    // Send audio to the session
    if err := session.SendAudio(ctx, audioChunk); err != nil {
        log.Fatal(err)
    }

    // Receive events
    for event, err := range session.Recv(ctx) {
        if err != nil {
            log.Printf("session: %v", err)
            break
        }
        switch event.Type {
        case s2s.EventAudioOutput:
            playAudio(event.Audio)
        case s2s.EventTextOutput:
            fmt.Printf("Agent: %s", event.Text)
        case s2s.EventTranscript:
            fmt.Printf("User said: %s\n", event.Text)
        case s2s.EventToolCall:
            fmt.Printf("Tool call: %s(%s)\n", event.ToolCall.Name, event.ToolCall.Arguments)
        case s2s.EventTurnEnd:
            fmt.Println("--- turn complete ---")
        case s2s.EventError:
            log.Printf("error: %v", event.Error)
        }
    }
}
// audioChunk is PCM16 audio captured from your microphone or transport.
var audioChunk []byte

// playAudio writes synthesized PCM16 audio to your output device or transport.
func playAudio(pcm []byte) {
    fmt.Printf("received %d bytes of audio\n", len(pcm))
}
```

## Direct Construction

```go
import "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/nova"

engine, err := nova.New(s2s.Config{
    Model:        "amazon.nova-sonic-v1:0",
    Instructions: "You are a helpful voice assistant.",
    Extra:        map[string]any{"region": "us-west-2"},
})
```

## Session Lifecycle

1. **Start**: Opens an `InvokeModelWithBidirectionalStream` stream and sends `sessionStart`, `promptStart` (24 kHz LPCM audio output, text and tool-use output configuration, tools), the system prompt as a `SYSTEM` text content block when instructions are set, and an interactive `USER` `AUDIO` content block.
2. **Audio I/O**: `SendAudio` streams 16-bit mono LPCM (16 kHz unless `Config.SampleRate` says otherwise) on the open audio block. `audioOutput` events surface as `EventAudioOutput`.
3. **Text**: `SendText` sends its own text content block. `FINAL`-stage assistant `textOutput` surfaces as `EventTextOutput`; `SPECULATIVE` previews are dropped.
4. **Tool Calls**: `toolUse` events surface as `EventToolCall`. Send results back via `SendToolResult`, which sends its own tool-result content block.
5. **Turn end**: `contentEnd` with stop reason `END_TURN` or `INTERRUPTED` surfaces as `EventTurnEnd`.
6. **Close**: Sends `contentEnd`, `promptEnd`, and `sessionEnd`, then closes the stream.

## Tool Calling

```go
session, err := engine.Start(ctx,
    s2s.WithInstructions("You have access to a knowledge base."),
    s2s.WithTools([]schema.ToolDefinition{
        {
            Name:        "lookup",
            Description: "Look up information in the knowledge base",
            InputSchema: map[string]any{
                "type": "object",
                "properties": map[string]any{
                    "query": map[string]any{"type": "string"},
                },
                "required": []string{"query"},
            },
        },
    }),
)

for event, err := range session.Recv(ctx) {
    if err != nil {
        log.Printf("session: %v", err)
        break
    }
    if event.Type == s2s.EventToolCall {
        result := lookupKnowledgeBase(event.ToolCall.Arguments)
        if err := session.SendToolResult(ctx, schema.ToolResult{
            CallID:  event.ToolCall.ID,
            Content: []schema.ContentPart{schema.TextPart{Text: result}},
        }); err != nil {
            log.Printf("send tool result: %v", err)
        }
    }
}
```

## FrameProcessor Integration

```go
processor := s2s.AsFrameProcessor(engine,
    s2s.WithModel("amazon.nova-sonic-v1:0"),
    s2s.WithInstructions("You are a helpful voice assistant."),
)
pipeline := voice.Chain(vadProcessor, processor)
```

## Advanced Features

### User Interruption

Nova detects barge-in itself from the input audio stream and ends the assistant turn with stop reason `INTERRUPTED`, which arrives as `EventTurnEnd`. There is no client-side interrupt event, so `Interrupt` is a no-op on an open session (it returns an error only after `Close`). Stop local playback when you see the turn end:

```go
if err := session.Interrupt(ctx); err != nil {
    log.Printf("interrupt error: %v", err)
}
```

### Input Transcription

Nova emits `USER` `textOutput` events with the user's speech transcribed to text, accessible via `EventTranscript` events in the session.

### AWS Region Selection

The Bedrock Runtime client is created for `Extra["region"]` (default `us-east-1`); the AWS SDK resolves the regional Bedrock Runtime endpoint.

```go
engine, err := s2s.New("nova", s2s.Config{
    Model: "amazon.nova-sonic-v1:0",
    Extra: map[string]any{"region": "eu-west-1"},
})
```

### Custom Endpoint

For VPC endpoints or custom deployments, set `base_url` to an `http(s)` Bedrock Runtime endpoint. Other schemes, including the legacy `wss://` WebSocket URL, are rejected by `New`:

```go
engine, err := s2s.New("nova", s2s.Config{
    Model: "amazon.nova-sonic-v1:0",
    Extra: map[string]any{
        "region":   "us-east-1",
        "base_url": "https://bedrock-runtime.vpce.internal.corp",
    },
})
```

### Per-Session Options

```go
session, err := engine.Start(ctx,
    s2s.WithModel("amazon.nova-sonic-v1:0"),
    s2s.WithInstructions("You are a customer service agent."),
    s2s.WithTools(toolDefs),
)
```
