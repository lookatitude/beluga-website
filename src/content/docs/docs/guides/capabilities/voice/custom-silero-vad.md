---
title: Custom VAD with Silero Models
description: "Configure Beluga AI's Silero VAD provider in Go — thresholds, sample rates, streaming detection over audio frames, and audio preprocessing before detection."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, Silero VAD, voice activity detection, streaming, speech detection, ActivityDetector"
---

Voice activity detection (VAD) classifies each audio frame as speech or non-speech. Beluga's `silero` provider reports a speech probability on Silero's 0.0-1.0 scale, so thresholds you tune for it carry over to Silero-style models. This tutorial shows how to configure the provider, run it over a stream of audio frames, plug it into a voice pipeline, and preprocess audio before detection.

**Current implementation:** the `silero` provider accepts a `ModelPath` (or `model_path`) setting, but it does not load an ONNX model yet. It always computes the probability from normalized signal energy, calibrated to approximate Silero's output. It is therefore not yet more robust to loud non-speech noise (keyboards, doors) than an energy detector. Plan for that when you choose thresholds, and see [Noise-Resistant VAD](/docs/guides/capabilities/voice/noise-resistant-vad) for mitigation.

## What You Will Build

A VAD setup that classifies 16-bit PCM frames as speech or non-speech, runs over a continuous audio stream, and plugs into Beluga's cascading voice pipeline.

## Prerequisites

- Go 1.26 or later
- 16-bit little-endian mono PCM audio at 8 or 16 kHz
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) is recommended background

## Step 1: Create a Silero VAD

Use the typed constructor, or create the detector through the VAD registry by name. Both return a type that implements `voice.ActivityDetector`.

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

func main() {
	ctx := context.Background()

	// Typed constructor.
	detector, err := silero.New(silero.Config{
		Threshold:  0.5,
		SampleRate: 16000,
	})
	if err != nil {
		log.Fatalf("create VAD: %v", err)
	}

	// Equivalent, through the registry (the import above registers "silero").
	fromRegistry, err := voice.NewVAD("silero", map[string]any{
		"threshold":   0.5,
		"sample_rate": 16000,
	})
	if err != nil {
		log.Fatalf("create VAD from registry: %v", err)
	}
	fmt.Println("registered VADs:", voice.ListVAD())

	// 32 ms of silence at 16 kHz: 512 samples, 2 bytes each.
	frame := make([]byte, 1024)
	for _, d := range []voice.ActivityDetector{detector, fromRegistry} {
		res, err := d.DetectActivity(ctx, frame)
		if err != nil {
			log.Fatalf("detect: %v", err)
		}
		fmt.Printf("speech=%v event=%s confidence=%.2f\n", res.IsSpeech, res.EventType, res.Confidence)
	}
}
```

## Configuration Options

| `silero.Config` field | Registry key  | Default | Description                                        |
|-----------------------|---------------|---------|----------------------------------------------------|
| `Threshold`           | `threshold`   | 0.5     | Speech probability threshold, (0.0, 1.0]. Out-of-range values fall back to the default. |
| `SampleRate`          | `sample_rate` | 16000   | Audio sample rate in Hz (8000 or 16000)            |
| `ModelPath`           | `model_path`  | (none)  | Path to a Silero ONNX model. Accepted but not loaded yet. |

The detector has no frame-size, minimum-speech, or maximum-silence settings. It classifies whatever buffer you pass, so frame size is up to you. 20-32 ms frames (320-512 samples at 16 kHz) are a common choice. To require sustained speech or silence before a state change, wrap the detector as shown in [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning#step-2-add-minimum-speech-and-silence-durations).

`DetectActivity` returns a `voice.ActivityResult`:

| Field        | Type                 | Description                                                  |
|--------------|----------------------|--------------------------------------------------------------|
| `IsSpeech`   | `bool`               | Whether the frame's probability is at or above the threshold |
| `EventType`  | `voice.VADEventType` | `VADSpeechStart` while speech is detected, `VADSpeechEnd` on the first non-speech frame after speech, otherwise `VADSilence` |
| `Confidence` | `float64`            | Speech probability (0.0-1.0)                                 |

The detector keeps the previous frame's state to emit `VADSpeechEnd`, so use one detector instance per audio stream.

## Step 2: Streaming Detection

For continuous audio, call `DetectActivity` on each frame as it arrives. Here the source is an `iter.Seq2` of PCM chunks, the same shape Beluga's transports and STT engines use:

```go
import (
	"context"
	"fmt"
	"iter"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// detectStream reports speech start and end events for an audio stream.
func detectStream(ctx context.Context, vad voice.ActivityDetector, audio iter.Seq2[[]byte, error]) error {
	speaking := false
	for frame, err := range audio {
		if err != nil {
			return err
		}
		res, err := vad.DetectActivity(ctx, frame)
		if err != nil {
			return fmt.Errorf("detect: %w", err)
		}
		switch {
		case res.IsSpeech && !speaking:
			speaking = true
			fmt.Printf("speech started (confidence %.2f)\n", res.Confidence)
		case res.EventType == voice.VADSpeechEnd:
			speaking = false
			fmt.Println("speech ended")
		}
	}
	return nil
}
```

In a cascading pipeline you don't need this loop. Pass the detector to `voice.WithVAD`, and the pipeline runs it on every incoming audio frame. It emits a `voice.SignalStart` control frame on speech start and `voice.SignalEndOfUtterance` on speech end, and forwards only speech frames to STT:

```go
pipe := voice.NewPipeline(
	voice.WithTransport(transport),
	voice.WithVAD(detector),
	voice.WithSTT(sttProcessor),
	voice.WithLLM(llmProcessor),
	voice.WithTTS(ttsProcessor),
)
```

## Step 3: Threshold Tuning by Environment

The threshold sets how high the speech probability must be before a frame counts as speech. The right value depends on the background noise in your deployment. Because the current implementation measures energy, the threshold effectively sets a loudness level: lower values catch softer speech, higher values reject more background sound.

```go
	// Quiet environment: a lower threshold captures softer speech.
	quietVAD, err := silero.New(silero.Config{Threshold: 0.3, SampleRate: 16000})
	if err != nil {
		log.Fatalf("create quiet VAD: %v", err)
	}

	// Noisy environment: a higher threshold reduces false positives.
	noisyVAD, err := silero.New(silero.Config{Threshold: 0.7, SampleRate: 16000})
	if err != nil {
		log.Fatalf("create noisy VAD: %v", err)
	}
```

### Tuning Guidelines

| Environment   | Starting threshold |
|---------------|--------------------|
| Quiet office  | 0.3-0.4            |
| Standard room | 0.5                |
| Open office   | 0.6                |
| Call center   | 0.7-0.8            |

These are starting points. Record audio from the real environment, log `Confidence` for speech and for background noise, and choose a threshold between the two distributions.

## Step 4: Preprocess Audio Before Detection

Beluga does not include a noise-cancellation stage. For noisy environments, either enable noise suppression in the client (browser WebRTC audio constraints and most telephony platforms offer it), or wrap the detector with your own preprocessing. Any type that implements `voice.ActivityDetector` can be passed to `voice.WithVAD`. This wrapper applies a one-pole high-pass filter that removes low-frequency rumble (HVAC, traffic) before detection:

```go
import (
	"context"
	"encoding/binary"
	"math"
	"sync"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// highPassVAD filters out low-frequency noise before running the inner detector.
type highPassVAD struct {
	inner voice.ActivityDetector
	alpha float64

	mu         sync.Mutex
	prevIn     float64
	prevOut    float64
}

var _ voice.ActivityDetector = (*highPassVAD)(nil)

// newHighPassVAD returns a detector with a high-pass filter at cutoffHz.
func newHighPassVAD(inner voice.ActivityDetector, sampleRate int, cutoffHz float64) *highPassVAD {
	rc := 1 / (2 * math.Pi * cutoffHz)
	dt := 1 / float64(sampleRate)
	return &highPassVAD{inner: inner, alpha: rc / (rc + dt)}
}

func (h *highPassVAD) DetectActivity(ctx context.Context, audio []byte) (voice.ActivityResult, error) {
	filtered := make([]byte, len(audio)&^1)

	h.mu.Lock()
	for i := 0; i+1 < len(audio); i += 2 {
		x := float64(int16(binary.LittleEndian.Uint16(audio[i:])))
		y := h.alpha * (h.prevOut + x - h.prevIn)
		h.prevIn, h.prevOut = x, y
		y = math.Max(math.MinInt16, math.Min(math.MaxInt16, y))
		binary.LittleEndian.PutUint16(filtered[i:], uint16(int16(y)))
	}
	h.mu.Unlock()

	return h.inner.DetectActivity(ctx, filtered)
}
```

Use it as `voice.WithVAD(newHighPassVAD(detector, 16000, 150))`. A 100-200 Hz cutoff leaves the speech band intact. The filtered audio is used only for detection; the pipeline still forwards the original frame to STT.

## Verification

1. Run Step 1 and confirm a silent frame reports `speech=false`.
2. Feed recorded speech through `detectStream` and confirm start and end events line up with the utterances.
3. Log `Confidence` for speech and background noise in your environment and pick a threshold between them.
4. Compare false triggers with and without the high-pass wrapper in a room with low-frequency noise.

## Next Steps

- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Add duration rules and environment profiles
- [ML-Based Turn Prediction](/docs/guides/capabilities/voice/ml-turn-prediction) -- Decide when the user has finished speaking
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Use VAD for barge-in detection
