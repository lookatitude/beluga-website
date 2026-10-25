---
title: Preemptive Generation Strategies
description: "Reduce perceived voice latency in Go by generating agent replies from interim STT transcripts before the user finishes speaking — with Beluga AI's voice packages."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, preemptive generation, voice latency, interim transcripts, STT, voice AI"
---

Preemptive generation uses interim (partial) STT transcripts to start generating a response before the user finishes speaking. Much of a sentence's meaning is set in its first words: "What is the weather in" almost certainly ends with a location. Starting generation early can produce a usable response by the time the final transcript arrives. When the final transcript confirms the interim, the preemptive response is used right away, hiding most of the LLM latency inside the user's speaking time.

The cost is extra LLM calls per user turn, and a risk of answering the wrong question if the transcript changes at the end. The strategies below let you choose that tradeoff.

## What You Will Build

A preemptive handler that consumes streaming STT events, speculatively generates replies from interim transcripts in the background, and decides on the final transcript whether to use the preemptive reply or regenerate.

## Prerequisites

- Go 1.26 or later
- A streaming STT provider that emits interim results. In Beluga, `assemblyai` emits partial transcripts (`IsFinal: false`) and `gladia` passes through the provider's `is_final` flag. The `deepgram` engine does not request interim results, so it emits only final transcripts.
- An LLM provider for `llm.New`
- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) is recommended background

## The Latency Problem

In a standard pipeline, the agent waits for the final transcript before generating a response, so LLM processing and TTS synthesis happen after the user stops speaking:

```
User speaks ──▶ Silence detected ──▶ Final transcript ──▶ LLM ──▶ TTS ──▶ Audio
                                     ▲ latency starts here
```

With preemptive generation, the LLM call starts during the user's speech. If the interim and final transcripts are similar enough, the response is ready when the user finishes:

```
User speaks ──▶ Interim transcript ──▶ LLM (preemptive) ──▶ Buffer
                    ...
               ──▶ Final transcript ──▶ Compare ──▶ Use preemptive or regenerate
                                                         │
                                                         ▼
                                                   TTS ──▶ Audio
```

## Step 1: Streaming STT Engine

Streaming is essential: batch transcription (`Transcribe`) returns one final transcript and gives you nothing to act on early. `TranscribeStream` takes an audio iterator and returns an iterator of `stt.TranscriptEvent` values, each with `Text` and `IsFinal`:

```go
package main

import (
	"context"
	"fmt"
	"iter"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/assemblyai"
)

func main() {
	ctx := context.Background()

	engine, err := stt.New("assemblyai", stt.Config{
		Language:   "en",
		SampleRate: 16000,
		Extra:      map[string]any{"api_key": os.Getenv("ASSEMBLYAI_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create STT: %v", err)
	}

	for event, err := range engine.TranscribeStream(ctx, microphone(ctx)) {
		if err != nil {
			log.Fatalf("transcribe: %v", err)
		}
		fmt.Printf("final=%v text=%q\n", event.IsFinal, event.Text)
	}
}

// microphone yields 16-bit PCM chunks from your audio source.
func microphone(ctx context.Context) iter.Seq2[[]byte, error] {
	return func(yield func([]byte, error) bool) {
		// Read from your capture device or transport and yield chunks here.
	}
}
```

## Step 2: Choose a Strategy

There are three ways to handle a preemptive response. The choice depends on your tolerance for wrong answers versus your latency budget:

```go
// PreemptiveStrategy determines how to handle preemptive responses.
type PreemptiveStrategy int

const (
	// UseIfSimilar uses the preemptive response if the final transcript
	// is similar to the interim that generated it.
	UseIfSimilar PreemptiveStrategy = iota
	// AlwaysUse uses the preemptive response whenever one is ready.
	AlwaysUse
	// Discard ignores preemptive responses and always generates
	// from the final transcript.
	Discard
)
```

| Strategy     | Latency reduction | Risk                                             |
|--------------|-------------------|--------------------------------------------------|
| UseIfSimilar | Moderate          | Low: falls back to the final if the interim was wrong |
| AlwaysUse    | Maximum           | Medium: may answer the wrong transcript          |
| Discard      | None              | None: standard behavior                          |

Use `UseIfSimilar` or `Discard` when correctness matters. `AlwaysUse` suits rapid-fire Q&A where users will simply rephrase.

## Step 3: Implement the Preemptive Handler

Interim events arrive while earlier generations are still running, so the handler runs each generation in a goroutine, cancels the previous one when a newer interim arrives, and guards its state with a mutex. It also skips interims that barely changed, so you don't pay for an LLM call on every 100-200 ms update.

```go
import (
	"context"
	"strings"
	"sync"
)

// GenerateFunc produces a reply for a transcript, typically by calling an LLM.
type GenerateFunc func(ctx context.Context, transcript string) (string, error)

// generation is one speculative reply for one interim transcript.
type generation struct {
	interim string
	cancel  context.CancelFunc
	done    chan struct{} // closed after reply and err are set
	reply   string
	err     error
}

// PreemptiveHandler manages preemptive generation for one conversation.
type PreemptiveHandler struct {
	strategy  PreemptiveStrategy
	threshold float64 // word-overlap similarity, 0.0-1.0
	generate  GenerateFunc

	mu      sync.Mutex
	current *generation
}

// NewPreemptiveHandler creates a handler with the given strategy.
func NewPreemptiveHandler(strategy PreemptiveStrategy, threshold float64, generate GenerateFunc) *PreemptiveHandler {
	return &PreemptiveHandler{strategy: strategy, threshold: threshold, generate: generate}
}

// OnInterim starts a background generation for an interim transcript.
func (h *PreemptiveHandler) OnInterim(ctx context.Context, interim string) {
	if h.strategy == Discard {
		return
	}
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.current != nil {
		// Skip interims that barely changed since the last generation.
		if similarity(h.current.interim, interim) >= 0.95 {
			return
		}
		h.current.cancel() // the previous interim is stale
	}

	genCtx, cancel := context.WithCancel(ctx)
	g := &generation{interim: interim, cancel: cancel, done: make(chan struct{})}
	h.current = g

	go func() {
		g.reply, g.err = h.generate(genCtx, interim)
		close(g.done)
	}()
}

// OnFinal returns the reply to speak for the final transcript.
func (h *PreemptiveHandler) OnFinal(ctx context.Context, final string) (string, error) {
	h.mu.Lock()
	g := h.current
	h.current = nil
	h.mu.Unlock()

	usable := g != nil && (h.strategy == AlwaysUse ||
		(h.strategy == UseIfSimilar && similarity(g.interim, final) >= h.threshold))

	if usable {
		select {
		case <-g.done: // wait for the in-flight generation; it started earlier
		case <-ctx.Done():
			g.cancel()
			return "", ctx.Err()
		}
		g.cancel() // release the context's resources
		if g.err == nil && g.reply != "" {
			return g.reply, nil
		}
	} else if g != nil {
		g.cancel()
	}

	// Fall back to generating from the final transcript.
	return h.generate(ctx, final)
}

// similarity is the share of words two transcripts have in common.
// Swap in edit distance or embedding similarity for production.
func similarity(a, b string) float64 {
	wordsA := strings.Fields(strings.ToLower(a))
	wordsB := strings.Fields(strings.ToLower(b))
	if len(wordsA) == 0 || len(wordsB) == 0 {
		return 0
	}
	inB := make(map[string]bool, len(wordsB))
	for _, w := range wordsB {
		inB[w] = true
	}
	matches := 0
	for _, w := range wordsA {
		if inB[w] {
			matches++
		}
	}
	return float64(matches) / float64(max(len(wordsA), len(wordsB)))
}
```

Word overlap is fast but crude: "weather in Paris" and "weather in London" overlap by two thirds. Pick a threshold high enough (0.8 is a reasonable start) that a changed key word causes regeneration, or use edit distance or embedding similarity instead.

## Step 4: Wire It to STT, the LLM, and TTS

Feed the STT event stream into the handler. Interim events start speculative generation, and final events resolve the strategy and produce the reply to synthesize. This uses the `engine` and `microphone` from Step 1:

```go
import (
	"context"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/config"
	"github.com/lookatitude/beluga-ai/v2/llm"
	_ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
	"github.com/lookatitude/beluga-ai/v2/schema"
	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	"github.com/lookatitude/beluga-ai/v2/voice/tts"
)

func converse(ctx context.Context, engine stt.STT, speaker tts.TTS) error {
	model, err := llm.New("openai", config.ProviderConfig{
		APIKey: os.Getenv("OPENAI_API_KEY"),
		Model:  "gpt-4o-mini",
	})
	if err != nil {
		return err
	}

	handler := NewPreemptiveHandler(UseIfSimilar, 0.8, func(ctx context.Context, transcript string) (string, error) {
		resp, err := model.Generate(ctx, []schema.Message{
			schema.NewSystemMessage("You are a concise voice assistant."),
			schema.NewHumanMessage(transcript),
		})
		if err != nil {
			return "", err
		}
		return resp.Text(), nil
	})

	for event, err := range engine.TranscribeStream(ctx, microphone(ctx)) {
		if err != nil {
			return err
		}
		if !event.IsFinal {
			handler.OnInterim(ctx, event.Text)
			continue
		}

		reply, err := handler.OnFinal(ctx, event.Text)
		if err != nil {
			log.Printf("generate reply: %v", err)
			continue
		}
		audio, err := speaker.Synthesize(ctx, reply)
		if err != nil {
			log.Printf("synthesize: %v", err)
			continue
		}
		play(audio)
	}
	return nil
}

// play sends synthesized audio to your output device or transport.
func play(audio []byte) {}
```

## Verification

1. Log interim and final transcripts to see how early they stabilize for your users.
2. Measure time from the final transcript to the first audio byte with `Discard` (baseline) and with `UseIfSimilar`.
3. With `UseIfSimilar`, say a sentence whose key word changes at the end ("book a flight to Paris... no, Rome") and check that the handler regenerates.
4. With `AlwaysUse`, check that you get the fastest responses, and note how often they answer a stale transcript.
5. Count LLM calls per turn to confirm the skip-unchanged-interims rule keeps cost in check.

## Next Steps

- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Cancel playback when the user interrupts
- [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary) -- Detect when the user finishes speaking
- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) -- Streaming STT fundamentals
