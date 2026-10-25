---
title: WebRTC Browser VAD
description: "Use lightweight WebRTC-based voice activity detection with browser audio streaming in Beluga AI for consistent speech detection."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "WebRTC VAD, browser voice detection, Beluga AI, speech detection, DSP algorithm, voice pipeline Go, client-side audio"
---

Browser-based applications need a fast, deterministic way to distinguish speech from silence before sending audio upstream. The WebRTC VAD provider uses traditional DSP algorithms that consume minimal CPU and produce consistent results across all clients, making it the right choice when you need predictable behavior without the overhead of a neural network model. Audio is streamed from the browser to a Go backend where VAD decisions are computed and returned.

## Overview

The `voice/vad/providers/webrtc` package registers a `"webrtc"` detector with the voice VAD registry. It is a pure-Go detector in the spirit of WebRTC VAD (RMS energy plus zero-crossing rate, not a port of the libwebrtc GMM model) running in your Go backend. Browser clients send audio (via WebSocket or HTTP) and receive speech/non-speech decisions, ensuring consistent VAD behavior across all clients.

## Prerequisites

- Go 1.26 or later
- Browser client capable of sending audio (WebSocket, HTTP upload)
- Audio format: PCM 16-bit mono, 16 kHz

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

## Configuration

Create a WebRTC VAD detector through the registry:

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/voice"
    _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
)

func main() {
    ctx := context.Background()

    detector, err := voice.NewVAD("webrtc", map[string]any{
        "threshold":     1000.0, // RMS energy threshold
        "zcr_threshold": 0.1,    // zero-crossing rate ceiling
    })
    if err != nil {
        log.Fatalf("Failed to create VAD provider: %v", err)
    }

    chunk := make([]byte, 1024)
    result, err := detector.DetectActivity(ctx, chunk)
    if err != nil {
        log.Fatalf("Processing failed: %v", err)
    }
    fmt.Printf("Speech detected: %v\n", result.IsSpeech)
}
```

## Usage

### Accept Browser Audio

Expose an HTTP or WebSocket endpoint that receives raw PCM chunks from the browser, pass each chunk to `DetectActivity`, and return `{"speech": true}` or `{"speech": false}` to the client. A detector tracks speech start/end state, so create one per client connection.

### Streaming Over WebSocket

For continuous streaming from the browser, loop over incoming chunks and push decisions back:

```go
func vadLoop(ctx context.Context, detector voice.ActivityDetector, chunks <-chan []byte, send func(speech bool) error) error {
    for chunk := range chunks {
        result, err := detector.DetectActivity(ctx, chunk)
        if err != nil {
            return fmt.Errorf("vad: %w", err)
        }
        if result.EventType == voice.VADSpeechStart || result.EventType == voice.VADSpeechEnd {
            if err := send(result.IsSpeech); err != nil {
                return err
            }
        }
    }
    return nil
}
```

For a full server-side voice agent, use `voice.WithVAD(detector)` in a `voice.VoicePipeline` with the WebSocket transport from `voice/transport`.

## Configuration Reference

| Key             | Description                                  | Default |
|-----------------|----------------------------------------------|---------|
| `threshold`     | RMS energy threshold for speech              | 1000.0  |
| `zcr_threshold` | Max zero-crossing rate counted as speech     | 0.1     |

Audio must be 16-bit little-endian mono PCM.

## Troubleshooting

### Browser audio format mismatch

Convert browser audio (usually 48 kHz float32) to 16-bit mono PCM before passing it to the VAD. Document the expected format (PCM 16-bit, 16 kHz, mono) for client developers.

### High latency

Use smaller audio chunks (10-30 ms). Keep WebSocket or HTTP round-trips tight. Consider running VAD in a dedicated goroutine to avoid blocking request handlers.

### Provider 'webrtc' not found

Import the WebRTC provider to trigger registration:

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
```

## Advanced Topics

### Production Deployment

- **CORS and authentication**: Secure your audio endpoint; validate origin and tokens
- **Rate limiting**: Limit requests per client to prevent abuse
- **Monitoring**: Log and track request volume, latency, and error rates with OpenTelemetry

## Related Resources

- [ONNX Runtime Edge VAD](/docs/guides/production/integrations/onnx-edge-vad)
- [Voice Services Overview](/docs/reference/providers/voice/)
