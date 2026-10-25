---
title: Voice-Enabled IVR System
description: "Replace touch-tone IVR with AI-powered voice response. Reduce abandonment rates with natural language intent detection in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "voice IVR, interactive voice response AI, contact center AI, speech intent detection, Beluga AI, Go, telephony use case"
---

Contact centers with touch-tone IVR systems face high abandonment rates from deep menu trees and frequent mis-presses. Callers navigate through "press 1 for billing, press 2 for support" hierarchies that assume the caller knows which department handles their issue — they often do not, leading to misroutes, transfers, and repeat navigation. Each additional menu level compounds the abandonment problem.

A voice-enabled IVR lets callers speak their intent directly ("I need to dispute a charge"), collapsing multi-level menu trees into a single interaction. This use case demonstrates building a voice-enabled IVR using Beluga AI's frame-based voice pipeline with STT for intent detection and TTS for prompts. The frame pipeline approach is chosen because each stage (audio input, transcription, intent classification, response synthesis) can be tested and deployed independently, and the telephony transport layer can be swapped without changing the intent logic.

## Solution Architecture

```mermaid
graph TB
    Caller[Caller] --> Tel[Telephony]
    Tel --> Pipeline[Voice Pipeline]
    Pipeline --> STT[STT]
    STT --> Intent[Intent Detection]
    Intent --> Router[Router]
    Router --> Queue[ACD Queue]
    Router --> SelfServe[Self-Serve Flow]
    Pipeline --> TTS[TTS]
    TTS --> Tel
```

The system processes caller audio through a frame-based pipeline: STT transcribes the caller's speech, intent detection maps the transcript to a routing decision, and TTS plays confirmation prompts back through the telephony transport.

The intent processor sits between STT and TTS as a custom frame processor, demonstrating the composability of Beluga AI's frame pipeline. This architecture means you can upgrade the intent detection logic (from keyword matching to LLM-based) without modifying the STT or TTS stages.

## Implementation

### Voice Pipeline Setup

The pipeline chains three frame processors: STT for transcription, a custom intent processor for routing logic, and TTS for spoken confirmations. Using `voice.Chain()` connects them so that text frames from STT flow into the intent processor, and text frames from the intent processor flow into TTS for synthesis.

```go
package main

import (
    "context"
    "fmt"
    "os"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/voice"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"

    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/cartesia"
)

func buildIVRPipeline(ctx context.Context) (voice.FrameProcessor, error) {
    sttEngine, err := stt.New("deepgram", stt.Config{
        SampleRate: 8000, // narrowband telephony audio
        Encoding:   "linear16",
        Extra:      map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
    })
    if err != nil {
        return nil, fmt.Errorf("create stt engine: %w", err)
    }

    ttsEngine, err := tts.New("cartesia", tts.Config{
        Voice:      os.Getenv("CARTESIA_VOICE_ID"),
        SampleRate: 8000,
        Extra:      map[string]any{"api_key": os.Getenv("CARTESIA_API_KEY")},
    })
    if err != nil {
        return nil, fmt.Errorf("create tts engine: %w", err)
    }

    sttProc := stt.AsFrameProcessor(sttEngine,
        stt.WithLanguage("en"),
        stt.WithPunctuation(true),
    )

    ttsProc := tts.AsFrameProcessor(ttsEngine, 8000)

    pipeline := voice.Chain(sttProc, intentProcessor(), ttsProc)
    return pipeline, nil
}
```

### Intent Detection and Routing

The intent processor uses `voice.FrameLoop`, Beluga AI's adapter for turning a per-frame function into a frame processor. It passes through non-text frames unchanged and only processes text frames — this pattern ensures audio and control frames propagate correctly through the pipeline. The intent detection uses keyword matching for simplicity and determinism, though it can be replaced with an LLM-based classifier for more nuanced intent recognition.

```go
func intentProcessor() voice.FrameProcessor {
    return voice.FrameLoop(func(ctx context.Context, frame voice.Frame) ([]voice.Frame, error) {
        if frame.Type != voice.FrameText {
            return []voice.Frame{frame}, nil
        }
        intent := detectIntent(frame.Text())
        response := routeIntent(ctx, intent)
        return []voice.Frame{voice.NewTextFrame(response)}, nil
    })
}

func containsAny(s string, words ...string) bool {
    s = strings.ToLower(s)
    for _, w := range words {
        if strings.Contains(s, w) {
            return true
        }
    }
    return false
}

func detectIntent(transcript string) string {
    // Map transcript to intent using keyword matching or LLM
    switch {
    case containsAny(transcript, "billing", "bill", "payment", "charge"):
        return "billing"
    case containsAny(transcript, "support", "help", "problem", "issue"):
        return "support"
    case containsAny(transcript, "spanish", "espanol"):
        return "spanish"
    default:
        return "unknown"
    }
}

func routeIntent(ctx context.Context, intent string) string {
    switch intent {
    case "billing":
        return "Transferring you to billing."
    case "support":
        return "Transferring you to technical support."
    case "spanish":
        return "Transfiriendo a un agente en espanol."
    default:
        return "Sorry, I didn't catch that. Say billing, support, or language."
    }
}
```

## Deployment Considerations

- **Telephony integration**: Beluga's `voice/telephony` package defines the `TelephonyProvider`, `SIPEndpoint`, and `CallRouter` interfaces (plus a `PrefixRouter`), but ships no carrier provider. Bridge your carrier's media stream to the pipeline with `transport.NewWebSocketTransport`, and implement `TelephonyProvider` for call control
- **Concurrent sessions**: Configure maximum concurrent sessions and reject or queue callers at capacity
- **Multi-language**: Design intent sets and prompts for each language upfront
- **Fallback**: Keep DTMF as fallback for noisy or non-English callers
- **Observability**: Instrument STT, routing decisions, and telephony events with OpenTelemetry

## What to Measure

Track IVR completion rate, average time to route, and misroute rate before and after the rollout, so you can see whether the voice front end actually helps your callers.

### Lessons Learned

- **Structured intents**: A limited set of intents (billing, support, language) improved accuracy and latency
- **Confirmation prompts**: Short TTS confirmations reduced misroutes
- **Start small**: Begin with a small intent set and expand based on caller data

## Related Resources

- [Voice AI Applications](/docs/guides/capabilities/voice/voice-applications/) for full voice pipeline patterns
- [Voice Sessions Overview](/docs/guides/capabilities/voice/voice-sessions-overview/) for session management
- [Outbound Calling](/docs/guides/capabilities/voice/outbound-calling/) for outbound voice patterns
