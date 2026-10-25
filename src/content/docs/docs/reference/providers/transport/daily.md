---
title: "Daily Transport Provider"
description: "Daily.co WebRTC transport for voice pipelines in Beluga AI. Bidirectional audio streaming with room management and low-latency delivery in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Daily, WebRTC, audio transport, voice pipeline, bidirectional audio, low latency, Go, Beluga AI"
---

:::caution[Not yet functional]
The `daily` provider is registered but not implemented: it never dials Daily. `transport.New("daily", ...)` and `daily.New` always return an error wrapping `transport.ErrNotImplemented` (which also wraps `errors.ErrUnsupported`), and every method on a `daily.Transport` value returns the same error instead of silently discarding audio. The configuration and examples below describe the planned integration. Use `transport.NewWebSocketTransport` for a working transport today. Track progress in the [framework repository](https://github.com/lookatitude/beluga-ai).
:::

The Daily provider implements bidirectional audio transport through Daily.co rooms. It enables voice pipelines to send and receive audio via Daily's WebRTC infrastructure.

Choose Daily when you want a managed WebRTC service with simple room-based audio transport. Daily handles the WebRTC infrastructure, letting you focus on voice pipeline logic. For self-hosted WebRTC infrastructure, consider [LiveKit](/docs/reference/providers/transport/livekit). For interoperability with Pipecat-based processing systems, consider [Pipecat](/docs/reference/providers/transport/pipecat).

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2/voice/transport/providers/daily
```

## Configuration

| Field        | Required | Default  | Description                              |
|--------------|----------|----------|------------------------------------------|
| `URL`        | Yes      | —        | Daily.co room URL                        |
| `Token`      | No       | —        | Daily room token for authentication      |
| `SampleRate` | No       | `16000`  | Audio sample rate in Hz                  |

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/voice/transport"
    _ "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/daily"
)

func main() {
    t, err := transport.New("daily", transport.Config{
        URL:   "https://myapp.daily.co/room-name",
        Token: "your-daily-token",
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

Write processed audio frames back to the Daily room using `voice.NewAudioFrame`:

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
import "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/daily"

t, err := daily.New(transport.Config{
    URL:        "https://myapp.daily.co/room-name",
    Token:      "your-daily-token",
    SampleRate: 16000,
})
```

## Error Handling

`transport.New("daily", ...)` currently always fails with an error wrapping `transport.ErrNotImplemented`, so check for it and fall back to a working transport:

```go
t, err := transport.New("daily", cfg)
if errors.Is(err, transport.ErrNotImplemented) {
    // daily is not implemented yet; use the built-in WebSocket transport
    t, err = transport.NewWebSocketTransport(ctx, wsURL)
}
if err != nil {
    log.Fatal(err)
}
defer t.Close()
```

Refer to the [Daily.co documentation](https://docs.daily.co/) for room setup and token generation.
