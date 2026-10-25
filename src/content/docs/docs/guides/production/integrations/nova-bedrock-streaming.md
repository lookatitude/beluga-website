---
title: Amazon Nova S2S on Bedrock
description: "Integrate Amazon Nova 2 Sonic for real-time speech-to-speech voice conversations via AWS Bedrock with Beluga AI in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Amazon Nova, AWS Bedrock S2S, speech-to-speech, Beluga AI, voice AI AWS, real-time audio, Go voice provider"
---

For teams already running infrastructure on AWS, Amazon Nova provides end-to-end voice conversations through AWS Bedrock without introducing a separate vendor. This avoids additional billing relationships, keeps audio data within your AWS account boundary, and leverages existing IAM policies for access control. This guide covers integrating the Amazon Nova S2S provider with Beluga AI for real-time streaming voice interactions.

## Overview

The Amazon Nova integration is the `voice/s2s/providers/nova` package. It registers itself as `"nova"` with the `s2s` registry and implements the standard `s2s.S2S` / `s2s.Session` interfaces, so the code you write against it is the same as for the OpenAI Realtime and Gemini Live providers.

The provider talks to Bedrock through the `InvokeModelWithBidirectionalStream` API using `aws-sdk-go-v2`, so requests are SigV4-signed with your AWS credentials: static keys from `Extra["access_key_id"]` / `Extra["secret_access_key"]` (and optional `Extra["session_token"]`), or the default AWS credential chain when those are absent.

## Prerequisites

- Go 1.26 or later
- AWS account with Bedrock access
- Nova 2 Sonic model enabled in Bedrock console
- AWS credentials configured (IAM role or access keys)

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

Configure AWS credentials:

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"
```

Enable the Nova 2 Sonic model in the AWS Bedrock console before proceeding.

## Configuration

Create a Nova engine through the registry and start a session. Instructions and tools go on `s2s.Config` (or as `s2s.Option`s to `Start`); the region goes in `Extra`:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/s2s"
    _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/nova"
)

func main() {
    ctx := context.Background()

    engine, err := s2s.New("nova", s2s.Config{
        Model:        "amazon.nova-sonic-v1:0",
        Instructions: "You are a helpful assistant.",
        Extra:        map[string]any{"region": os.Getenv("AWS_REGION")},
    })
    if err != nil {
        log.Fatalf("Failed to create Nova provider: %v", err)
    }

    session, err := engine.Start(ctx)
    if err != nil {
        log.Fatalf("Failed to start session: %v", err)
    }
    defer session.Close()

    fmt.Println("Nova session started")
}
```

## Usage

### Bidirectional Audio Streaming

Send audio with `SendAudio` and consume `s2s.SessionEvent` values from `Recv`:

```go
func handleNovaSession(ctx context.Context, session s2s.Session, audioIn <-chan []byte, play func([]byte)) error {
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
        case s2s.EventTranscript, s2s.EventTextOutput:
            log.Printf("text: %s", event.Text)
        case s2s.EventError:
            return event.Error
        }
    }
    return nil
}
```

To use the engine inside a voice pipeline, wrap it with `s2s.AsFrameProcessor(engine)`.

### Observability

Add OpenTelemetry tracing to monitor Nova sessions:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

tracer := otel.Tracer("beluga.voice.s2s.nova")
ctx, span := tracer.Start(ctx, "nova.start",
    trace.WithAttributes(
        attribute.String("model", "amazon.nova-sonic-v1:0"),
        attribute.String("region", os.Getenv("AWS_REGION")),
    ),
)
defer span.End()
```

## Configuration Reference

| Field               | Description                | Default                  | Required |
|---------------------|----------------------------|--------------------------|----------|
| `Extra["region"]`   | AWS region                 | `us-east-1`              | No       |
| `Extra["base_url"]` | Bedrock Runtime endpoint override (`http(s)` only) | SDK-resolved regional endpoint | No |
| `Extra["access_key_id"]`, `Extra["secret_access_key"]`, `Extra["session_token"]` | Static AWS credentials | Default AWS credential chain | No |
| `Model`             | Nova model ID              | `amazon.nova-sonic-v1:0` | No       |
| `Voice`             | Voice selection            | `matthew`                | No       |
| `Instructions`      | System instructions        | -                        | No       |

## Troubleshooting

### Model not enabled

Verify the Nova model is enabled in the AWS Bedrock console for your region. Navigate to Bedrock > Model access and confirm Nova 2 Sonic is available.

### Access denied

Ensure your IAM role or user has the required Bedrock permissions. Add `bedrock:InvokeModelWithResponseStream` to your IAM policy.

## Advanced Topics

### Production Deployment

- Use IAM roles instead of access keys for authentication in production
- Monitor Bedrock usage through AWS Cost Explorer and CloudWatch
- Choose an AWS region close to your users for lower latency
- Implement connection retry logic for transient Bedrock errors
- Set context timeouts to prevent indefinite streaming sessions

## Related Resources

- [OpenAI Realtime API](/docs/guides/production/integrations/openai-realtime)
- [Voice Services Overview](/docs/reference/providers/voice/)
