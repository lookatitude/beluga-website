---
title: "VAD API — Silero, WebRTC Detection"
description: "Voice VAD API reference for Beluga AI. Voice activity detection with Silero ONNX model and WebRTC energy-based speech detection providers."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "VAD API, voice activity detection, Silero, WebRTC, speech detection, energy threshold, Beluga AI, Go, reference"
---

## silero

```go
import "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
```

Package silero registers the "silero" VAD (Voice Activity Detection) name
for the Beluga AI voice pipeline.

Despite the name, this provider does NOT run the Silero neural model. It is
an RMS-energy detector on 16-bit little-endian PCM audio whose default
threshold is calibrated to approximate Silero VAD sensitivity. Loading the
Silero ONNX model is not implemented: setting model_path (Config.ModelPath)
makes construction fail instead of being silently ignored.

This package requires CGO and is only compiled when the cgo build tag is set.

## Registration

This package registers itself as "silero" with the voice VAD registry. Import
it with a blank identifier to enable:

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
```

## Usage

```go
vad, err := voice.NewVAD("silero", map[string]any{"threshold": 0.5})
if err != nil {
    return err
}
result, err := vad.DetectActivity(ctx, audioPCM)
```

## Configuration

Configuration is passed as map[string]any:

- threshold — Speech probability threshold, 0.0 to 1.0 (default: 0.5)
- sample_rate — Audio sample rate, 8000 or 16000 (default: 16000)
- model_path — not supported; returns an error when set

## Exported Types

- [VAD] — energy-based voice.ActivityDetector
- [Config] — configuration struct
- [New] — constructor accepting Config

---

## webrtc

```go
import "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
```

Package webrtc provides a pure Go WebRTC-style VAD (Voice Activity Detection)
provider for the Beluga AI voice pipeline. It uses energy and zero-crossing
rate (ZCR) analysis on 16-bit PCM audio to detect speech, distinguishing
voiced content from noise.

## Registration

This package registers itself as "webrtc" with the voice VAD registry. Import
it with a blank identifier to enable:

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
```

## Usage

```go
vad, err := voice.NewVAD("webrtc", map[string]any{"threshold": 1500.0})
result, err := vad.DetectActivity(ctx, audioPCM)
```

## Detection Algorithm

Speech is detected when both conditions are met:

- RMS energy exceeds the energy threshold (filters out silence)
- Zero-crossing rate is below the ZCR threshold (filters out noise)

This dual-criteria approach provides better discrimination between speech
and noise compared to energy-only detection.

## Configuration

Configuration is passed as map[string]any:

- threshold — RMS energy threshold (default: 1000.0)
- zcr_threshold — Zero-crossing rate threshold (default: 0.1)

## Exported Types

- [VAD] — implements voice.VAD using energy + ZCR analysis
- [New] — constructor accepting energy and ZCR thresholds
