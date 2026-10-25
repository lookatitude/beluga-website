---
title: "Voice Transport API — WebSocket, LiveKit"
description: "Voice transport API reference for Beluga AI. AudioTransport interface with WebSocket, LiveKit, Daily, and Pipecat transport providers."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "voice transport API, AudioTransport, WebSocket, LiveKit, Daily, Pipecat, WebRTC, Beluga AI, Go, reference"
---

## transport

```go
import "github.com/lookatitude/beluga-ai/v2/voice/transport"
```

Package transport provides the audio transport interface and registry for the
Beluga AI voice pipeline. Transports handle bidirectional audio I/O between
clients and the voice pipeline, abstracting the underlying protocol
(WebSocket, LiveKit, Daily, etc.).

LiveKit is treated as a transport, not a framework dependency. LiveKit's
server provides WebRTC transport, while Beluga handles all STT/LLM/TTS
processing through the frame-based pipeline.

## Core Interface

The `AudioTransport` interface provides bidirectional audio I/O:

```go
type AudioTransport interface {
    Recv(ctx context.Context) (<-chan voice.Frame, error)
    Send(ctx context.Context, frame voice.Frame) error
    AudioOut() io.Writer
    Close() error
}
```

## Registry Pattern

Providers register via `Register` in their init() function and are created
with `New`. Use `List` to discover available providers.

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/transport"

t, err := transport.New("websocket", transport.Config{URL: "ws://..."})
frames, err := t.Recv(ctx)
for frame := range frames {
    // process incoming audio frame
}
```

## Pipeline Integration

Use `AsVoiceTransport` to adapt an AudioTransport to the voice.Transport
interface expected by the [voice.VoicePipeline].

## Built-in Transport

The package includes a `WebSocketTransport` implementation registered as
"websocket". Configure it with `NewWebSocketTransport` and options
`WithWSSampleRate` and `WithWSChannels`.

## Configuration

The `Config` struct supports URL, authentication token, sample rate,
channel count, and provider-specific extras. Use functional options
`WithURL`, `WithToken`, `WithSampleRate`, and `WithChannels`.

## Available Providers

- websocket — Built-in WebSocket transport (voice/transport)
- livekit — LiveKit WebRTC rooms (voice/transport/providers/livekit)
- daily — Daily.co rooms (voice/transport/providers/daily)
- pipecat — Pipecat server (voice/transport/providers/pipecat)

---

## daily

```go
import "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/daily"
```

Package daily registers the "daily" transport name for Daily.co rooms in the
Beluga AI voice pipeline.

## Status: not implemented

This provider is a placeholder. It does not connect to Daily:
`New` (and `transport.New("daily", ...)`) always returns an error wrapping
`transport.ErrNotImplemented`, which in turn wraps `errors.ErrUnsupported`.
Earlier releases returned a transport that silently discarded audio and
never produced frames; that fake success was removed.

Use the built-in "websocket" transport (voice/transport) until a real
Daily integration is available.

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/daily"

_, err := transport.New("daily", transport.Config{URL: "..."})
if errors.Is(err, transport.ErrNotImplemented) {
    // fall back to another transport
}
```

---

## livekit

```go
import "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/livekit"
```

Package livekit registers the "livekit" transport name for LiveKit WebRTC rooms in the
Beluga AI voice pipeline.

## Status: not implemented

This provider is a placeholder. It does not connect to LiveKit:
`New` (and `transport.New("livekit", ...)`) always returns an error wrapping
`transport.ErrNotImplemented`, which in turn wraps `errors.ErrUnsupported`.
Earlier releases returned a transport that silently discarded audio and
never produced frames; that fake success was removed.

Use the built-in "websocket" transport (voice/transport) until a real
LiveKit integration is available.

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/livekit"

_, err := transport.New("livekit", transport.Config{URL: "..."})
if errors.Is(err, transport.ErrNotImplemented) {
    // fall back to another transport
}
```

---

## pipecat

```go
import "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/pipecat"
```

Package pipecat registers the "pipecat" transport name for Pipecat servers in the
Beluga AI voice pipeline.

## Status: not implemented

This provider is a placeholder. It does not connect to Pipecat:
`New` (and `transport.New("pipecat", ...)`) always returns an error wrapping
`transport.ErrNotImplemented`, which in turn wraps `errors.ErrUnsupported`.
Earlier releases returned a transport that silently discarded audio and
never produced frames; that fake success was removed.

Use the built-in "websocket" transport (voice/transport) until a real
Pipecat integration is available.

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/transport/providers/pipecat"

_, err := transport.New("pipecat", transport.Config{URL: "..."})
if errors.Is(err, transport.ErrNotImplemented) {
    // fall back to another transport
}
```
