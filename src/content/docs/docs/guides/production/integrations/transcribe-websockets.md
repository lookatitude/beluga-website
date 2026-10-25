---
title: AWS Transcribe WebSocket STT
description: "Integrate AWS Transcribe for real-time streaming speech-to-text via WebSocket with speaker diarization in Beluga AI pipelines."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "AWS Transcribe, speech-to-text, WebSocket STT, Beluga AI, real-time transcription, speaker diarization, Go STT provider"
---

For organizations already operating within the AWS ecosystem, AWS Transcribe provides real-time speech transcription that integrates natively with IAM, CloudWatch, and other AWS services. Its automatic language detection and speaker diarization capabilities make it well suited for multi-speaker, multi-language scenarios such as contact center transcription. This guide covers integrating AWS Transcribe as an STT provider within Beluga AI.

## Overview

Beluga AI does not ship an AWS Transcribe provider. This guide wraps the AWS Transcribe Streaming SDK in a small type that implements the `stt.STT` interface (`Transcribe` and `TranscribeStream`), so it can be used anywhere a built-in STT provider can. Audio is streamed over WebSocket for low-latency transcription with support for multiple languages and speaker diarization.

## Prerequisites

- Go 1.26 or later
- AWS account with Transcribe access
- AWS credentials configured (IAM role or access keys)

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
go get github.com/aws/aws-sdk-go-v2/service/transcribestreaming
```

Configure AWS credentials:

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"
```

## Configuration

Create an AWS Transcribe STT provider:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/aws/aws-sdk-go-v2/config"
    "github.com/aws/aws-sdk-go-v2/service/transcribestreaming"
)

func main() {
    ctx := context.Background()

    cfg, err := config.LoadDefaultConfig(ctx,
        config.WithRegion(os.Getenv("AWS_REGION")),
    )
    if err != nil {
        log.Fatalf("Failed to load AWS config: %v", err)
    }

    client := transcribestreaming.NewFromConfig(cfg)

    provider := NewAWSTranscribeSTT(client, "en-US")

    audio, err := os.ReadFile("sample.pcm")
    if err != nil {
        log.Fatalf("Failed to read audio: %v", err)
    }
    transcript, err := provider.Transcribe(ctx, audio)
    if err != nil {
        log.Fatalf("Transcription failed: %v", err)
    }

    fmt.Printf("Transcript: %s\n", transcript)
}
```

## Usage

### Custom Provider Wrapper

Wrap the AWS Transcribe client to implement `stt.STT`. The streaming call itself (`StartStreamTranscription`, sending `AudioEvent`s, reading `TranscriptEvent`s) is AWS SDK code and is left as an outline here:

```go
import (
    "context"
    "errors"
    "iter"
    "strings"

    "github.com/aws/aws-sdk-go-v2/service/transcribestreaming"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
)

type AWSTranscribeSTT struct {
    client   *transcribestreaming.Client
    language string
}

var _ stt.STT = (*AWSTranscribeSTT)(nil)

func NewAWSTranscribeSTT(client *transcribestreaming.Client, language string) *AWSTranscribeSTT {
    return &AWSTranscribeSTT{client: client, language: language}
}

// Transcribe streams a complete buffer and joins the final results.
func (t *AWSTranscribeSTT) Transcribe(ctx context.Context, audio []byte, opts ...stt.Option) (string, error) {
    single := func(yield func([]byte, error) bool) { yield(audio, nil) }
    var parts []string
    for event, err := range t.TranscribeStream(ctx, single, opts...) {
        if err != nil {
            return "", err
        }
        if event.IsFinal {
            parts = append(parts, event.Text)
        }
    }
    return strings.Join(parts, " "), nil
}

// TranscribeStream sends audio chunks to AWS Transcribe and yields events.
func (t *AWSTranscribeSTT) TranscribeStream(ctx context.Context, audio iter.Seq2[[]byte, error], opts ...stt.Option) iter.Seq2[stt.TranscriptEvent, error] {
    return func(yield func(stt.TranscriptEvent, error) bool) {
        // 1. Call t.client.StartStreamTranscription with t.language and the
        //    sample rate from stt.ApplyOptions(opts...).SampleRate.
        // 2. Forward each chunk from audio as an AudioEvent.
        // 3. For each result, yield stt.TranscriptEvent{Text: ..., IsFinal: !result.IsPartial}.
        yield(stt.TranscriptEvent{}, errors.New("aws transcribe: streaming not implemented"))
    }
}
```

### Voice Pipeline Integration

Wrap the provider with `stt.AsFrameProcessor` to use it as the STT stage of a `voice.VoicePipeline`:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
)

pipe := voice.NewPipeline(
    voice.WithTransport(transport),
    voice.WithVAD(voice.NewEnergyVAD(voice.EnergyVADConfig{})),
    voice.WithSTT(stt.AsFrameProcessor(provider, stt.WithSampleRate(16000))),
    voice.WithLLM(llmStage),
    voice.WithTTS(ttsStage),
)
if err := pipe.Run(ctx); err != nil {
    log.Fatalf("pipeline: %v", err)
}
```

You can also register the wrapper with `stt.Register("aws-transcribe", factory)` so it can be selected by name with `stt.New`.

## Configuration Reference

| Option       | Description         | Default    | Required |
|-------------|---------------------|------------|----------|
| `Region`     | AWS region          | `us-east-1`| No      |
| `Language`   | Language code       | `en-US`    | No       |
| `SampleRate` | Audio sample rate   | `16000`    | No       |

## Troubleshooting

### Credentials not found

Ensure AWS credentials are configured via environment variables, shared credentials file, or IAM role. Run `aws configure` to set up the default profile.

### Region not supported

AWS Transcribe Streaming is not available in all regions. Use a supported region such as `us-east-1`, `us-west-2`, or `eu-west-1`.

## Advanced Topics

### Production Deployment

- Use IAM roles instead of access keys for authentication
- Monitor usage through AWS CloudWatch and Cost Explorer
- Choose an AWS region close to your users for lower latency
- Use WebSocket streaming for all real-time transcription scenarios
- Implement reconnection logic for WebSocket failures

## Related Resources

- [Deepgram Live Streams](/docs/guides/production/integrations/deepgram-streams)
- [Voice Services Overview](/docs/reference/providers/voice/)
