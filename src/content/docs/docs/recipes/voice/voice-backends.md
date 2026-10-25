---
title: "Voice Backends Configuration"
description: "Recipe for configuring and switching between STT, TTS, and S2S voice backends in Go with provider fallback chains using Beluga AI registry."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, voice backends, Go STT TTS config, provider switching, fallback chain, voice registry, backend configuration recipe"
---

## Problem

You are building a voice agent and need to choose the right voice backend, configure providers with proper settings, switch between providers without code changes, and handle fallback when a provider is unavailable. Voice systems are complex multi-provider stacks: you might use Deepgram for STT, ElevenLabs for TTS, and a WebSocket transport. Each provider has unique configuration parameters, API authentication schemes, and operational characteristics. Hardcoding provider choices into application logic makes it difficult to test alternatives, respond to outages, or optimize costs by switching providers based on usage patterns.

The challenge is decoupling provider selection from application logic. You want to configure providers via environment variables or config files, swap providers without code changes, and implement fallback chains when a primary provider fails. This requires a consistent abstraction layer across heterogeneous providers, where the application code interacts with interfaces rather than concrete provider types.

## Solution

Beluga AI's voice system uses a consistent registry pattern across all voice backends. You can switch providers through configuration, implement automatic fallback, and test with mocks without changing application code. The registry pattern works by having each provider package register itself in an `init()` function, making it available for lookup by name. The application calls `stt.New(name, cfg)`, `tts.New(name, cfg)`, or `s2s.New(name, cfg)` with a provider name string, and the registry returns the appropriate implementation. This design follows Go's `database/sql` driver pattern and Beluga's core extensibility model.

The reasoning behind this approach is operational flexibility. By standardizing on `Register` + `New` + `List`, you gain several benefits: provider selection becomes a runtime configuration parameter (not a compile-time dependency), testing becomes easier (register a mock provider in test `init()`), and fallback chains can iterate through the registry without hardcoding provider names. Each family shares one `Config` struct (language, model, voice, sample rate, and so on); provider-specific settings such as API keys go in `Config.Extra`, and per-call overrides use functional options such as `stt.WithLanguage` or `tts.WithVoice`.

## Recipe 1: Configure STT Provider

Set up Deepgram for real-time speech-to-text. Deepgram is chosen here for its low-latency WebSocket API and high accuracy on conversational speech. The same engine serves batch calls (`Transcribe`) and streaming (`TranscribeStream`, over Deepgram's WebSocket API). The `nova-2` model balances accuracy and speed for general-purpose use.

```go
package main

import (
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram" // Register provider
)

func setupSTT() (stt.STT, error) {
	return stt.New("deepgram", stt.Config{
		Model:       "nova-2",
		Language:    "en-US",
		SampleRate:  16000,
		Encoding:    "linear16",
		Punctuation: true,
		Extra:       map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
	})
}

func main() {
	engine, err := setupSTT()
	if err != nil {
		log.Fatalf("stt: %v", err)
	}
	log.Printf("STT ready: %T (registered: %v)", engine, stt.List())
}
```

## Recipe 2: Configure TTS Provider

Set up ElevenLabs for text-to-speech. ElevenLabs offers natural voices and voice cloning, which matters for applications where users listen for extended periods. `Voice` and `Model` are common `tts.Config` fields; the API key goes in `Extra`.

```go
import (
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/tts"
	_ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs" // Register provider
)

func setupTTS() (tts.TTS, error) {
	return tts.New("elevenlabs", tts.Config{
		Voice:      "21m00Tcm4TlvDq8ikWAM",
		Model:      "eleven_multilingual_v2",
		SampleRate: 24000,
		Extra:      map[string]any{"api_key": os.Getenv("ELEVENLABS_API_KEY")},
	})
}
```

## Recipe 3: Configure S2S Provider

Set up OpenAI Realtime for end-to-end speech conversations. Speech-to-speech (S2S) providers replace the STT → LLM → TTS pipeline by handling the entire conversation flow internally, reducing latency and preserving prosody. Instructions and tools are part of `s2s.Config`.

```go
import (
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/s2s"
	_ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai" // registers "openai_realtime"
)

func setupS2S() (s2s.S2S, error) {
	return s2s.New("openai_realtime", s2s.Config{
		Model:        "gpt-4o-realtime-preview",
		Voice:        "alloy",
		Instructions: "You are a concise, friendly voice assistant.",
		Extra:        map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
	})
}
```

Call `engine.Start(ctx)` to open a session, or wrap the engine with `s2s.AsFrameProcessor` for use in a voice pipeline.

## Recipe 4: Switch Providers via Configuration

Switch providers based on environment variables without code changes. This pattern externalizes provider selection, making it easy to compare providers during development or switch providers in production without redeployment. The `VoiceConfig` struct uses struct tags (`yaml`, `env`) for whichever config loader you use.

```go
import (
	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/assemblyai"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/whisper"
)

type VoiceConfig struct {
	STTProvider string `yaml:"stt_provider" env:"VOICE_STT_PROVIDER"`
	STTAPIKey   string `yaml:"stt_api_key" env:"VOICE_STT_API_KEY"`
	STTModel    string `yaml:"stt_model" env:"VOICE_STT_MODEL"`
}

func setupSTTFromConfig(cfg VoiceConfig) (stt.STT, error) {
	return stt.New(cfg.STTProvider, stt.Config{
		Model: cfg.STTModel,
		Extra: map[string]any{"api_key": cfg.STTAPIKey},
	})
}
```

## Recipe 5: Implement Provider Fallback

Automatic fallback if the primary provider fails. This pattern implements resilience through redundancy. When the primary provider fails (due to API outages, quota limits, or network issues), the fallback chain tries alternative providers. The warning log helps with post-incident analysis. Because `FallbackSTT` implements `stt.STT` itself, it can be wrapped with `stt.AsFrameProcessor` like any single provider.

```go
import (
	"context"
	"fmt"
	"iter"
	"log/slog"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
)

type namedSTT struct {
	name   string
	engine stt.STT
}

type FallbackSTT struct {
	providers []namedSTT
}

var _ stt.STT = (*FallbackSTT)(nil)

func (f *FallbackSTT) Transcribe(ctx context.Context, audio []byte, opts ...stt.Option) (string, error) {
	var lastErr error
	for _, p := range f.providers {
		text, err := p.engine.Transcribe(ctx, audio, opts...)
		if err == nil {
			return text, nil
		}
		lastErr = err
		slog.Warn("STT provider failed, trying next", "provider", p.name, "error", err)
	}
	return "", fmt.Errorf("all providers failed, last error: %w", lastErr)
}

// TranscribeStream uses the primary provider; a consumed audio stream
// cannot be replayed to a second provider.
func (f *FallbackSTT) TranscribeStream(ctx context.Context, audio iter.Seq2[[]byte, error], opts ...stt.Option) iter.Seq2[stt.TranscriptEvent, error] {
	return f.providers[0].engine.TranscribeStream(ctx, audio, opts...)
}
```

## Provider Reference

These are the providers that ship with Beluga AI today. Import each with a blank identifier to register it.

### STT Providers (`voice/stt/providers/...`)

| Registry name | Package | Notes |
|---------------|---------|-------|
| `deepgram` | `deepgram` | HTTP batch, WebSocket streaming |
| `assemblyai` | `assemblyai` | |
| `elevenlabs` | `elevenlabs` | |
| `gladia` | `gladia` | |
| `groq` | `groq` | Hosted Whisper models |
| `whisper` | `whisper` | OpenAI Whisper API |

### TTS Providers (`voice/tts/providers/...`)

| Registry name | Package |
|---------------|---------|
| `elevenlabs` | `elevenlabs` |
| `cartesia` | `cartesia` |
| `playht` | `playht` |
| `lmnt` | `lmnt` |
| `fish` | `fish` |
| `groq` | `groq` |
| `smallest` | `smallest` |

### S2S Providers (`voice/s2s/providers/...`)

| Registry name | Package | Notes |
|---------------|---------|-------|
| `openai_realtime` | `openai` | OpenAI Realtime API over WebSocket |
| `gemini_live` | `gemini` | Gemini Live API |
| `nova` | `nova` | Amazon Nova Sonic; does not sign requests with AWS SigV4 yet, so it cannot authenticate directly against Bedrock |

Other services (Google, Azure, AWS Transcribe, OpenAI TTS) can be added by implementing `stt.STT` or `tts.TTS` and calling `stt.Register` / `tts.Register`.

## Related Recipes

- **[LLM Error Handling](/docs/recipes/llm/llm-error-handling/)** -- Similar error handling and retry patterns
- **[Voice Stream Scaling](/docs/recipes/voice/voice-stream-scaling/)** -- Scaling concurrent voice streams
- **[S2S Voice Metrics](/docs/recipes/voice/s2s-voice-metrics/)** -- Custom metrics for voice systems
