---
title: Noisy Environment Turn Detection
description: "Tune Beluga AI turn detection for noisy environments like contact centers and factory floors to prevent false speech triggers."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "noisy turn detection, contact center voice, Beluga AI, noise-resistant VAD, voice AI tuning, Go voice pipeline"
---

Default turn detection parameters assume clean audio. In real-world deployments -- contact centers with hold music, retail floors with announcements, or factory environments with machinery -- background noise causes frequent false turn-end triggers that interrupt users. This guide shows how to make end-of-turn detection noise-resistant with the VAD building blocks Beluga ships, so your voice agent waits for genuine speech completion before responding.

## Overview

Beluga AI has no dedicated turn-detection package. In the cascading `voice.VoicePipeline`, end of turn is driven by voice activity detection: when the configured `voice.ActivityDetector` reports `voice.VADSpeechEnd`, the pipeline emits a `voice.SignalEndOfUtterance` control frame (and calls the `OnSpeechEnd` hook). The built-in detectors (`voice.EnergyVAD`, and the `webrtc` and `silero` providers) report speech end on the first non-speech chunk, which is too eager for noisy audio.

Two levers make detection robust:

1. **Reject noise at the VAD.** The `webrtc` provider combines an RMS energy threshold with a zero-crossing-rate (ZCR) threshold; raising the energy threshold and lowering the ZCR threshold filters out broadband noise such as fans, hum, and crowd murmur.
2. **Smooth decisions over time.** Wrap the VAD in a small `voice.ActivityDetector` of your own that requires a minimum stretch of silence before ending the turn and ignores very short bursts.

## Prerequisites

- Go 1.26 or later
- 16-bit mono PCM audio (the format the built-in VADs expect)

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

## Configuration

### A noise-tolerant turn detector

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/lookatitude/beluga-ai/v2/voice"
    _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
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

    // Stricter thresholds than the defaults (1000 / 0.1) for noisy rooms.
    vad, err := voice.NewVAD("webrtc", map[string]any{
        "threshold":     1800.0,
        "zcr_threshold": 0.08,
    })
    if err != nil {
        log.Fatalf("Failed to create VAD: %v", err)
    }

    detector := &TurnDetector{
        Inner:      vad,
        SampleRate: 16000,
        MinSilence: 700 * time.Millisecond,
        MinSpeech:  200 * time.Millisecond,
        MaxTurn:    30 * time.Second,
    }

    chunk := make([]byte, 640) // 20 ms of 16 kHz 16-bit audio
    res, err := detector.DetectActivity(ctx, chunk)
    if err != nil {
        log.Fatalf("Detection failed: %v", err)
    }
    fmt.Printf("event=%q speech=%v\n", res.EventType, res.IsSpeech)
}
```

### Using it in a pipeline

Pass the wrapper wherever a VAD is accepted; the pipeline then emits `SignalEndOfUtterance` only when the smoothed detector ends the turn:

```go
pipe := voice.NewPipeline(
    voice.WithTransport(transport),
    voice.WithVAD(detector),
    voice.WithSTT(sttStage),
    voice.WithLLM(llmStage),
    voice.WithTTS(ttsStage),
    voice.WithHooks(voice.Hooks{
        OnSpeechEnd: func(ctx context.Context) { log.Println("turn ended") },
    }),
)
if err := pipe.Run(ctx); err != nil {
    log.Fatalf("pipeline: %v", err)
}
```

## Configuration Reference

| Setting                  | Where                     | Default  | Noisy environment |
|--------------------------|---------------------------|----------|-------------------|
| `threshold`              | `webrtc` VAD config       | 1000.0   | 1500-2500         |
| `zcr_threshold`          | `webrtc` VAD config       | 0.1      | 0.06-0.09         |
| `MinSilence`             | `TurnDetector` (your code)| -        | 600-800 ms        |
| `MinSpeech`              | `TurnDetector` (your code)| -        | 150-300 ms        |
| `MaxTurn`                | `TurnDetector` (your code)| -        | 20-60 s           |

## Troubleshooting

### Too many false turn-end events in noise

Increase `MinSilence` (600-800 ms). If the VAD itself flickers, raise the `webrtc` energy threshold so noise never counts as speech.

### Missed end-of-turn in noisy segments

The VAD is classifying background noise as speech, so silence never accumulates. Raise `threshold` or lower `zcr_threshold`, and check the audio format: the built-in VADs assume 16-bit little-endian PCM.

### Provider 'webrtc' not registered

Import the provider to trigger registration:

```go
import _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
```

## Advanced Topics

### Production Deployment

- Create one `TurnDetector` per session; it keeps per-stream state
- A/B test thresholds with recorded noisy audio before rollout
- Log `OnSpeechEnd` timestamps to measure false turn-end rate

## Related Resources

- [Heuristic Turn Detection Tuning](/docs/guides/production/integrations/turn-heuristic-tuning)
- [Voice Services Overview](/docs/reference/providers/voice/)
