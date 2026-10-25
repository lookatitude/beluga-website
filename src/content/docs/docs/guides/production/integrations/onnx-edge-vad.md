---
title: Edge VAD (Silero Provider)
description: "Run voice activity detection on edge devices with the Beluga AI Silero and WebRTC VAD providers, and plug in your own ONNX model."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "ONNX VAD, Silero VAD, edge computing, voice activity detection, Beluga AI, offline VAD, Go voice pipeline"
---

Running VAD on the edge eliminates the network round-trip for speech detection, which reduces latency and keeps audio data local for privacy-sensitive deployments. Beluga's VAD providers are pure computation on PCM samples with no network calls, so they run fine on resource-constrained devices such as Raspberry Pi, embedded gateways, and kiosk hardware. This guide covers configuring the `silero` provider for low-resource environments, and what to do if you need real ONNX model inference.

## Overview

The `voice/vad/providers/silero` package registers a `"silero"` detector with the voice VAD registry (`voice.NewVAD`). It implements `voice.ActivityDetector`: each call to `DetectActivity` takes a chunk of 16-bit PCM audio and returns a `voice.ActivityResult` with `IsSpeech`, an event type (`VADSpeechStart`, `VADSpeechEnd`, `VADSilence`), and a confidence.

:::caution[No ONNX inference today]
Despite its name, the `silero` provider does **not** load or run the Silero ONNX model. Setting `model_path` makes construction fail with `core.ErrInvalidInput`; without it, the provider scores speech with an energy-based approximation of Silero's behavior. The package is also compiled only when cgo is enabled (`//go:build cgo`). If you need real Silero model inference, implement `voice.ActivityDetector` yourself on top of an ONNX Runtime binding and register it with `voice.RegisterVAD`, as shown below.
:::

## Prerequisites

- Go 1.26 or later, with cgo enabled for the `silero` package (`CGO_ENABLED=1`)
- 16-bit little-endian mono PCM audio at 8 kHz or 16 kHz

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

## Configuration

Create the detector through the registry:

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
    ctx := context.Background()

    detector, err := voice.NewVAD("silero", map[string]any{
        "threshold":   0.5,
        "sample_rate": 16000,
    })
    if err != nil {
        log.Fatalf("Failed to create VAD provider: %v", err)
    }

    chunk := make([]byte, 1024) // 512 samples of 16-bit audio
    result, err := detector.DetectActivity(ctx, chunk)
    if err != nil {
        log.Fatalf("Processing failed: %v", err)
    }
    fmt.Printf("Speech detected: %v (%s)\n", result.IsSpeech, result.EventType)
}
```

If your edge toolchain builds with `CGO_ENABLED=0`, use the pure-Go `webrtc` provider instead (`voice.NewVAD("webrtc", map[string]any{"threshold": 1000.0})`) or the built-in `voice.NewEnergyVAD`.

## Usage

### Real-Time Capture Loop

Call `DetectActivity` for each chunk from your capture loop and forward only speech:

```go
func captureLoop(ctx context.Context, detector voice.ActivityDetector, chunks <-chan []byte, forward func([]byte)) error {
    for chunk := range chunks {
        result, err := detector.DetectActivity(ctx, chunk)
        if err != nil {
            return fmt.Errorf("vad: %w", err)
        }
        if result.IsSpeech {
            forward(chunk) // to STT or the rest of the pipeline
        }
    }
    return nil
}
```

Inside a `voice.VoicePipeline`, pass the detector with `voice.WithVAD(detector)`; the pipeline then emits start and end-of-utterance control frames for you.

### Plugging in a Real ONNX Model

The registry accepts any `voice.ActivityDetector`. Wrap your ONNX Runtime session in a type with a `DetectActivity` method and register a factory:

```go
type onnxVAD struct {
    infer     func(samples []float32) (float32, error) // your ONNX Runtime call
    threshold float32
    speaking  bool
}

func (v *onnxVAD) DetectActivity(ctx context.Context, audio []byte) (voice.ActivityResult, error) {
    samples := make([]float32, len(audio)/2)
    for i := range samples {
        samples[i] = float32(int16(binary.LittleEndian.Uint16(audio[2*i:]))) / 32768
    }
    p, err := v.infer(samples)
    if err != nil {
        return voice.ActivityResult{}, err
    }
    isSpeech := p >= v.threshold
    event := voice.VADSilence
    switch {
    case isSpeech && !v.speaking:
        event = voice.VADSpeechStart
    case !isSpeech && v.speaking:
        event = voice.VADSpeechEnd
    }
    v.speaking = isSpeech
    return voice.ActivityResult{IsSpeech: isSpeech, EventType: event, Confidence: float64(p)}, nil
}

func init() {
    voice.RegisterVAD("silero-onnx", func(cfg map[string]any) (voice.ActivityDetector, error) {
        path, _ := cfg["model_path"].(string)
        infer, err := loadSileroModel(path) // your loader
        if err != nil {
            return nil, err
        }
        return &onnxVAD{infer: infer, threshold: 0.5}, nil
    })
}
```

## Configuration Reference

| Key           | Description                         | Default | Edge Notes                 |
|---------------|-------------------------------------|---------|----------------------------|
| `threshold`   | Speech probability threshold (0-1)  | 0.5     | 0.5-0.6 typical            |
| `sample_rate` | Audio sample rate (Hz)              | 16000   | 8000 or 16000; match input |
| `model_path`  | Not supported; construction fails when set | -  | See the caution above      |

## Troubleshooting

### "build constraints exclude all Go files" for the silero package

The package builds only with cgo. Enable cgo (`CGO_ENABLED=1` and a C toolchain for the target), or switch to the `webrtc` provider.

### High CPU usage on edge

Process larger chunks (fewer calls), or skip every other chunk during long silences. Profile with `pprof` to identify bottlenecks.

### Too many false triggers

Raise `threshold`, and smooth decisions over time with a wrapper detector; see [Heuristic Turn Detection Tuning](/docs/guides/production/integrations/turn-heuristic-tuning).

## Related Resources

- [WebRTC VAD in Browser](/docs/guides/production/integrations/webrtc-browser-vad)
- [Voice Services Overview](/docs/reference/providers/voice/)
