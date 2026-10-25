---
title: Real-Time STT Streaming Tutorial
description: "Implement real-time speech-to-text streaming in Go with Beluga AI's STT engines — send audio incrementally over a WebSocket and handle transcripts as they arrive."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, STT streaming, Deepgram, AssemblyAI, WebSocket, real-time, transcription"
---

Real-time STT streaming lets a voice application process audio incrementally and get transcripts with minimal delay. Batch transcription waits for the complete audio before producing output. Streaming STT processes audio as it arrives, so the agent can start understanding the user before they finish speaking, which enables features like preemptive generation and turn-taking. This tutorial shows how to create a streaming STT engine, feed it audio, and handle transcripts as they arrive.

## What You Will Build

A streaming speech-to-text loop that sends 16 kHz PCM audio chunks to Deepgram over a WebSocket and prints transcripts as they arrive.

## Prerequisites

- Deepgram API key (or another streaming provider, see below)
- Go 1.26 or later
- Basic understanding of audio buffers and PCM encoding

## Step 1: Create the STT Engine

Create an engine from the STT registry. The blank import `_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"` runs the provider's `init()` function, which registers the `"deepgram"` factory. This is the same registration pattern used across all Beluga extensible packages.

```go
package main

import (
	"context"
	"fmt"
	"iter"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
)

func main() {
	ctx := context.Background()

	engine, err := stt.New("deepgram", stt.Config{
		Model:       "nova-2",
		Language:    "en-US",
		SampleRate:  16000,
		Encoding:    "linear16",
		Punctuation: true,
		Extra:       map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create STT engine: %v", err)
	}

	for event, err := range engine.TranscribeStream(ctx, audioSource(ctx)) {
		if err != nil {
			log.Fatalf("transcribe: %v", err)
		}
		if event.IsFinal {
			fmt.Printf("\n[Final] %s (confidence: %.2f)\n", event.Text, event.Confidence)
		} else {
			fmt.Printf("\r[Interim] %s", event.Text)
		}
	}
}

// audioSource yields 20 ms frames of 16 kHz mono 16-bit PCM:
// 16000 samples/s * 0.020 s * 2 bytes/sample = 640 bytes per frame.
func audioSource(ctx context.Context) iter.Seq2[[]byte, error] {
	return func(yield func([]byte, error) bool) {
		frame := make([]byte, 640) // replace with reads from your microphone or transport
		for range 50 {
			if ctx.Err() != nil || !yield(frame, nil) {
				return
			}
		}
	}
}
```

The `stt.Config` fields apply to every provider. Provider-specific settings, such as the API key or a custom `base_url`, go in `Extra`.

## Step 2: How Streaming Works

`TranscribeStream` takes an audio iterator and returns a transcript iterator:

```go
TranscribeStream(ctx context.Context, audioStream iter.Seq2[[]byte, error], opts ...stt.Option) iter.Seq2[stt.TranscriptEvent, error]
```

When you start ranging over the result, the Deepgram engine opens a WebSocket to the provider. It then pulls audio chunks from your iterator in a background goroutine and sends them as they arrive, while yielding transcript events back to your loop. Sending and receiving happen concurrently, even though your code only sees two iterators. The stream ends when the connection closes, when `ctx` is cancelled, or when either side reports an error. To stop early, cancel `ctx` or `break` out of the loop.

Per-call options override the engine's config for one stream, for example `engine.TranscribeStream(ctx, audio, stt.WithLanguage("de"))`.

Smaller audio frames reduce latency, because the model receives data sooner, but increase overhead with more WebSocket messages. 20-50 ms frames are a common choice.

## Step 3: Handle Transcript Events

Each `stt.TranscriptEvent` carries the text and recognition metadata:

| Field        | Type            | Description                                  |
|--------------|-----------------|----------------------------------------------|
| `Text`       | `string`        | Transcribed text                             |
| `IsFinal`    | `bool`          | Whether this is a final (non-revisable) result |
| `Confidence` | `float64`       | Model confidence score (0.0 to 1.0)          |
| `Timestamp`  | `time.Duration` | Offset of the segment in the audio stream    |
| `Language`   | `string`        | Language code                                |
| `Words`      | `[]stt.Word`    | Word-level timing, when the provider returns it |

Errors arrive as the second value of the iterator instead of a field on the event. Always check `err` before using `event`.

Whether you get interim (partial) results depends on the provider. Interim transcripts update continuously as the model refines its prediction; final transcripts are the model's confirmed output for a segment of speech.

| Provider     | Streaming events                                                |
|--------------|-----------------------------------------------------------------|
| `assemblyai` | Partial transcripts (`IsFinal: false`) and final transcripts    |
| `gladia`     | Uses the provider's `is_final` flag                             |
| `deepgram`   | The engine does not request interim results, so events are final |
| `elevenlabs`, `groq`, `whisper` | Final transcripts                             |

If you need interim results, for example for [preemptive generation](/docs/guides/capabilities/voice/preemptive-generation), use `assemblyai`:

```go
engine, err := stt.New("assemblyai", stt.Config{
	SampleRate: 16000,
	Extra:      map[string]any{"api_key": os.Getenv("ASSEMBLYAI_API_KEY")},
})
```

## Step 4: Use the Engine in a Voice Pipeline

In a cascading `voice.VoicePipeline`, wrap the engine with `stt.AsFrameProcessor`. The processor transcribes each audio frame it receives and emits a text frame per non-empty result:

```go
import (
	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/stt"
)

func newPipeline(transport voice.Transport, vad voice.ActivityDetector, engine stt.STT, llm, tts voice.FrameProcessor) *voice.VoicePipeline {
	return voice.NewPipeline(
		voice.WithTransport(transport),
		voice.WithVAD(vad),
		voice.WithSTT(stt.AsFrameProcessor(engine, stt.WithLanguage("en-US"))),
		voice.WithLLM(llm),
		voice.WithTTS(tts),
	)
}
```

`stt.AsFrameProcessor` calls the batch `Transcribe` method per frame, not `TranscribeStream`. Use `TranscribeStream` directly, as in Step 1, when you need interim results or a single long-lived provider connection.

## Architecture

```
Audio source ──▶ iter.Seq2[[]byte] ──▶ [WebSocket] ──▶ Provider API
                                                           │
                                                           ▼
Application ◀── iter.Seq2[TranscriptEvent] ◀── [WebSocket] ◀┘
```

## Verification

1. Set the `DEEPGRAM_API_KEY` environment variable.
2. Replace `audioSource` with reads from a microphone or a 16 kHz WAV file (skip the 44-byte header).
3. Confirm that transcripts print as you speak, not only at the end.
4. Switch to `assemblyai` and confirm that interim transcripts update in place before each final line.

## Next Steps

- [Fine-tuning Whisper for Industry Terms](/docs/guides/capabilities/voice/whisper-finetuning) -- Improve accuracy for specialized vocabulary
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Combine STT with full session management
- [Custom Silero VAD](/docs/guides/capabilities/voice/custom-silero-vad) -- Add voice activity detection to filter silence
