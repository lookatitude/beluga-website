---
title: Cloning Voices with ElevenLabs
description: "Use ElevenLabs cloned voices for TTS in Go with Beluga AI — configure the provider with a Voice ID, generate audio, and stream synthesis sentence by sentence."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, ElevenLabs, voice cloning, TTS, speech synthesis, streaming audio"
---

ElevenLabs provides high-fidelity voice synthesis, including cloned voices. A cloned voice is a synthetic voice that closely matches a real person's voice, which is valuable for brand consistency, personalization, and accessibility. You create the clone in ElevenLabs (the Voice Lab dashboard or their API); Beluga then uses it by Voice ID like any other voice. This tutorial shows how to configure the ElevenLabs TTS provider with a cloned voice, generate audio, and stream synthesis for lower latency.

## What You Will Build

A text-to-speech setup using ElevenLabs that speaks with a cloned or professional voice, saves complete audio files, and streams audio sentence by sentence for playback.

## Prerequisites

- ElevenLabs API key
- At least one Voice ID from the ElevenLabs Voice Lab dashboard

## Step 1: Configure the ElevenLabs Provider

Create a TTS engine through the registry with your Voice ID and model. The blank import runs the provider's `init()` function, which registers the `"elevenlabs"` factory. `Voice` takes the ElevenLabs Voice ID, not a display name; the ID maps to a specific voice profile, including cloned voices you created in the Voice Lab.

```go
package main

import (
	"context"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/tts"
	_ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

func main() {
	ctx := context.Background()

	engine, err := tts.New("elevenlabs", tts.Config{
		Voice: "pMsXg91Y39Z99L9Z9999", // your cloned Voice ID
		Model: "eleven_multilingual_v2",
		Extra: map[string]any{"api_key": os.Getenv("ELEVENLABS_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create TTS engine: %v", err)
	}

	audio, err := engine.Synthesize(ctx, "Welcome to the future of voice agents.")
	if err != nil {
		log.Fatalf("synthesize: %v", err)
	}

	if err := os.WriteFile("output.mp3", audio, 0o644); err != nil {
		log.Fatalf("write file: %v", err)
	}
	log.Println("Audio saved to output.mp3")
}
```

The `eleven_multilingual_v2` model provides multilingual synthesis. If you omit `Model`, the provider uses `eleven_monolingual_v1`; if you omit `Voice`, it uses the stock "Rachel" voice. The provider returns MP3 audio (`audio/mpeg`).

Per-call options override the engine config, so one engine can speak with several voices: `engine.Synthesize(ctx, text, tts.WithVoice(otherVoiceID))`.

## Step 2: Voice Settings for Clone Fidelity

ElevenLabs exposes `stability` and `similarity_boost` controls that balance natural variation against fidelity to the original voice. Beluga's ElevenLabs provider currently sends fixed values, `stability: 0.5` and `similarity_boost: 0.75`, and does not read these settings from `tts.Config`. Those defaults are a reasonable middle ground for cloned voices.

| Setting            | Effect                                                                     |
|--------------------|----------------------------------------------------------------------------|
| `stability`        | Lower values add natural variation; higher values give consistent delivery. Conversational agents tend to sound better at 0.3-0.6, narration at 0.7-0.9. |
| `similarity_boost` | How closely the output matches the original voice sample. Higher values matter for cloned voices where speaker identity is important. |

If you need different values, set them as the voice's default settings in ElevenLabs, or implement your own `tts.TTS` that calls the ElevenLabs API with the settings you want and register it with `tts.Register`.

## Step 3: Streaming Synthesis

For voice applications where time to first audio matters, use `SynthesizeStream`. It takes an iterator of text chunks, typically sentences from a streaming LLM response, and yields one audio chunk per text chunk as soon as it is synthesized. Playback of the first sentence can start while later sentences are still being generated.

```go
import (
	"context"
	"io"
	"iter"

	"github.com/lookatitude/beluga-ai/v2/voice/tts"
)

// sentences yields text chunks for synthesis, for example from an LLM stream.
func sentences(parts ...string) iter.Seq2[string, error] {
	return func(yield func(string, error) bool) {
		for _, p := range parts {
			if !yield(p, nil) {
				return
			}
		}
	}
}

// speak streams synthesized audio for each sentence to out as it arrives.
func speak(ctx context.Context, engine tts.TTS, out io.Writer) error {
	text := sentences("This sentence is synthesized first.", "This one follows right after.")
	for chunk, err := range engine.SynthesizeStream(ctx, text) {
		if err != nil {
			return err
		}
		if _, err := out.Write(chunk); err != nil {
			return err
		}
	}
	return nil
}
```

The ElevenLabs provider makes one synthesis request per text chunk, so chunk your text at sentence boundaries: very short chunks add per-request overhead, and very long ones delay the first audio.

To use the engine in a cascading voice pipeline, wrap it with `tts.AsFrameProcessor(engine, sampleRate)` and pass it to `voice.WithTTS`. Because ElevenLabs returns MP3, the client or transport must decode MP3. If your pipeline needs raw PCM, use a provider that returns it, such as `cartesia`.

## Architecture

```
Text ──────────────▶ Synthesize() ──────────▶ []byte (complete MP3)

iter.Seq2[string] ─▶ SynthesizeStream() ────▶ iter.Seq2[[]byte] (one chunk per sentence)
```

## Verification

1. Set the `ELEVENLABS_API_KEY` environment variable and your Voice ID.
2. Run Step 1 and play `output.mp3`; check that it sounds like the cloned voice.
3. Run `speak` with several sentences and confirm the first chunk arrives before the last sentence is synthesized.
4. Compare the clone with different voice settings configured in the ElevenLabs dashboard.

## Next Steps

- [SSML Tuning for Expressive Speech](/docs/guides/capabilities/voice/ssml-tuning) -- Add pauses, emphasis, and prosody control
- [Native S2S with Amazon Nova](/docs/guides/capabilities/voice/s2s-amazon-nova) -- End-to-end voice-to-voice models
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Integrate TTS into full voice sessions
