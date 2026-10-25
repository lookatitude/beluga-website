---
title: Native S2S with Amazon Nova
description: "Build low-latency voice conversations in Go with Beluga AI's speech-to-speech (S2S) interface and the Amazon Nova provider — sessions, bidirectional audio, and interruptions."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, Amazon Nova, S2S, Speech-to-Speech, voice conversation, low-latency"
---

Speech-to-Speech (S2S) models process audio input and produce audio output directly, bypassing the traditional STT-LLM-TTS pipeline. This architectural shift eliminates the latency overhead of intermediate text conversion and preserves tonal and emotional cues that are lost when speech is transcribed to text and back. This tutorial shows how to use Beluga's S2S interface with the Amazon Nova provider: create an engine, open a bidirectional session, stream audio both ways, and handle interruptions.

**Provider status:** the `nova` provider (registered as `"nova"`) calls Bedrock's `InvokeModelWithBidirectionalStream` API through `aws-sdk-go-v2`, so requests are SigV4-signed with your AWS credentials (static keys in `Extra`, or the default AWS credential chain). The session code below is the same for every S2S provider.

## What You Will Build

A real-time voice conversation loop over a Beluga S2S session that sends microphone audio, plays the model's audio, and handles interruptions.

## Prerequisites

- AWS account with Bedrock access to Nova Sonic and AWS credentials available to the default credential chain; or an OpenAI or Gemini API key to run the same code with another provider
- Go 1.26 or later
- Basic understanding of bidirectional audio streams

## S2S vs. Traditional Pipeline

Traditional voice agents use a three-stage pipeline where each stage adds latency and loses information:

```
Audio ──▶ STT ──▶ Text ──▶ LLM ──▶ Text ──▶ TTS ──▶ Audio
```

Each transition introduces delay: STT must wait for enough audio to produce a transcript, the LLM processes text, and TTS synthesizes audio from scratch. Emotional cues like hesitation, excitement, or sarcasm are lost during the STT step and cannot be recovered by TTS.

Native S2S processes audio end-to-end in a single step:

```
Audio ──▶ S2S Model ──▶ Audio
```

The S2S approach eliminates latency from intermediate text conversion and preserves tonal and emotional cues from the speaker's voice. The model can also respond with appropriate intonation because it processes the audio signal directly rather than a text approximation.

## Step 1: Create the S2S Engine

Beluga uses the registry pattern for S2S providers, the same pattern used across all extensible packages. The blank import runs the Nova provider's `init()` function, which registers the `"nova"` factory; `s2s.New` looks it up and creates an engine.

```go
package main

import (
	"context"
	"io"
	"iter"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/s2s"
	_ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/nova"
)

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	engine, err := s2s.New("nova", s2s.Config{
		Model:      "amazon.nova-sonic-v1:0",
		SampleRate: 16000,
		Extra: map[string]any{
			"region": "us-east-1", // credentials come from the default AWS chain
		},
	})
	if err != nil {
		log.Fatalf("create S2S engine: %v", err)
	}

	if err := converse(ctx, engine, microphone(ctx), os.Stdout); err != nil {
		log.Fatal(err)
	}
}

// microphone yields 20 ms PCM frames from your audio source.
func microphone(ctx context.Context) iter.Seq2[[]byte, error] {
	return func(yield func([]byte, error) bool) {}
}

// converse is defined in Steps 2-4.
func converse(ctx context.Context, engine s2s.S2S, mic iter.Seq2[[]byte, error], speaker io.Writer) error {
	return nil
}
```

| `s2s.Config` field | Nova default             | Description                                  |
|--------------------|--------------------------|----------------------------------------------|
| `Model`            | `amazon.nova-sonic-v1:0` | Bedrock model ID                             |
| `Voice`            | `matthew`                | Voice identifier                             |
| `Instructions`     | (none)                   | System instructions for the conversation     |
| `SampleRate`       | `16000`                  | Input audio sample rate in Hz                |
| `Extra["region"]`  | `us-east-1`              | AWS region for the Bedrock Runtime client    |
| `Extra["base_url"]`| SDK-resolved endpoint    | Override the Bedrock Runtime endpoint (`http(s)` only) |

## Step 2: Start a Session

S2S needs a bidirectional session: the model processes input and generates output concurrently, and the session stays open for the whole conversation. `Start` accepts options that override the engine config for this session:

```go
	session, err := engine.Start(ctx,
		s2s.WithVoice("matthew"),
		s2s.WithInstructions("You are a friendly assistant. Keep answers short."),
	)
	if err != nil {
		return fmt.Errorf("start session: %w", err)
	}
	defer session.Close()
```

A `s2s.Session` combines three small interfaces: `SessionSender` (`SendAudio`, `SendText`, `SendToolResult`), `SessionReceiver` (`Recv`), and `SessionControl` (`Interrupt`, `Close`).

## Step 3: Send User Audio and Receive Model Output

Send audio in a goroutine while the main loop ranges over `session.Recv(ctx)`, so neither direction blocks the other. Send small frames: 20 ms at 16 kHz is 640 bytes. Smaller frames let the model start processing sooner, at the cost of more messages.

```go
	sendErr := make(chan error, 1)
	go func() {
		for frame, err := range mic {
			if err != nil {
				sendErr <- err
				return
			}
			if err := session.SendAudio(ctx, frame); err != nil {
				sendErr <- fmt.Errorf("send audio: %w", err)
				return
			}
		}
		sendErr <- nil
	}()

	for event, err := range session.Recv(ctx) {
		if err != nil {
			return fmt.Errorf("receive: %w", err)
		}
		switch event.Type {
		case s2s.EventAudioOutput:
			if _, err := speaker.Write(event.Audio); err != nil {
				return fmt.Errorf("play audio: %w", err)
			}
		case s2s.EventTranscript:
			log.Printf("user: %s", event.Text)
		case s2s.EventTextOutput:
			log.Printf("model: %s", event.Text)
		case s2s.EventTurnEnd:
			log.Println("[S2S] response complete")
		case s2s.EventError:
			log.Printf("provider error: %v", event.Error)
		}
	}
	return <-sendErr
```

Each `s2s.SessionEvent` has a `Type` and, depending on the type, `Audio`, `Text`, `ToolCall`, or `Error`:

| Event type         | Fields used | Meaning                                 |
|--------------------|-------------|-----------------------------------------|
| `EventAudioOutput` | `Audio`     | A chunk of the model's spoken response  |
| `EventTranscript`  | `Text`      | Transcript of the user's speech         |
| `EventTextOutput`  | `Text`      | Text of the model's response            |
| `EventToolCall`    | `ToolCall`  | The model wants to call a tool          |
| `EventTurnEnd`     | none        | The model finished its turn             |
| `EventError`       | `Error`     | A provider-reported error               |

## Step 4: Interruption Handling

S2S models listen to the input stream continuously, so they can react when the user starts speaking over them. Nova detects barge-in itself and ends the turn with `EventTurnEnd`, so its `Interrupt` is a no-op; other providers stop the current response when you call it. Calling `Interrupt` when your own VAD or a push-to-talk button detects barge-in keeps the code provider-neutral:

```go
	if err := session.Interrupt(ctx); err != nil {
		log.Printf("interrupt: %v", err)
	}
```

Also stop local playback and drop any audio you have buffered for the interrupted response. In a frame pipeline built with `s2s.AsFrameProcessor`, sending a `voice.NewControlFrame(voice.SignalInterrupt)` frame calls `Interrupt` for you.

## Architecture

```
User Microphone                              User Speaker
      │                                           ▲
      ▼                                           │
 SendAudio(ctx, audio)                    Recv(ctx)        
      │                                           │
      ▼                                           │
┌─────────────────── S2S Session ──────────────────┐
│                                                   │
│  Audio In ──▶ Amazon Nova Model ──▶ Audio Out     │
│                                                   │
└───────────────────────────────────────────────────┘
```

## Verification

1. Configure AWS credentials for the default credential chain (or switch the provider to `openai` with an API key).
2. Run the application and say "Hello, who are you?"
3. Verify the model responds with voice and that `EventTurnEnd` arrives after each response.
4. Speak over the model while it is responding and confirm the response stops with `EventTurnEnd`.

## Next Steps

- [Configuring S2S Reasoning Modes](/docs/guides/capabilities/voice/s2s-reasoning-modes) -- Optimize for speed or quality
- [Voice Session Interruptions](/docs/guides/capabilities/voice/session-interruptions) -- Session-level interruption management
- [Scalable Voice Backend](/docs/guides/capabilities/voice/scalable-backend) -- Run many concurrent voice sessions
