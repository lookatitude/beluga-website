---
title: VAD and Turn Detection Sensitivity
description: "Tune VAD thresholds, minimum speech and silence durations, and environment profiles in Go for natural turn-taking with Beluga AI's voice pipeline."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, VAD tuning, voice sensitivity, silero, webrtc, energy VAD, noise environment, sensitivity profiles"
---

Voice Activity Detection (VAD) decides whether an audio frame contains speech. Together with your turn rules, it sets the turn-taking rhythm of a conversation. Tuning it matters. Too sensitive, and the agent reacts to breathing, a cough, or a closing door. Too conservative, and it misses the start of speech or leaves awkward pauses before responding.

The right values depend on the environment and the use case. A threshold tuned for a quiet office triggers on machine noise in a factory. A threshold tuned for a factory ignores soft-spoken users in an office. Wake-word style detection wants high sensitivity, barge-in wants balanced sensitivity, and long-form dictation wants low sensitivity so continuous speech is not fragmented. This guide shows how to configure Beluga's VAD providers, add duration rules on top of them, and package validated settings as named profiles.

## What You Will Build

- A VAD created from Beluga's registry with an explicit threshold.
- A debounce wrapper that adds minimum-speech and minimum-silence durations to any `voice.ActivityDetector`.
- Named sensitivity profiles (`sensitive`, `balanced`, `robust`) selected at runtime.
- Barge-in handling that uses the voice session state.

## Prerequisites

- Go 1.26 or later
- Basic understanding of 16-bit PCM audio
- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) is recommended background

## Step 1: Configure a VAD Provider

Beluga registers three detectors under the `voice.ActivityDetector` interface. All of them analyze 16-bit little-endian PCM:

| Name     | Package                                | Config keys (`map[string]any`)              | Detection method                                      |
|----------|----------------------------------------|---------------------------------------------|-------------------------------------------------------|
| `energy` | `voice` (built in)                     | `threshold` (RMS, default 1000)             | RMS energy above a threshold                          |
| `webrtc` | `voice/vad/providers/webrtc`           | `threshold` (RMS, default 1000), `zcr_threshold` (default 0.1) | RMS energy plus zero-crossing rate        |
| `silero` | `voice/vad/providers/silero`           | `threshold` (0-1, default 0.5), `sample_rate` (default 16000); `model_path` is rejected | Normalized energy, calibrated to Silero's scale |

The `silero` provider does not load an ONNX model: setting `model_path` returns an error. It always uses an energy-based approximation calibrated to Silero's 0-1 probability scale. Its thresholds are tunable, but you should not expect neural-network accuracy from it yet.

Create a detector from the registry by name, or with the provider's typed constructor:

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
		log.Fatalf("create VAD: %v", err)
	}

	// 20 ms of silence at 16 kHz: 320 samples, 2 bytes each.
	audio := make([]byte, 640)
	res, err := detector.DetectActivity(ctx, audio)
	if err != nil {
		log.Fatalf("detect: %v", err)
	}

	fmt.Printf("speech=%v event=%s confidence=%.2f\n", res.IsSpeech, res.EventType, res.Confidence)
}
```

`DetectActivity` returns a `voice.ActivityResult` with `IsSpeech`, an `EventType` (`voice.VADSpeechStart`, `voice.VADSpeechEnd`, or `voice.VADSilence`), and a `Confidence` score. In the cascading pipeline, `VADSpeechStart` emits a `voice.SignalStart` control frame, `VADSpeechEnd` emits `voice.SignalEndOfUtterance`, and audio frames with `IsSpeech` set are forwarded to STT.

## Step 2: Add Minimum Speech and Silence Durations

The built-in detectors classify each frame on its own. A single loud frame (a click or a tap on the desk) can start an utterance, and a single quiet frame (a breath) can end one. Two duration rules fix this:

- **Minimum speech duration** filters transient noise. Speech must last this long before it counts.
- **Minimum silence duration** filters natural pauses. Silence must last this long before speech ends.

Wrap any detector to add them. Frame duration is derived from the frame size (two bytes per sample):

```go
import (
	"context"
	"sync"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// debouncedVAD adds minimum speech and silence durations to an ActivityDetector.
type debouncedVAD struct {
	inner      voice.ActivityDetector
	sampleRate int
	minSpeech  time.Duration
	minSilence time.Duration

	mu       sync.Mutex
	speaking bool
	run      time.Duration // length of the current speech or silence run
}

var _ voice.ActivityDetector = (*debouncedVAD)(nil)

func newDebouncedVAD(inner voice.ActivityDetector, sampleRate int, minSpeech, minSilence time.Duration) *debouncedVAD {
	return &debouncedVAD{inner: inner, sampleRate: sampleRate, minSpeech: minSpeech, minSilence: minSilence}
}

func (d *debouncedVAD) DetectActivity(ctx context.Context, audio []byte) (voice.ActivityResult, error) {
	res, err := d.inner.DetectActivity(ctx, audio)
	if err != nil {
		return voice.ActivityResult{}, err
	}
	frame := time.Duration(len(audio)/2) * time.Second / time.Duration(d.sampleRate)

	d.mu.Lock()
	defer d.mu.Unlock()

	if !d.speaking {
		if !res.IsSpeech {
			d.run = 0
			return voice.ActivityResult{EventType: voice.VADSilence, Confidence: res.Confidence}, nil
		}
		d.run += frame
		if d.run < d.minSpeech {
			// Not sustained yet. Speech frames before the start event are
			// dropped, so keep minSpeech short (100-300 ms).
			return voice.ActivityResult{EventType: voice.VADSilence, Confidence: res.Confidence}, nil
		}
		d.speaking, d.run = true, 0
		return voice.ActivityResult{IsSpeech: true, EventType: voice.VADSpeechStart, Confidence: res.Confidence}, nil
	}

	if res.IsSpeech {
		d.run = 0
		// Empty EventType: still speaking, no state transition to report.
		return voice.ActivityResult{IsSpeech: true, Confidence: res.Confidence}, nil
	}
	d.run += frame
	if d.run < d.minSilence {
		// A short pause inside speech: keep forwarding audio.
		return voice.ActivityResult{IsSpeech: true, Confidence: res.Confidence}, nil
	}
	d.speaking, d.run = false, 0
	return voice.ActivityResult{EventType: voice.VADSpeechEnd, Confidence: res.Confidence}, nil
}
```

The parameters interact. A higher threshold with a short minimum speech duration reacts quickly but only to loud speech. A lower threshold with a longer minimum speech duration catches quiet speech while still rejecting short noise bursts.

## Step 3: Package Settings as Sensitivity Profiles

Rather than scattering magic numbers through the code, bundle a provider, its config, and the duration rules into named profiles. Pick the profile at runtime from an environment variable, a tenant setting, or request metadata:

```go
import (
	"fmt"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// SensitivityProfile is a validated set of VAD settings for one environment.
type SensitivityProfile struct {
	Provider   string
	Config     map[string]any
	MinSpeech  time.Duration
	MinSilence time.Duration
}

var profiles = map[string]SensitivityProfile{
	// Quiet rooms, wake-word style: catch every utterance.
	"sensitive": {
		Provider:   "silero",
		Config:     map[string]any{"threshold": 0.4, "sample_rate": 16000},
		MinSpeech:  100 * time.Millisecond,
		MinSilence: 400 * time.Millisecond,
	},
	// General purpose.
	"balanced": {
		Provider:   "silero",
		Config:     map[string]any{"threshold": 0.5, "sample_rate": 16000},
		MinSpeech:  150 * time.Millisecond,
		MinSilence: 500 * time.Millisecond,
	},
	// Noisy environments: prefer precision over recall.
	"robust": {
		Provider:   "webrtc",
		Config:     map[string]any{"threshold": 1800.0, "zcr_threshold": 0.08},
		MinSpeech:  250 * time.Millisecond,
		MinSilence: 600 * time.Millisecond,
	},
}

// NewVADForProfile builds a debounced detector from a named profile.
func NewVADForProfile(name string, sampleRate int) (voice.ActivityDetector, error) {
	p, ok := profiles[name]
	if !ok {
		return nil, fmt.Errorf("unknown VAD profile %q", name)
	}
	base, err := voice.NewVAD(p.Provider, p.Config)
	if err != nil {
		return nil, fmt.Errorf("create %s VAD: %w", p.Provider, err)
	}
	return newDebouncedVAD(base, sampleRate, p.MinSpeech, p.MinSilence), nil
}
```

Import the providers your profiles use (`_ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"` and `.../webrtc`) so they register. Pass the result to `voice.WithVAD` when you build the pipeline.

What each profile trades off:

- **`sensitive`** uses a low threshold and short durations. It rarely misses an utterance, at the cost of more false triggers. Use it where missing speech is worse than reacting to noise.
- **`balanced`** works adequately in most rooms.
- **`robust`** uses the WebRTC-style detector, whose zero-crossing check helps reject hiss and broadband noise, plus a higher energy threshold and longer durations. It may miss quiet or fragmented speech.

Treat these numbers as starting points. Measure false-positive and false-negative rates in each target environment, and record the expected environment next to each profile. The same pattern supports per-tenant profiles, profiles loaded from a config file, and A/B tests of sensitivity changes without code changes.

## Step 4: Barge-In While the Agent Is Speaking

When the agent is speaking and the user starts talking, playback should stop right away. Missing an interruption (the user feels ignored) costs more than a false positive (the agent pauses briefly), so you can use a more sensitive profile for this check. `voice.VoiceSession` tracks whether the agent is speaking:

```go
import (
	"context"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// checkBargeIn stops agent playback when the user speaks over it.
// stopPlayback is your transport-specific function that halts audio output.
func checkBargeIn(ctx context.Context, vad voice.ActivityDetector, sess *voice.VoiceSession, audio []byte, stopPlayback func()) error {
	if sess.CurrentState() != voice.StateSpeaking {
		return nil
	}
	res, err := vad.DetectActivity(ctx, audio)
	if err != nil {
		return err
	}
	if res.EventType == voice.VADSpeechStart {
		stopPlayback()
		return sess.Transition(voice.StateListening)
	}
	return nil
}
```

The cascading `voice.VoicePipeline` does not stop TTS playback on its own. For speech-to-speech engines, sending a `voice.NewControlFrame(voice.SignalInterrupt)` frame into `s2s.AsFrameProcessor` calls the session's `Interrupt` method. See [Barge-In Detection](/docs/guides/capabilities/voice/barge-in-detection) for a fuller treatment.

## Verification

1. Run the agent in your target environment.
2. Hum, cough, or tap the desk. With the debounced detector, the agent should not react.
3. Say "Hello." The agent should respond within about one second.
4. Speak a long sentence with a natural mid-sentence pause. The agent should wait for the whole sentence.
5. Interrupt the agent mid-sentence. Playback should stop immediately.
6. Repeat with each profile and record which one gives the fewest false triggers and missed utterances.

## Next Steps

- [Custom Silero VAD](/docs/guides/capabilities/voice/custom-silero-vad) -- Configure the Silero provider
- [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary) -- Combine VAD with transcript rules
- [Native S2S with Amazon Nova](/docs/guides/capabilities/voice/s2s-amazon-nova) -- Models with built-in VAD
