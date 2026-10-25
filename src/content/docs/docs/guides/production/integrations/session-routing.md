---
title: Multi-Provider Voice Routing
description: "Route Beluga AI voice sessions to different STT, TTS, or S2S providers based on tenant, region, or feature flags dynamically."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "session routing, multi-provider voice, Beluga AI, A/B testing voice, tenant routing, voice provider selection, Go voice"
---

Production voice deployments rarely use a single provider for all sessions. Enterprise customers may require specific STT providers for compliance, regional latency differences may favor different TTS engines, and A/B testing demands side-by-side provider comparison. Multi-provider session routing selects the optimal voice provider combination per session based on tenant identity, geographic region, or feature flags -- all without code changes. This guide covers implementing a routing layer on top of Beluga AI's voice provider registries (`voice/stt`, `voice/tts`, `voice/s2s`) and `voice.NewPipeline`.

## Overview

Rather than hardcoding a single STT/TTS provider, session routing evaluates context at session creation time and selects the appropriate providers. This supports multi-tenant deployments, A/B testing, and regional optimization without code changes.

## Prerequisites

- Go 1.26 or later
- Multiple STT/TTS or S2S providers configured
- Routing criteria defined (tenant, region, feature flags)

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2
```

## Configuration

### Define Routing Context

Establish what drives provider selection for each session:

```go
type RouteContext struct {
    SessionID string
    TenantID  string
    Region    string
    Features  map[string]bool
}
```

### Implement the Router

Every voice provider family has a registry, so a router only needs to pick provider names and configs. `stt.New`, `tts.New`, and `s2s.New` return the `stt.STT`, `tts.TTS`, and `s2s.S2S` interfaces:

```go
import (
    "context"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/s2s"
    _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/assemblyai"
    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/cartesia"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

type Providers struct {
    STT stt.STT
    TTS tts.TTS
    S2S s2s.S2S // set instead of STT/TTS for speech-to-speech routes
}

func SelectProviders(ctx context.Context, rc RouteContext) (Providers, error) {
    if rc.Features["s2s"] {
        engine, err := s2s.New("openai_realtime", s2s.Config{
            Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
        })
        return Providers{S2S: engine}, err
    }

    sttName, sttKey := "deepgram", os.Getenv("DEEPGRAM_API_KEY")
    if rc.Region == "eu" {
        sttName, sttKey = "assemblyai", os.Getenv("ASSEMBLYAI_API_KEY")
    }
    sttEngine, err := stt.New(sttName, stt.Config{Extra: map[string]any{"api_key": sttKey}})
    if err != nil {
        return Providers{}, err
    }

    ttsName, ttsKey := "elevenlabs", os.Getenv("ELEVENLABS_API_KEY")
    if rc.Features["low_latency_tts"] {
        ttsName, ttsKey = "cartesia", os.Getenv("CARTESIA_API_KEY")
    }
    ttsEngine, err := tts.New(ttsName, tts.Config{Extra: map[string]any{"api_key": ttsKey}})
    if err != nil {
        return Providers{}, err
    }
    return Providers{STT: sttEngine, TTS: ttsEngine}, nil
}
```

Use a configuration file or database lookup to map tenant/region to provider names and configs.

## Usage

### Build a Pipeline from the Routed Providers

Wrap the engines as frame processors and build a cascading `voice.VoicePipeline`, or wrap the S2S engine for a speech-to-speech route:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice"
    "github.com/lookatitude/beluga-ai/v2/voice/s2s"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"
)

func buildPipeline(ctx context.Context, rc RouteContext, transport voice.Transport, llmStage voice.FrameProcessor) (*voice.VoicePipeline, error) {
    p, err := SelectProviders(ctx, rc)
    if err != nil {
        return nil, err
    }
    sess := voice.NewSession(rc.SessionID)

    if p.S2S != nil {
        // A pipeline with a single processor stage: transport -> S2S -> transport.
        return voice.NewPipeline(
            voice.WithTransport(transport),
            voice.WithLLM(s2s.AsFrameProcessor(p.S2S)),
            voice.WithSession(sess),
        ), nil
    }
    return voice.NewPipeline(
        voice.WithTransport(transport),
        voice.WithVAD(voice.NewEnergyVAD(voice.EnergyVADConfig{})),
        voice.WithSTT(stt.AsFrameProcessor(p.STT)),
        voice.WithLLM(llmStage),
        voice.WithTTS(tts.AsFrameProcessor(p.TTS, 24000)),
        voice.WithSession(sess),
    ), nil
}
```

`voice.NewHybridPipeline` is the alternative when a single session should switch between S2S and cascade modes based on a `voice.SwitchPolicy`.

### Choose VAD per Route

VAD detectors also come from a registry, so the route can pick one by name:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice"
    _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/webrtc"
)

vad, err := voice.NewVAD("webrtc", map[string]any{"threshold": 1200.0})
if err != nil {
    return nil, err
}
pipe := voice.NewPipeline(
    voice.WithTransport(transport),
    voice.WithVAD(vad),
    voice.WithSTT(stt.AsFrameProcessor(p.STT)),
    voice.WithLLM(llmStage),
    voice.WithTTS(tts.AsFrameProcessor(p.TTS, 24000)),
)
```

Beluga has no separate turn-detection package; end of turn follows the VAD's speech-end event. See [Heuristic Turn Detection Tuning](/docs/guides/production/integrations/turn-heuristic-tuning) for a smoothing wrapper.

## Configuration Reference

| Option       | Description                             | Default             |
|--------------|-----------------------------------------|---------------------|
| Routing key  | Tenant, region, feature flags           | Application-defined |
| Provider map | Tenant/region to STT/TTS/S2S provider name and config | Config file or DB |
| Fallback     | Default provider when route is missing  | Application-defined |

## Troubleshooting

### Provider not found for tenant

Fall back to a default provider. Log and emit metrics for missing mappings to identify configuration gaps.

### Session creation fails after routing

Validate provider configuration at startup or in a readiness check. Return clear errors with the routing context included for debugging.

### Switching providers mid-session

A `voice.VoicePipeline` keeps the processors it was built with. Provider failover requires building a new pipeline (you can carry the same `voice.VoiceSession` across). Design routing logic to execute at session start only.

## Advanced Topics

### Production Deployment

- **Caching**: Reuse provider instances per tenant/region to avoid creating new ones for every session
- **Observability**: Tag metrics and traces with route context (tenant, region) for debugging
- **Testing**: Unit-test the router with mock providers; integration-test one or two representative routes

## Related Resources

- [Voice Session Persistence](/docs/guides/production/integrations/session-persistence)
- [Voice Services Overview](/docs/guides/production/integrations/voice-services)
