---
title: "Handling Long Utterances"
description: "Recipe for chunking and buffering long user speech in Go with turn-aware flushing to keep voice sessions responsive and avoid timeouts."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, long utterances, Go speech chunking, audio buffering, turn-aware flushing, voice session, timeout prevention recipe"
---

## Problem

Users sometimes deliver extended monologues without clear turn boundaries: detailed problem descriptions, lengthy instructions, storytelling, or open-ended brainstorming. Long utterances create multiple challenges for voice systems. First, accumulating audio in memory until the user stops speaking risks exhausting buffer capacity, causing dropped audio or system instability. Second, many STT providers impose duration limits (typically 30-60 seconds per request) or perform poorly on very long continuous audio due to model context windows. Third, waiting for complete utterance transcription before beginning LLM processing increases latency, making the system feel unresponsive during long input. Fourth, timeouts configured for normal turn lengths may expire during long monologues, terminating processing prematurely and frustrating users.

The challenge is processing long audio incrementally without fragmenting coherent thoughts, maintaining responsive feedback so users know the system is listening, and avoiding resource exhaustion or timeout failures.

## Solution

Chunk audio into fixed-duration segments that STT providers handle efficiently (typically 2-5 seconds), use voice activity detection to identify natural boundaries within long speech for flushing accumulated transcripts, and optionally provide incremental feedback to users indicating continued processing. Chunking keeps buffer sizes bounded and ensures each STT request stays within provider limits. Turn detection identifies sentence boundaries or natural pauses within long monologues where it is safe to flush accumulated transcripts and begin agent processing without fragmenting the user's thought.

The architecture buffers incoming audio until reaching either a chunk duration limit or a turn boundary detected by turn detection. At chunk boundaries, the system sends audio to STT and accumulates the resulting transcript. At turn boundaries (detected via sentence markers and silence), the system flushes accumulated transcripts to the agent for processing and begins a new accumulation cycle. This two-level buffering (chunk-level for STT, turn-level for agent processing) balances STT efficiency with natural conversation flow.

Optional incremental feedback provides users with acknowledgment during long input. Simple strategies include playing a brief tone or saying "I'm listening" after each processed chunk. More sophisticated approaches generate partial agent responses based on interim transcripts, then refine them as more context arrives. This feedback reassures users that the system has not crashed or stopped listening, particularly important in voice-only interfaces where visual feedback is unavailable.

## Code Example

Beluga has no separate turn-detection package, so this example detects the turn boundary itself: a `voice.ActivityDetector` classifies each 20 ms frame, and a run of silence (or a maximum turn duration) ends the turn. Audio is sent to the `stt.STT` engine in 3-second chunks as it accumulates.

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
)

var tracer = otel.Tracer("beluga.voice.long_utterances")

const (
	chunkDuration = 3 * time.Second
	maxTurn       = 30 * time.Second
	minSilence    = 600 * time.Millisecond
	sampleRate    = 16000
	bytesPerSec   = sampleRate * 2   // 16-bit mono
	frameBytes    = bytesPerSec / 50 // 20 ms frames
)

// utteranceBuffer transcribes audio in fixed-size chunks and returns the
// joined transcript when the turn ends.
type utteranceBuffer struct {
	engine  stt.STT
	vad     voice.ActivityDetector
	pending []byte
	parts   []string
	turn    time.Duration
	silence time.Duration
}

// Push adds one frame. It returns the transcript and true when a turn ends.
func (b *utteranceBuffer) Push(ctx context.Context, frame []byte) (string, bool, error) {
	res, err := b.vad.DetectActivity(ctx, frame)
	if err != nil {
		return "", false, fmt.Errorf("vad: %w", err)
	}
	frameDur := time.Duration(len(frame)) * time.Second / bytesPerSec
	b.turn += frameDur
	if res.IsSpeech {
		b.silence = 0
	} else {
		b.silence += frameDur
	}
	b.pending = append(b.pending, frame...)

	if time.Duration(len(b.pending))*time.Second/bytesPerSec >= chunkDuration {
		if err := b.transcribePending(ctx); err != nil {
			return "", false, err
		}
	}
	if b.silence < minSilence && b.turn < maxTurn {
		return "", false, nil
	}

	// Turn boundary: flush the remaining audio and the accumulated text.
	if err := b.transcribePending(ctx); err != nil {
		return "", false, err
	}
	text := strings.Join(b.parts, " ")
	b.parts, b.turn, b.silence = nil, 0, 0
	return text, text != "", nil
}

func (b *utteranceBuffer) transcribePending(ctx context.Context) error {
	if len(b.pending) == 0 {
		return nil
	}
	ctx, span := tracer.Start(ctx, "transcribe_chunk",
		trace.WithAttributes(attribute.Int("chunk_bytes", len(b.pending))))
	defer span.End()

	text, err := b.engine.Transcribe(ctx, b.pending,
		stt.WithSampleRate(sampleRate), stt.WithEncoding("linear16"))
	b.pending = b.pending[:0]
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("transcribe: %w", err)
	}
	span.SetStatus(codes.Ok, "")
	if text != "" {
		b.parts = append(b.parts, text)
	}
	return nil
}

func main() {
	ctx := context.Background()

	engine, err := stt.New("deepgram", stt.Config{
		Extra: map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
	})
	if err != nil {
		log.Fatalf("stt: %v", err)
	}

	buf := &utteranceBuffer{
		engine: engine,
		vad:    voice.NewEnergyVAD(voice.EnergyVADConfig{Threshold: 1000}),
	}

	audio, err := os.ReadFile("monologue.pcm") // 16 kHz 16-bit mono PCM
	if err != nil {
		log.Fatalf("read audio: %v", err)
	}
	for _, frame := range chunkAudio(audio, frameBytes) {
		text, done, err := buf.Push(ctx, frame)
		if err != nil {
			log.Fatalf("push: %v", err)
		}
		if done {
			fmt.Println("turn:", text) // hand the whole turn to the agent
		}
	}
}

func chunkAudio(audio []byte, size int) [][]byte {
	var chunks [][]byte
	for len(audio) > 0 {
		n := min(size, len(audio))
		chunks = append(chunks, audio[:n])
		audio = audio[n:]
	}
	return chunks
}
```

The chunk size follows from duration and sample rate (3 seconds x 16kHz x 2 bytes per sample = 96,000 bytes per chunk). The turn ends after 600 ms of continuous silence or after 30 seconds, whichever comes first.

## Explanation

1. **Chunk size** -- Deriving chunk size from duration and sample rate ensures audio chunks contain the right amount of data for efficient STT processing. Three-second chunks provide enough context for accurate transcription without overwhelming provider APIs or exceeding request size limits. For 16-bit mono audio at 16kHz (common for speech), this yields 96,000 bytes per chunk. For different formats (8kHz narrow-band, 48kHz wideband), adjust the sample rate and bytes per sample accordingly. Keep chunks between 2-5 seconds: shorter chunks increase API call overhead and may lack sufficient context for accurate transcription, longer chunks approach provider limits and increase memory usage.

2. **Turn boundary** -- A long `minSilence` (600ms) accommodates long-form speech: users delivering detailed explanations pause for breath or thought, and those pauses should not end the turn. `maxTurn` ensures that even rambling monologues eventually flush accumulated transcripts and trigger agent processing, preventing unbounded memory growth and providing periodic feedback. When the turn ends, all accumulated transcript chunks go to the agent as a single coherent input. In a `voice.VoicePipeline`, the same idea applies to the VAD you pass with `voice.WithVAD`: the pipeline ends the turn when the detector reports `voice.VADSpeechEnd`.

3. **Buffering** -- Accumulating audio until reaching chunk size or a turn boundary keeps memory usage bounded while maintaining conversation coherence. The buffer holds unprocessed audio (not yet sent to STT) and accumulated transcripts (STT results not yet sent to the agent). Flush at turn boundaries rather than arbitrary time limits to avoid fragmenting user thoughts; the `maxTurn` cap is the safety valve for users who never pause.

**Key insight:** Long utterances are manageable with chunking for STT efficiency, turn-aware flushing for conversation coherence, and optional incremental processing for user feedback. Users should receive acknowledgment at least every 10-15 seconds during long monologues, either through partial agent responses ("I understand so far...") or simple auditory cues, confirming the system has not stopped listening.

## Variations

### Variable Chunk Size

Adjust chunk size based on environment or provider constraints. Mobile connections with limited bandwidth benefit from smaller chunks (1-2 seconds) to reduce upload latency. High-bandwidth connections can use larger chunks (4-5 seconds) to reduce API call overhead. Check provider documentation for optimal chunk sizes: some STT services perform better with specific durations.

### Incremental Feedback

Synthesize a short acknowledgment with your `tts.TTS` engine and send it to the caller during long turns, reassuring users the system is processing their input.

```go
// After each chunk or after N seconds of continuous input
ack, err := ttsEngine.Synthesize(ctx, "Got it, go on")
if err != nil {
	return fmt.Errorf("synthesize ack: %w", err)
}
if err := transport.Send(ctx, voice.NewAudioFrame(ack, 24000)); err != nil {
	return fmt.Errorf("send ack: %w", err)
}
```

### Max Utterance Duration

The `maxTurn` cap in the example is a hard time-based limit. Tune it to your use case: flushing even without a silence boundary ensures timely feedback and prevents accidental microphone activation from consuming unlimited resources.

## Related Recipes

- **[Preemptive Generation](./voice-preemptive-gen)** -- Interim results and latency reduction
- **[Sentence-Boundary Turns](./sentence-boundary-turns)** -- Turn boundaries with sentence detection
- **[Voice Backends Configuration](./voice-backends)** -- Backend provider setup
