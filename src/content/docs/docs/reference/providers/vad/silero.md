---
title: "Silero VAD Provider"
description: "Silero voice activity detection in Beluga AI. High-accuracy neural network VAD with confidence scoring and configurable thresholds in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Silero VAD, voice activity detection, neural network, speech detection, confidence scoring, Go, Beluga AI"
---

Despite its name, the Silero provider does not run the Silero neural model. It is an RMS-energy detector on 16-bit little-endian PCM audio whose default threshold is calibrated to approximate Silero VAD sensitivity. Loading the Silero ONNX model is not implemented: setting `ModelPath` (`model_path`) makes construction fail instead of being silently ignored. This provider requires CGO.

Choose Silero when you want detection thresholds on Silero's 0-1 probability scale. Do not expect neural-network accuracy in noisy environments; for real Silero inference, implement `voice.ActivityDetector` on an ONNX Runtime binding and register it with `voice.RegisterVAD`. Note that it requires CGO. For a pure Go alternative with no CGO dependency, use [WebRTC](/docs/reference/providers/vad/webrtc).

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero
```

This package uses the `cgo` build tag. Ensure CGO is enabled in your build environment.

## Configuration

| Field        | Required | Default  | Description                             |
|--------------|----------|----------|-----------------------------------------|
| `Threshold`  | No       | `0.5`    | Speech probability threshold (0.0-1.0)  |
| `SampleRate` | No       | `16000`  | Audio sample rate in Hz (8000 or 16000) |
| `ModelPath`  | No       | —        | Not supported; construction returns `core.ErrInvalidInput` when set |

**Registry configuration keys:**

| Key           | Type      | Maps to      |
|---------------|-----------|--------------|
| `threshold`   | `float64` | `Threshold`  |
| `sample_rate` | `int`     | `SampleRate` |
| `model_path`  | `string`  | `ModelPath`  |

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/voice"
    _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

func main() {
    vad, err := voice.NewVAD("silero", map[string]any{
        "threshold":  0.5,
        "sample_rate": 16000,
    })
    if err != nil {
        log.Fatal(err)
    }

    // audioPCM is 16-bit little-endian PCM audio data
    var audioPCM []byte // ... obtained from audio source

    result, err := vad.DetectActivity(context.Background(), audioPCM)
    if err != nil {
        log.Fatal(err)
    }

    fmt.Printf("Speech: %v, Event: %s, Confidence: %.2f\n",
        result.IsSpeech, result.EventType, result.Confidence)
}
```

## Advanced Features

### ONNX Model Loading

ONNX model loading is not implemented. Passing `model_path` returns an error rather than silently falling back to the energy detector:

```go
_, err := voice.NewVAD("silero", map[string]any{
    "threshold":  0.5,
    "model_path": "/models/silero_vad.onnx",
})
// err: "silero: ModelPath is not supported: this provider is an energy-based
// approximation and cannot load the Silero ONNX model" (core.ErrInvalidInput)
```

### Continuous Detection with State Tracking

The provider tracks speech state internally and emits transition events:

```go
for _, chunk := range audioChunks {
    result, err := vad.DetectActivity(ctx, chunk)
    if err != nil {
        log.Fatal(err)
    }

    switch result.EventType {
    case voice.VADSpeechStart:
        fmt.Println("Speech started")
    case voice.VADSpeechEnd:
        fmt.Println("Speech ended")
    case voice.VADSilence:
        // Ongoing silence
    }
}
```

### Threshold Tuning

Lower thresholds increase sensitivity (more false positives), while higher thresholds reduce sensitivity (more missed speech):

- `0.3` — High sensitivity, suitable for quiet environments
- `0.5` — Balanced default for general use
- `0.7` — Low sensitivity, rejects ambient noise

## Direct Construction

For compile-time type safety, construct the provider directly:

```go
import "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"

vad, err := silero.New(silero.Config{
    Threshold:  0.5,
    SampleRate: 16000,
})
```

## Error Handling

```go
result, err := vad.DetectActivity(ctx, audioPCM)
if err != nil {
    log.Printf("VAD detection failed: %v", err)
    // Handle error — audio frame may be malformed
}
```

Audio data must be 16-bit little-endian PCM. Frames shorter than 2 bytes return a silence result without error.
