---
title: Sentence-Boundary Turn Detection
description: "Detect user turn completion in Go by combining sentence-end markers, silence thresholds, and utterance length limits, wired into a Beluga AI voice pipeline."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, turn detection, sentence boundary, heuristic, silence threshold, VAD, voice pipeline"
---

Deciding when a user has finished speaking is central to a responsive voice agent, and harder than it looks. Detection that relies only on silence waits for long pauses (500-1000 ms) and feels sluggish. Detection that fires too early cuts users off mid-sentence. Users pause between phrases, trail off, and speak in fragments, so a single fixed signal is never enough.

Heuristic turn detection combines a few simple, predictable rules: a sentence-end marker (`.`, `!`, `?`) in the transcript, a minimum silence after speech, and minimum and maximum utterance lengths. It needs no model files and is easy to debug. The tradeoff is that heuristics cannot pick up conversational nuance such as an intentional pause, but for structured interactions (commands, short queries, form-filling) they work well.

## What You Will Build

- A `TurnDetector` type that applies sentence-boundary, length, and silence rules to a transcript.
- A silence-hangover wrapper around a Beluga `voice.ActivityDetector`, so the pipeline only signals end of utterance after a configurable silence.
- A `voice.FrameProcessor` stage that buffers transcript fragments and forwards one text frame per completed turn to the LLM.

## Prerequisites

- Go 1.26 or later
- Familiarity with the Beluga voice pipeline (`voice.NewPipeline`) and frame model

## How Turns Flow Through a Beluga Pipeline

Beluga does not ship a separate turn-detection package. In the cascading pipeline (`voice.NewPipeline`), the VAD stage runs `DetectActivity` on every audio frame and:

- emits a `voice.SignalStart` control frame on `voice.VADSpeechStart`,
- emits a `voice.SignalEndOfUtterance` control frame on `voice.VADSpeechEnd`, and
- forwards the audio frame to STT when `IsSpeech` is true.

Control frames pass through `stt.AsFrameProcessor` unchanged, so a stage placed after STT sees transcript text frames interleaved with end-of-utterance signals. That is where the sentence-boundary rules go. How long a pause has to last before the VAD reports `VADSpeechEnd` is the silence rule, so it goes in a VAD wrapper.

## Step 1: The Turn Rules

The rules are plain Go with no framework dependency, which makes them easy to unit-test:

```go
package main

import (
	"fmt"
	"strings"
	"time"
)

// TurnDetector decides whether an accumulated transcript is a complete turn.
type TurnDetector struct {
	// SentenceEndMarkers are characters that indicate a complete sentence.
	SentenceEndMarkers string
	// MinTurnLength is the minimum transcript length, in characters.
	MinTurnLength int
	// MaxTurnLength forces a turn end once the transcript is this long.
	MaxTurnLength int
	// MinSilence is the silence required after speech before a turn can end.
	MinSilence time.Duration
}

// DefaultTurnDetector returns rules suited to short question-and-answer exchanges.
func DefaultTurnDetector() TurnDetector {
	return TurnDetector{
		SentenceEndMarkers: ".!?",
		MinTurnLength:      10,
		MaxTurnLength:      5000,
		MinSilence:         400 * time.Millisecond,
	}
}

// Complete reports whether transcript, followed by silence, ends the user's turn.
func (d TurnDetector) Complete(transcript string, silence time.Duration) bool {
	t := strings.TrimSpace(transcript)
	if d.MaxTurnLength > 0 && len(t) >= d.MaxTurnLength {
		return true // never accumulate without bound
	}
	if len(t) < d.MinTurnLength || silence < d.MinSilence {
		return false
	}
	last := t[len(t)-1:]
	return strings.ContainsAny(last, d.SentenceEndMarkers)
}

func main() {
	d := DefaultTurnDetector()
	fmt.Println(d.Complete("I want to", 500*time.Millisecond))                    // false: no sentence end
	fmt.Println(d.Complete("Book a flight to Lisbon.", 200*time.Millisecond))     // false: pause too short
	fmt.Println(d.Complete("Book a flight to Lisbon.", 450*time.Millisecond))     // true
}
```

The evaluation order matters:

1. **Maximum length** forces a turn end regardless of the other rules, so long monologues are eventually processed.
2. **Minimum length** stops very short fragments ("um", "so") from ending a turn.
3. **Silence** confirms that the user stopped speaking rather than pausing for breath. Natural inter-phrase pauses are typically 200-300 ms, so 400-600 ms is a good starting range.
4. **Sentence-end marker** provides evidence of a natural break. On its own it is not enough: "I need a flight. I want to leave tomorrow." should be one turn, which the silence rule handles.

| Field                | Default | Description                                          |
|----------------------|---------|------------------------------------------------------|
| `MinSilence`         | 400ms   | Silence required after speech before a turn can end |
| `SentenceEndMarkers` | `.!?`   | Characters that indicate a complete sentence        |
| `MinTurnLength`      | 10      | Minimum transcript length (characters)               |
| `MaxTurnLength`      | 5000    | Transcript length that forces a turn end            |

## Step 2: Enforce Minimum Silence in the VAD

Beluga's built-in detectors (`voice.EnergyVAD`, `voice/vad/providers/silero`, `voice/vad/providers/webrtc`) classify each frame on its own, so a single quiet frame can end an utterance. Wrap the detector so `VADSpeechEnd` is only reported after `MinSilence` of continuous non-speech audio. The duration comes from the frame size: 16-bit PCM has two bytes per sample.

```go
import (
	"context"
	"sync"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// hangoverVAD wraps an ActivityDetector and delays VADSpeechEnd until
// minSilence of continuous silence has been observed.
type hangoverVAD struct {
	inner      voice.ActivityDetector
	sampleRate int
	minSilence time.Duration

	mu       sync.Mutex
	speaking bool
	silence  time.Duration
}

var _ voice.ActivityDetector = (*hangoverVAD)(nil)

func newHangoverVAD(inner voice.ActivityDetector, sampleRate int, minSilence time.Duration) *hangoverVAD {
	return &hangoverVAD{inner: inner, sampleRate: sampleRate, minSilence: minSilence}
}

func (h *hangoverVAD) DetectActivity(ctx context.Context, audio []byte) (voice.ActivityResult, error) {
	res, err := h.inner.DetectActivity(ctx, audio)
	if err != nil {
		return voice.ActivityResult{}, err
	}
	frameDur := time.Duration(len(audio)/2) * time.Second / time.Duration(h.sampleRate)

	h.mu.Lock()
	defer h.mu.Unlock()

	switch {
	case res.IsSpeech && !h.speaking:
		h.speaking, h.silence = true, 0
		return voice.ActivityResult{IsSpeech: true, EventType: voice.VADSpeechStart, Confidence: res.Confidence}, nil
	case res.IsSpeech:
		h.silence = 0
		// Empty EventType: still speaking, no state transition to report.
		return voice.ActivityResult{IsSpeech: true, Confidence: res.Confidence}, nil
	case h.speaking:
		h.silence += frameDur
		if h.silence >= h.minSilence {
			h.speaking = false
			return voice.ActivityResult{EventType: voice.VADSpeechEnd, Confidence: res.Confidence}, nil
		}
		// Short pause: keep forwarding audio so STT sees the trailing sound.
		return voice.ActivityResult{IsSpeech: true, Confidence: res.Confidence}, nil
	default:
		return voice.ActivityResult{EventType: voice.VADSilence, Confidence: res.Confidence}, nil
	}
}
```

Because the wrapper only reports the end of speech after `MinSilence`, every `SignalEndOfUtterance` the pipeline emits already satisfies the silence rule.

## Step 3: Buffer Transcripts Until the Turn Is Complete

Place a stage after STT that collects text frames and releases them as one turn. On each end-of-utterance signal it applies the `TurnDetector` rules. If the transcript is not complete yet (for example, "I want to..." with no sentence end), it keeps buffering and waits for the next utterance.

```go
import (
	"context"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// turnStage buffers transcript fragments and emits one text frame per turn.
func turnStage(d TurnDetector) voice.FrameProcessor {
	var buf strings.Builder

	flush := func(signal voice.Frame) []voice.Frame {
		text := strings.TrimSpace(buf.String())
		buf.Reset()
		return []voice.Frame{voice.NewTextFrame(text), signal}
	}

	return voice.FrameLoop(func(ctx context.Context, f voice.Frame) ([]voice.Frame, error) {
		switch {
		case f.Type == voice.FrameText:
			if buf.Len() > 0 {
				buf.WriteByte(' ')
			}
			buf.WriteString(f.Text())
			// Enforce the maximum length even while the user keeps talking.
			if d.MaxTurnLength > 0 && buf.Len() >= d.MaxTurnLength {
				return flush(voice.NewControlFrame(voice.SignalEndOfUtterance)), nil
			}
			return nil, nil
		case f.Signal() == voice.SignalEndOfUtterance:
			// The hangover VAD has already enforced MinSilence.
			if d.Complete(buf.String(), d.MinSilence) {
				return flush(f), nil
			}
			return nil, nil // incomplete: wait for more speech
		default:
			return []voice.Frame{f}, nil
		}
	})
}
```

## Step 4: Wire It into the Pipeline

`voice.WithSTT` accepts any `voice.FrameProcessor`, so chain the STT engine and the turn stage together. This uses the types from the previous steps:

```go
import (
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
	"github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

func buildPipeline(transport voice.Transport, llmStage, ttsStage voice.FrameProcessor) (*voice.VoicePipeline, error) {
	const sampleRate = 16000
	rules := DefaultTurnDetector()

	base, err := silero.New(silero.Config{Threshold: 0.5, SampleRate: sampleRate})
	if err != nil {
		return nil, err
	}

	engine, err := stt.New("deepgram", stt.Config{
		SampleRate: sampleRate,
		Extra:      map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
	})
	if err != nil {
		return nil, err
	}

	return voice.NewPipeline(
		voice.WithTransport(transport),
		voice.WithVAD(newHangoverVAD(base, sampleRate, rules.MinSilence)),
		voice.WithSTT(voice.Chain(stt.AsFrameProcessor(engine), turnStage(rules))),
		voice.WithLLM(llmStage),
		voice.WithTTS(ttsStage),
	), nil
}
```

The LLM stage now receives one text frame per complete turn instead of one per audio chunk.

## Tuning for Different Conversation Styles

A fixed threshold that suits one speaking style fails another. Start from these profiles:

| Use case                    | `MinSilence` | `MinTurnLength` | `MaxTurnLength` |
|-----------------------------|--------------|-----------------|-----------------|
| Commands, short queries     | 300-400ms    | 8-10            | 1000-2000       |
| Open conversation (default) | 400-600ms    | 10-20           | 5000            |
| Dictation, storytelling     | 600-800ms    | 20-30           | 10000+          |

Some transcription styles use other punctuation. To treat semicolons, colons, or ellipses as sentence ends, extend the marker set:

```go
rules := DefaultTurnDetector()
rules.SentenceEndMarkers = ".!?;:…"
```

`Complete` checks only the last byte of the transcript, so multi-byte markers such as `…` need a `strings.HasSuffix` check instead of `ContainsAny`.

## Verification

1. Unit-test `TurnDetector.Complete` with short fragments, transcripts without sentence ends, and transcripts at `MaxTurnLength`.
2. Feed `hangoverVAD` synthetic PCM (speech, then a pause shorter than `MinSilence`, then speech) and check that it reports no `VADSpeechEnd` in between.
3. Say "I want to... book a flight." with a short pause in the middle and confirm the LLM receives a single turn.

## Next Steps

- [ML-Based Turn Prediction](/docs/guides/capabilities/voice/ml-turn-prediction) -- Go beyond heuristics
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Tune VAD thresholds alongside turn rules
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Handle barge-in during agent speech
