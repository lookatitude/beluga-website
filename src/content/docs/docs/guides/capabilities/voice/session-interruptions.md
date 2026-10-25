---
title: Voice Session Interruptions
description: "Implement barge-in detection and playback cancellation in Go so users can naturally interrupt a speaking voice agent — using Beluga AI's voice session state and VAD."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, voice interruption, barge-in, playback cancellation, VAD, voice session"
---

In natural conversation, speakers interrupt each other. A voice agent that cannot be interrupted feels unresponsive: users expect to cut in with a correction or follow-up without waiting for the agent to finish. This tutorial builds interruptible playback: detect user speech while the agent is speaking, stop playback within one audio chunk, and return to listening. It uses Beluga's `voice.VoiceSession` state machine, a VAD from the `voice` package, and a TTS engine.

## What You Will Build

A `Speaker` that plays synthesized speech in small chunks and can be cancelled mid-utterance, a barge-in watcher that cancels it when the VAD detects user speech, and session state that tracks whether the agent is speaking or listening.

## Prerequisites

- Go 1.26 or later
- A TTS provider API key (this example uses `cartesia`, which returns raw PCM)
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) is recommended background

## The Session State Machine

`voice.VoiceSession` tracks one conversation's state and turn history, and it is safe for concurrent use. `Transition` enforces valid state changes and returns an error for invalid ones:

```
 idle ──▶ listening ──▶ speaking ──▶ listening
              ▲                          │
              └──── (agent done or ──────┘
                     interrupted)
 any state ──▶ idle (reset)
```

A new session starts in `voice.StateIdle`. Move it to `voice.StateListening` when the conversation starts, to `voice.StateSpeaking` while the agent plays audio, and back to `voice.StateListening` when playback ends or the user interrupts. Barge-in is the speaking-to-listening transition triggered by user speech.

## Step 1: Interruptible Playback

Playing a whole synthesized buffer in one write cannot be stopped. The `Speaker` instead writes 20 ms chunks at real-time pace and checks for cancellation between chunks, so an interruption takes effect within about 20 ms. It uses `context.WithCancelCause` to tell an interruption apart from the caller cancelling the context.

```go
// ErrInterrupted is returned by Say when the user barged in.
var ErrInterrupted = errors.New("playback interrupted")

// Speaker plays synthesized speech and can be interrupted mid-utterance.
type Speaker struct {
	engine tts.TTS
	sess   *voice.VoiceSession
	out    io.Writer

	mu     sync.Mutex
	cancel context.CancelCauseFunc
}

func NewSpeaker(engine tts.TTS, sess *voice.VoiceSession, out io.Writer) *Speaker {
	return &Speaker{engine: engine, sess: sess, out: out}
}

// Say synthesizes text and plays it in 20 ms chunks at real-time pace, so an
// interruption takes effect within one chunk.
func (s *Speaker) Say(ctx context.Context, text string) error {
	audio, err := s.engine.Synthesize(ctx, text)
	if err != nil {
		return fmt.Errorf("synthesize: %w", err)
	}

	playCtx, cancel := context.WithCancelCause(ctx)
	s.mu.Lock()
	s.cancel = cancel
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		s.cancel = nil
		s.mu.Unlock()
		cancel(nil)
	}()

	if err := s.sess.Transition(voice.StateSpeaking); err != nil {
		return err
	}
	defer func() {
		// Back to listening, unless an interruption already moved us there.
		if s.sess.CurrentState() == voice.StateSpeaking {
			if err := s.sess.Transition(voice.StateListening); err != nil {
				log.Printf("transition: %v", err)
			}
		}
	}()

	chunk := sampleRate / 50 * 2 // 20 ms of 16-bit mono PCM
	tick := time.NewTicker(20 * time.Millisecond)
	defer tick.Stop()
	for off := 0; off < len(audio); off += chunk {
		select {
		case <-playCtx.Done():
			if errors.Is(context.Cause(playCtx), ErrInterrupted) {
				return ErrInterrupted
			}
			return playCtx.Err()
		case <-tick.C:
		}
		end := min(off+chunk, len(audio))
		if _, err := s.out.Write(audio[off:end]); err != nil {
			return fmt.Errorf("play: %w", err)
		}
	}
	return nil
}

// Interrupt stops the current utterance, if any, and returns to listening.
func (s *Speaker) Interrupt() {
	s.mu.Lock()
	cancel := s.cancel
	s.mu.Unlock()
	if cancel == nil {
		return
	}
	cancel(ErrInterrupted)
	if s.sess.CurrentState() == voice.StateSpeaking {
		if err := s.sess.Transition(voice.StateListening); err != nil {
			log.Printf("transition: %v", err)
		}
	}
}
```

## Step 2: Detect Barge-In

The watcher runs the VAD on every microphone frame. A speech onset while the session is in the speaking state interrupts the speaker. VAD detects speech onset within one audio frame (typically 20-30 ms), much faster than waiting for STT to produce a transcript, so the agent stops sooner.

```go
// watchBargeIn interrupts the speaker when the user starts talking over it.
func watchBargeIn(ctx context.Context, vad voice.ActivityDetector, sess *voice.VoiceSession, sp *Speaker, mic iter.Seq2[[]byte, error]) error {
	speaking := false
	for frame, err := range mic {
		if err != nil {
			return err
		}
		res, err := vad.DetectActivity(ctx, frame)
		if err != nil {
			return err
		}
		onset := res.IsSpeech && !speaking
		speaking = res.IsSpeech
		if onset && sess.CurrentState() == voice.StateSpeaking {
			log.Println("user barged in; stopping playback")
			sp.Interrupt()
		}
	}
	return nil
}
```

A single loud frame (a cough, a door) also counts as an onset here. To require sustained speech before interrupting, wrap the VAD with the debounce wrapper from [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning#step-2-add-minimum-speech-and-silence-durations). Also enable echo cancellation on the client, or the agent's own voice will interrupt it.

## Step 3: Put It Together

The program creates the TTS engine, VAD, and session, starts the watcher, and speaks. An interruption is a normal event, not a failure: `Say` returns `ErrInterrupted` and the conversation continues with the user's new input.

```go
package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"iter"
	"log"
	"os"
	"sync"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/tts"
	_ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/cartesia"
	_ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

const sampleRate = 16000

func main() {
	ctx := context.Background()

	engine, err := tts.New("cartesia", tts.Config{
		Voice:      os.Getenv("CARTESIA_VOICE_ID"),
		SampleRate: sampleRate, // Cartesia returns raw 16-bit PCM
		Extra:      map[string]any{"api_key": os.Getenv("CARTESIA_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create TTS: %v", err)
	}

	vad, err := voice.NewVAD("silero", map[string]any{"threshold": 0.5, "sample_rate": sampleRate})
	if err != nil {
		log.Fatalf("create VAD: %v", err)
	}

	sess := voice.NewSession("session-001")
	if err := sess.Transition(voice.StateListening); err != nil {
		log.Fatalf("start session: %v", err)
	}

	speaker := NewSpeaker(engine, sess, os.Stdout) // replace os.Stdout with your audio output
	go func() {
		if err := watchBargeIn(ctx, vad, sess, speaker, microphone(ctx)); err != nil {
			log.Printf("barge-in watcher: %v", err)
		}
	}()

	err = speaker.Say(ctx, "Hello, how can I help you today?")
	switch {
	case errors.Is(err, ErrInterrupted):
		log.Println("interrupted; listening for the user's new input")
	case err != nil:
		log.Fatalf("say: %v", err)
	}
}

// microphone yields 20 ms PCM frames from your audio input.
func microphone(ctx context.Context) iter.Seq2[[]byte, error] {
	return func(yield func([]byte, error) bool) {}
}
```

In a cascading `voice.VoicePipeline`, the pipeline sends TTS audio through the transport and the client plays it, so the same idea applies at the transport: watch incoming audio during playback and tell the client to stop. [Barge-In Detection](/docs/guides/capabilities/voice/barge-in-detection) shows a transport wrapper that does this. For speech-to-speech engines, `session.Interrupt(ctx)` on an `s2s.Session` cancels the model's current response.

## Verification

1. Run the program with a long utterance and let it play to the end; the session ends in `voice.StateListening`.
2. Speak while the agent is talking and confirm `Say` returns `ErrInterrupted` within a frame or two.
3. Check `sess.CurrentState()` is `voice.StateListening` after the interruption.
4. Tap the desk during playback and decide whether you need the debounce wrapper.

## Next Steps

- [Preemptive Generation](/docs/guides/capabilities/voice/preemptive-generation) -- Start generating replies from interim transcripts
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Tune VAD thresholds for interruption detection
- [Custom Silero VAD](/docs/guides/capabilities/voice/custom-silero-vad) -- Configure voice activity detection
