---
title: Heuristic Turn Detection Tuning
description: "Tune heuristic end-of-turn detection in Beluga AI voice pipelines with silence duration, minimum speech, and maximum turn length."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "turn detection, voice AI, heuristic tuning, Beluga AI, silence detection, conversation turn, Go voice pipeline"
---

Accurate turn detection is critical to conversational voice UX. If the system cuts in too early, users feel interrupted; if it waits too long, conversations feel sluggish. A heuristic detector uses silence duration and turn-length limits to decide when a speaker has finished. It is lightweight, has no model dependency, and works well when the audio is reasonably clean.

## Overview

Beluga AI has no dedicated turn-detection package. In `voice.VoicePipeline`, end of turn follows voice activity detection: when the configured `voice.ActivityDetector` returns `voice.VADSpeechEnd`, the pipeline emits a `voice.SignalEndOfUtterance` control frame and calls the `OnSpeechEnd` hook. The built-in detectors report speech end on the first silent chunk, so a natural pause mid-sentence ends the turn.

The heuristic below is a small wrapper you own. It implements `voice.ActivityDetector`, delegates the speech/no-speech decision to a real VAD, and adds three knobs: minimum silence before ending a turn, minimum speech before starting one, and a maximum turn length.

## Prerequisites

- Go 1.26 or later
- 16-bit mono PCM audio

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

## Configuration

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/lookatitude/beluga-ai/v2/voice"
)

// TurnDetector wraps a voice.ActivityDetector and smooths its decisions
// into turns. It reports VADSpeechEnd only after MinSilence of continuous
// non-speech audio, ignores speech bursts shorter than MinSpeech, and forces
// a turn end after MaxTurn. Audio must be 16-bit mono PCM at SampleRate.
// A TurnDetector holds per-stream state: use one per session.
type TurnDetector struct {
    Inner      voice.ActivityDetector
    SampleRate int
    MinSilence time.Duration
    MinSpeech  time.Duration
    MaxTurn    time.Duration

    speaking bool
    speech   time.Duration
    silence  time.Duration
    turn     time.Duration
}

var _ voice.ActivityDetector = (*TurnDetector)(nil)

func (d *TurnDetector) DetectActivity(ctx context.Context, audio []byte) (voice.ActivityResult, error) {
    res, err := d.Inner.DetectActivity(ctx, audio)
    if err != nil {
        return voice.ActivityResult{}, err
    }
    chunk := time.Duration(len(audio)/2) * time.Second / time.Duration(d.SampleRate)

    if !d.speaking {
        if !res.IsSpeech {
            d.speech = 0 // a short burst followed by silence was noise
            return voice.ActivityResult{EventType: voice.VADSilence}, nil
        }
        d.speech += chunk
        if d.speech < d.MinSpeech {
            return voice.ActivityResult{EventType: voice.VADSilence}, nil
        }
        d.speaking, d.silence, d.turn = true, 0, d.speech
        return voice.ActivityResult{IsSpeech: true, EventType: voice.VADSpeechStart, Confidence: res.Confidence}, nil
    }

    d.turn += chunk
    if res.IsSpeech {
        d.silence = 0
    } else {
        d.silence += chunk
    }
    if d.silence >= d.MinSilence || (d.MaxTurn > 0 && d.turn >= d.MaxTurn) {
        d.speaking, d.speech = false, 0
        return voice.ActivityResult{EventType: voice.VADSpeechEnd, Confidence: res.Confidence}, nil
    }
    // Still inside the turn: keep forwarding audio (including short pauses)
    // without emitting a new transition.
    return voice.ActivityResult{IsSpeech: true, Confidence: res.Confidence}, nil
}

func main() {
    ctx := context.Background()

    detector := &TurnDetector{
        Inner:      voice.NewEnergyVAD(voice.EnergyVADConfig{Threshold: 1000}),
        SampleRate: 16000,
        MinSilence: 500 * time.Millisecond,
        MinSpeech:  100 * time.Millisecond,
        MaxTurn:    20 * time.Second,
    }

    chunk := make([]byte, 640) // 20 ms of 16 kHz 16-bit audio
    res, err := detector.DetectActivity(ctx, chunk)
    if err != nil {
        log.Fatalf("Detection failed: %v", err)
    }
    fmt.Printf("event=%q speech=%v\n", res.EventType, res.IsSpeech)
}
```

Use it as the pipeline VAD with `voice.WithVAD(detector)`.

## Usage

### Verifying the silence threshold

Feed silent chunks after speech and check when `VADSpeechEnd` appears. With 20 ms chunks and `MinSilence` of 500 ms, the turn should end on the 25th silent chunk:

```go
silent := make([]byte, 640)
for i := 1; i <= 30; i++ {
    res, err := detector.DetectActivity(ctx, silent)
    if err != nil {
        log.Fatalf("Detection failed: %v", err)
    }
    if res.EventType == voice.VADSpeechEnd {
        fmt.Printf("turn ended after %d silent chunks\n", i)
        break
    }
}
```

### Tuning Guidelines

| Goal                  | Adjustment                                                        |
|-----------------------|-------------------------------------------------------------------|
| Faster response       | Decrease `MinSilence` (300-400 ms). Risk: more false turn-end.    |
| Fewer false turn-end  | Increase `MinSilence` (600-800 ms). Risk: slower response.        |
| Ignore coughs/clicks  | Increase `MinSpeech` (150-300 ms).                                |
| Longer monologues     | Increase `MaxTurn`, or set it to 0 to disable the cap.            |
| Quieter speakers      | Lower the inner VAD threshold (`EnergyVADConfig.Threshold`).      |

## Configuration Reference

| Field        | Description                                   | Suggested start |
|--------------|-----------------------------------------------|-----------------|
| `Inner`      | Underlying VAD (`voice.EnergyVAD`, `webrtc`, `silero`) | `EnergyVAD`, threshold 1000 |
| `SampleRate` | PCM sample rate in Hz                         | 16000           |
| `MinSilence` | Silence required to end a turn                | 500 ms          |
| `MinSpeech`  | Speech required to start a turn               | 100 ms          |
| `MaxTurn`    | Force a turn end after this long (0 = off)    | 20 s            |

## Troubleshooting

### Turn detected too late

Lower `MinSilence` (350-450 ms). If silence never accumulates, the inner VAD is treating background noise as speech; raise its threshold.

### Turn detected too early / user gets cut off

Increase `MinSilence` (600-700 ms) so mid-sentence pauses do not end the turn.

### Durations look wrong

`TurnDetector` derives chunk duration from byte length assuming 16-bit mono PCM. Set `SampleRate` to the real rate of your audio.

## Advanced Topics

### Production Deployment

- Create one detector per session; it holds per-stream state
- Record `OnSpeechEnd` timing (via `voice.Hooks`) to monitor turn-end rate and latency
- See [Noisy Environment Turn Detection](/docs/guides/production/integrations/noisy-turn-detection) for VAD thresholds that suit loud environments

## Related Resources

- [Custom Turn Detectors for Noisy Environments](/docs/guides/production/integrations/noisy-turn-detection)
- [Voice Services Overview](/docs/reference/providers/voice/)
