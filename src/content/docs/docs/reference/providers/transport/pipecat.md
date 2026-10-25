---
title: "Pipecat Transport Provider"
description: "Pipecat-compatible transport for voice pipelines in Beluga AI. Frame-based audio streaming with pipeline integration and protocol bridging in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Pipecat, audio transport, voice pipeline, frame-based, pipeline integration, protocol bridge, Go, Beluga AI"
---

:::caution[Not yet functional]
The `pipecat` provider is registered but not implemented: it never dials Pipecat. `transport.New("pipecat", ...)` and `pipecat.New` always return an error wrapping `transport.ErrNotImplemented` (which also wraps `errors.ErrUnsupported`), and every method on a `pipecat.Transport` value returns the same error instead of silently discarding audio. The configuration and examples below describe the planned integration. Use `transport.NewWebSocketTransport` for a working transport today. Track progress in the [framework repository](https://github.com/lookatitude/beluga-ai).
:::

The Pipecat provider implements bidirectional audio transport through a Pipecat server over WebSocket. It enables Beluga's voice pipeline to interoperate with Pipecat-based audio processing systems.

Choose Pipecat when you need to bridge Beluga's voice pipeline with an existing Pipecat-based processing system over WebSocket. This is useful for hybrid architectures where some audio processing happens in a Pipecat server while Beluga handles the agent logic. For WebRTC-based transport, consider [LiveKit](/docs/reference/providers/transport/livekit) or [Daily](/docs/reference/providers/transport/daily).

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2/voice/transport/providers/pipecat
```

## Configuration

| Field        | Required | Default  | Description                              |
|--------------|----------|----------|------------------------------------------|
| `URL`        | Yes      | —        | Pipecat server WebSocket URL             |
| `SampleRate` | No       | `16000`  | Audio sample rate in Hz                  |

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/voice/transport"
    _ "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/pipecat"
)

func main() {
    t, err := transport.New("pipecat", transport.Config{
        URL: "ws://localhost:8765",
    })
    if err != nil {
        log.Fatal(err)
    }
    defer t.Close()

    // Receive incoming audio frames
    for frame, err := range t.Recv(context.Background()) {
        if err != nil {
            log.Fatal(err)
        }
        fmt.Printf("Received %d bytes of audio\n", len(frame.Data))
    }
}
```

## Advanced Features

### Sending Audio

Write processed audio back to the Pipecat server using `voice.NewAudioFrame`:

```go
frame := voice.NewAudioFrame(processedPCM, 16000)
err := t.Send(ctx, frame)
if err != nil {
    log.Printf("send failed: %v", err)
}
```

### Raw Audio Output

For direct audio piping without frame wrapping:

```go
writer := t.AudioOut()
_, err := writer.Write(rawPCMData)
if err != nil {
    log.Printf("audio write failed: %v", err)
}
```

## Direct Construction

```go
import "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/pipecat"

t, err := pipecat.New(transport.Config{
    URL:        "ws://localhost:8765",
    SampleRate: 16000,
})
```

## Error Handling

`transport.New("pipecat", ...)` currently always fails with an error wrapping `transport.ErrNotImplemented`, so check for it and fall back to a working transport:

```go
t, err := transport.New("pipecat", cfg)
if errors.Is(err, transport.ErrNotImplemented) {
    // pipecat is not implemented yet; use the built-in WebSocket transport
    t, err = transport.NewWebSocketTransport(ctx, wsURL)
}
if err != nil {
    log.Fatal(err)
}
defer t.Close()
```

Refer to the [Pipecat documentation](https://docs.pipecat.ai/) for server setup and configuration.
