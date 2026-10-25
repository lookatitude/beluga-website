---
title: Configuring S2S Reasoning Modes
description: "Tune speech-to-speech (S2S) sessions for different interaction styles in Go — model choice, instructions, and switching modes between sessions with Beluga AI."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, S2S, reasoning modes, latency, Speech-to-Speech, voice AI"
---

Speech-to-Speech models can be configured to optimize for different interaction patterns. A fast concierge needs immediate responses, while a patient tutor benefits from deeper reasoning. The key insight is that reasoning depth and latency are directly correlated -- more internal reasoning produces more nuanced responses but delays the start of audio output. Beluga's S2S interface does not have a reasoning-depth or latency-target setting. The levers you control are the model, the instructions, and the voice, set per session. This tutorial shows how to use them to build interaction modes, reduce latency, and switch modes based on user intent.

## What You Will Build

An S2S voice system that supports multiple interaction modes (fast concierge, balanced assistant, deep tutor) with the ability to switch between them at runtime based on conversation context.

## Prerequisites

- An OpenAI API key with Realtime access (or another S2S provider; see [Native S2S with Amazon Nova](/docs/guides/capabilities/voice/s2s-amazon-nova))
- Understanding of the S2S session lifecycle

## The Tradeoff: Speed vs. Thought

Response quality and latency pull in opposite directions. More capable models and longer, more considered answers produce better responses, but take longer to start and to play. Understanding this tradeoff is essential for designing conversational experiences: a customer asking "What time do you close?" expects a near-instant response, while a student asking "Why does gravity bend light?" benefits from a considered explanation.

| Mode      | Typical lever                         | Use case                                |
|-----------|---------------------------------------|-----------------------------------------|
| Concierge | Smaller, faster model; terse instructions | Quick answers, confirmations, greetings |
| Assistant | Default model; moderate instructions | General conversation, Q&A               |
| Tutor     | Most capable model; step-by-step instructions | Complex reasoning, tutoring, analysis |

Measure latency for your provider, model, and network; it varies too much to quote fixed numbers.

## Step 1: Configure a Mode

The engine config sets defaults, and `Start` options override them per session. `s2s.WithModel`, `s2s.WithInstructions`, `s2s.WithVoice`, `s2s.WithTools`, and `s2s.WithSampleRate` are available:

```go
package main

import (
	"context"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/s2s"
	_ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
)

const conciergePrompt = "You are a fast hotel concierge. Give short, 1-sentence answers. Be direct."

func main() {
	ctx := context.Background()

	engine, err := s2s.New("openai", s2s.Config{
		Model: "gpt-4o-realtime-preview",
		Voice: "alloy",
		Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create S2S engine: %v", err)
	}

	// Fast concierge mode: terse instructions keep responses short.
	session, err := engine.Start(ctx, s2s.WithInstructions(conciergePrompt))
	if err != nil {
		log.Fatalf("start session: %v", err)
	}
	defer session.Close()
}
```

If a task needs a more capable text model than the S2S model (for example, a long analysis), use a cascading pipeline for it instead, or a hybrid pipeline that switches to the cascade when tool use is heavy. See [Voice AI Pipeline Guide](/docs/guides/capabilities/voice/voice-ai).

## Step 2: Instructions for Interaction Style

S2S models follow session instructions the way text LLMs follow a system prompt. Instructions matter even more for voice, because response length is how long the user listens. Short, directive instructions produce shorter responses and less time spent speaking.

```go
const (
	tutorPrompt = "You are a patient math tutor. Explain your reasoning step-by-step. " +
		"Use analogies. Confirm the student understands before moving on."
	assistantPrompt = "You are a helpful assistant. Provide clear, moderate-length answers."
)
```

## Step 3: Latency Optimization

To keep microphone-to-speaker latency low, reduce delay at every stage:

1. **Send small frames**: 20 ms audio frames (640 bytes at 16 kHz mono, 960 bytes at 24 kHz) let the model receive input sooner.
2. **Use server-side turn detection**: the `openai` provider configures the session with server-side VAD (`turn_detection: server_vad`), so the model decides when the user finished speaking without an extra client round trip.
3. **Choose the model**: smaller realtime models usually respond faster; compare options from your provider on your own prompts.
4. **Keep responses short**: concise instructions reduce how long each response takes to play.

```go
	session, err := engine.Start(ctx,
		s2s.WithModel(os.Getenv("FAST_REALTIME_MODEL")), // a smaller realtime model from your provider
		s2s.WithSampleRate(24000),
		s2s.WithInstructions(conciergePrompt),
	)
	if err != nil {
		log.Fatalf("start session: %v", err)
	}
```

## Step 4: Dynamic Mode Switching

Session settings are fixed when the session starts, so switching modes means closing the current session and starting a new one with the new settings. Do it at a turn boundary (after `s2s.EventTurnEnd`), and carry context over by including a short summary of the conversation in the new instructions.

```go
import (
	"context"
	"fmt"

	"github.com/lookatitude/beluga-ai/v2/voice/s2s"
)

// ModeConfig holds the session settings for an interaction mode.
type ModeConfig struct {
	Model        string // empty keeps the engine default
	Instructions string
}

var modes = map[string]ModeConfig{
	"concierge": {Instructions: conciergePrompt},
	"assistant": {Instructions: assistantPrompt},
	"tutor":     {Model: "gpt-4o-realtime-preview", Instructions: tutorPrompt},
}

// SwitchMode closes the current session and starts a new one for modeName.
// summary is a short recap of the conversation so far.
func SwitchMode(ctx context.Context, engine s2s.S2S, current s2s.Session, modeName, summary string) (s2s.Session, error) {
	mode, ok := modes[modeName]
	if !ok {
		return nil, fmt.Errorf("unknown mode: %s", modeName)
	}
	if current != nil {
		if err := current.Close(); err != nil {
			return nil, fmt.Errorf("close session: %w", err)
		}
	}

	opts := []s2s.Option{
		s2s.WithInstructions(mode.Instructions + "\n\nConversation so far: " + summary),
	}
	if mode.Model != "" {
		opts = append(opts, s2s.WithModel(mode.Model))
	}

	session, err := engine.Start(ctx, opts...)
	if err != nil {
		return nil, fmt.Errorf("start session for mode %s: %w", modeName, err)
	}
	return session, nil
}
```

How you detect the intent to switch is up to you: a keyword ("explain", "step by step"), a tool the model can call to request a mode change, or a lightweight classifier on the transcript (`s2s.EventTranscript`).

## Verification

1. In concierge mode, ask "What is 2+2?" and measure the time to the first `EventAudioOutput`.
2. In tutor mode, ask "Explain the theory of relativity" and compare response depth and latency.
3. Call `SwitchMode` at a turn boundary and verify the new instructions take effect.

## Next Steps

- [Native S2S with Amazon Nova](/docs/guides/capabilities/voice/s2s-amazon-nova) -- Try a different S2S provider
- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) -- Compare with the traditional pipeline
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Tune VAD thresholds
