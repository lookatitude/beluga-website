---
title: Voice AI Applications in Go
description: "Build voice-enabled applications with STT, TTS, S2S, and composable frame-based pipelines. Production-ready Go voice system."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "voice AI application, STT TTS pipeline, speech-to-speech, frame processor, voice assistant Go, Beluga AI, voice use case"
---

Voice interfaces enable natural, hands-free interaction with AI systems. Unlike text-based interfaces that require a screen and keyboard, voice reaches users in situations where their hands and eyes are occupied — driving, cooking, operating equipment, or navigating a physical environment. The technical challenge is that voice processing involves multiple interdependent stages (audio capture, speech detection, transcription, response generation, synthesis) that must coordinate with sub-second latency to feel conversational.

Beluga AI provides a frame-based voice pipeline that composes STT (speech-to-text), TTS (text-to-speech), S2S (speech-to-speech), VAD (voice activity detection), and transport layers into flexible processing chains. The frame-based design was chosen over monolithic pipeline architectures because it allows each stage to be developed, tested, and swapped independently. A hotel concierge and a meeting transcription system share the same VAD and STT components but differ in downstream processing — the frame model makes this composition natural without framework-level abstraction leaks.

## Voice Pipeline Architecture

Beluga AI's voice system is built around the `FrameProcessor` interface. STT, TTS, and your agent logic are frame processors that take an input frame stream and return an output frame stream. Frame processors compose into pipelines using `voice.Chain()`, and `voice.NewPipeline` adds the transport and VAD (an `ActivityDetector`) around them.

This composable design follows the Unix pipe philosophy: each processor does one thing well, and complex behavior emerges from composition rather than configuration. You can insert a noise filter before VAD, add logging between stages, or swap a Deepgram STT for Whisper without touching any other component in the chain.

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Audio   │───▶│   VAD   │───▶│   STT   │───▶│  Agent  │───▶│   TTS   │
│  Input   │    │ (Silero)│    │(Deepgram│    │ (LLM +  │    │(ElevenL │
│ (WebSocket)│  │         │    │ Whisper)│    │  Tools) │    │Cartesia)│
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     Frames ──────▶ Frames ──────▶ Frames ──────▶ Frames ──────▶ Frames
```

## Frame Processing Basics

All voice components implement the `FrameProcessor` interface:

```go
// FrameProcessor (in package voice) processes a stream of frames
type FrameProcessor interface {
    Process(ctx context.Context, in iter.Seq2[Frame, error]) iter.Seq2[Frame, error]
}

// Compose processors into a single processor
chain := voice.Chain(
    sttProcessor,
    agentProcessor,
    ttsProcessor,
)
```

Frames carry typed data — audio, text, control signals, or images:

```go
// Audio frame from microphone or WebSocket
audioFrame := voice.NewAudioFrame(pcmData, 16000)

// Text frame from STT or agent
textFrame := voice.NewTextFrame("Hello, how can I help?")

// Control frame for signaling
endOfTurn := voice.NewControlFrame(voice.SignalEndOfUtterance)
```

## Use Case 1: Real-Time AI Concierge

A hotel concierge that handles guest inquiries, makes reservations, and provides information through natural voice conversations. Uses S2S (speech-to-speech) for the lowest possible latency — S2S processes audio end-to-end without separate STT/TTS stages, reducing the number of network round-trips and eliminating text as an intermediate representation.

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "io"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/schema"
    "github.com/lookatitude/beluga-ai/v2/tool"
    "github.com/lookatitude/beluga-ai/v2/voice/s2s"

    _ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
)

// Hotel systems the tools call into; implement these for your property.
type BookingSystem interface {
    Reserve(ctx context.Context, in BookingInput) (string, error)
}

type HotelDB interface {
    Lookup(ctx context.Context, topic string) (string, error)
}

func createConcierge(ctx context.Context, bookings BookingSystem, hotelDB HotelDB, guestAudio <-chan []byte, speaker io.Writer) error {
    // Define concierge tools
    bookingTool := tool.NewFuncTool(
        "make_reservation",
        "Make a restaurant, spa, or activity reservation for the guest",
        func(ctx context.Context, input BookingInput) (*tool.Result, error) {
            confirmation, err := bookings.Reserve(ctx, input)
            if err != nil {
                return tool.ErrorResult(err), nil
            }
            return tool.TextResult(fmt.Sprintf("Reservation confirmed: %s", confirmation)), nil
        },
    )

    infoTool := tool.NewFuncTool(
        "hotel_info",
        "Look up hotel information (hours, amenities, directions)",
        func(ctx context.Context, input InfoInput) (*tool.Result, error) {
            info, err := hotelDB.Lookup(ctx, input.Topic)
            if err != nil {
                return tool.ErrorResult(err), nil
            }
            return tool.TextResult(info), nil
        },
    )

    tools := tool.NewRegistry()
    for _, t := range []tool.Tool{bookingTool, infoTool} {
        if err := tools.Add(t); err != nil {
            return fmt.Errorf("register tool: %w", err)
        }
    }

    // Create the S2S engine
    engine, err := s2s.New("openai", s2s.Config{
        Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
    })
    if err != nil {
        return fmt.Errorf("create s2s engine: %w", err)
    }

    // Start a streaming session with the tools declared
    session, err := engine.Start(ctx,
        s2s.WithVoice("alloy"),
        s2s.WithInstructions("You are a luxury hotel concierge. Be warm, professional, "+
            "and helpful. Use the guest's name when known."),
        s2s.WithTools([]schema.ToolDefinition{
            tool.ToDefinition(bookingTool),
            tool.ToDefinition(infoTool),
        }),
    )
    if err != nil {
        return fmt.Errorf("start session: %w", err)
    }
    defer session.Close()

    // Forward the guest's microphone audio to the session
    go func() {
        for chunk := range guestAudio {
            if err := session.SendAudio(ctx, chunk); err != nil {
                log.Printf("send audio: %v", err)
                return
            }
        }
    }()

    // Process events from the session
    for event, err := range session.Recv(ctx) {
        if err != nil {
            return fmt.Errorf("session: %w", err)
        }
        switch event.Type {
        case s2s.EventAudioOutput:
            // Send audio to the guest's device
            if _, err := speaker.Write(event.Audio); err != nil {
                return fmt.Errorf("write audio: %w", err)
            }
        case s2s.EventToolCall:
            // Execute the tool and return the result to the model
            result := executeTool(ctx, tools, *event.ToolCall)
            if err := session.SendToolResult(ctx, result); err != nil {
                return fmt.Errorf("send tool result: %w", err)
            }
        case s2s.EventTranscript:
            // Log transcript for quality assurance
            log.Printf("Guest: %s", event.Text)
        }
    }

    return nil
}

// executeTool runs a tool call from the model and converts the outcome to a ToolResult.
func executeTool(ctx context.Context, tools *tool.Registry, call schema.ToolCall) schema.ToolResult {
    fail := func(err error) schema.ToolResult {
        return schema.ToolResult{CallID: call.ID, IsError: true,
            Content: []schema.ContentPart{schema.TextPart{Text: err.Error()}}}
    }
    t, err := tools.Get(call.Name)
    if err != nil {
        return fail(err)
    }
    var args map[string]any
    if err := json.Unmarshal([]byte(call.Arguments), &args); err != nil {
        return fail(fmt.Errorf("invalid arguments: %w", err))
    }
    res, err := t.Execute(ctx, args)
    if err != nil {
        return fail(err)
    }
    return schema.ToolResult{CallID: call.ID, Content: res.Content, IsError: res.IsError}
}

type BookingInput struct {
    Type   string `json:"type" enum:"restaurant,spa,activity"`
    Date   string `json:"date" description:"Reservation date (YYYY-MM-DD)"`
    Time   string `json:"time" description:"Reservation time (HH:MM)"`
    Guests int    `json:"guests"`
    Name   string `json:"name" description:"Guest name"`
}

type InfoInput struct {
    Topic string `json:"topic" description:"Topic to look up (pool hours, restaurant menu, etc.)"`
}

func main() {}
```

## Use Case 2: Meeting Transcription

A live meeting minutes generator that transcribes audio in real time, identifies speakers, and generates structured summaries. This use case chooses STT over S2S because the output is text (transcript and minutes), not audio — there is no need for speech synthesis on the output side.

```go
import (
    "context"
    "fmt"
    "iter"
    "os"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/schema"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
)

func transcribeMeeting(ctx context.Context, audioStream iter.Seq2[[]byte, error]) error {
    engine, err := stt.New("deepgram", stt.Config{
        SampleRate: 16000,
        Encoding:   "linear16",
        Extra:      map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
    })
    if err != nil {
        return fmt.Errorf("create stt engine: %w", err)
    }

    // Stream transcription with speaker diarization
    transcripts := engine.TranscribeStream(ctx, audioStream,
        stt.WithLanguage("en"),
        stt.WithPunctuation(true),
        stt.WithDiarization(true),
    )

    var fullTranscript strings.Builder
    for event, err := range transcripts {
        if err != nil {
            return fmt.Errorf("transcription error: %w", err)
        }

        if event.IsFinal {
            fullTranscript.WriteString(event.Text + "\n")
            // Real-time display
            fmt.Printf("[%s] %s\n", event.Timestamp, event.Text)
        }
    }

    // Generate meeting minutes from transcript
    minutes, err := generateMinutes(ctx, fullTranscript.String())
    if err != nil {
        return fmt.Errorf("generate minutes: %w", err)
    }

    fmt.Println(minutes)
    return nil
}

func generateMinutes(ctx context.Context, transcript string) (string, error) {
    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return "", err
    }

    msgs := []schema.Message{
        schema.NewSystemMessage("Generate structured meeting minutes from this transcript. " +
            "Include: attendees, key discussion points, decisions made, and action items."),
        schema.NewHumanMessage(transcript),
    }

    resp, err := model.Generate(ctx, msgs)
    if err != nil {
        return "", err
    }

    return resp.Text(), nil
}
```

## Use Case 3: Voice Forms

Collect structured data through natural voice conversations. The form orchestrator manages state across turns, validates answers, and supports corrections. This use case separates STT and TTS (rather than using S2S) because the form logic needs to inspect and validate the transcribed text between speech input and speech output — a step that requires text as an intermediate representation.

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"

    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

type FormField struct {
    Name       string
    Prompt     string
    Validate   func(string) error
    Required   bool
}

type VoiceForm struct {
    fields  []FormField
    current int
    answers map[string]string
    stt     stt.STT
    tts     tts.TTS
}

func (f *VoiceForm) Run(ctx context.Context, audioIn iter.Seq2[[]byte, error]) (map[string]string, error) {
    // Ask the first question
    question := f.fields[f.current].Prompt
    audio, err := f.tts.Synthesize(ctx, question,
        tts.WithVoice("aria"),
        tts.WithSpeed(1.0),
    )
    if err != nil {
        return nil, fmt.Errorf("synthesize: %w", err)
    }
    sendAudio(audio)

    // Process answers
    transcripts := f.stt.TranscribeStream(ctx, audioIn,
        stt.WithLanguage("en"),
        stt.WithPunctuation(true),
    )

    for event, err := range transcripts {
        if err != nil {
            return nil, fmt.Errorf("transcribe: %w", err)
        }

        if !event.IsFinal {
            continue
        }

        field := f.fields[f.current]

        // Validate the answer
        if err := field.Validate(event.Text); err != nil {
            reprompt := fmt.Sprintf("I didn't quite get that. %s", field.Prompt)
            audio, err := f.tts.Synthesize(ctx, reprompt, tts.WithVoice("aria"))
            if err != nil {
                return nil, fmt.Errorf("synthesize reprompt: %w", err)
            }
            sendAudio(audio)
            continue
        }

        // Save and advance
        f.answers[field.Name] = event.Text
        f.current++

        if f.current >= len(f.fields) {
            // Form complete
            confirm := "Thank you. I have all the information I need."
            audio, err := f.tts.Synthesize(ctx, confirm, tts.WithVoice("aria"))
            if err != nil {
                return nil, fmt.Errorf("synthesize confirm: %w", err)
            }
            sendAudio(audio)
            return f.answers, nil
        }

        // Ask next question
        next := f.fields[f.current].Prompt
        audio, err := f.tts.Synthesize(ctx, next, tts.WithVoice("aria"))
        if err != nil {
            return nil, fmt.Errorf("synthesize next: %w", err)
        }
        sendAudio(audio)
    }

    return f.answers, nil
}
```

## Use Case 4: Interactive Audiobooks

Dynamic narration with character voices and branching storylines. This is a TTS-only use case — the story text is pre-authored and the system synthesizes it with character-appropriate voices. STT is not needed because user choices come from the UI, not from speech.

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice/tts"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/elevenlabs"
)

type Character struct {
    Name  string
    Voice string // TTS voice ID
    Pitch float64
}

func narrateScene(ctx context.Context, engine tts.TTS, scene Scene) error {
    for _, line := range scene.Lines {
        char := scene.Characters[line.Speaker]

        audio, err := engine.Synthesize(ctx, line.Text,
            tts.WithVoice(char.Voice),
            tts.WithPitch(char.Pitch),
            tts.WithSpeed(0.95), // Slightly slower for narration
        )
        if err != nil {
            return fmt.Errorf("synthesize line: %w", err)
        }

        sendAudio(audio)
    }
    return nil
}
```

## Building a Full Voice Pipeline

Compose the stages into a complete cascading pipeline. `voice.NewPipeline` reads audio from the transport, runs VAD (passed with `voice.WithVAD`, because it is an `ActivityDetector` rather than a frame processor), then STT, your agent stage, and TTS, and writes the result back to the transport. Adding or removing a stage is a one-line change.

```go
import (
    "github.com/lookatitude/beluga-ai/v2/voice"
    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"
    _ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

// agentStage is your LLM or agent as a voice.FrameProcessor, e.g. a
// voice.FrameLoop that calls model.Generate on each text frame.
func buildVoicePipeline(conn voice.Transport, sttEngine stt.STT, ttsEngine tts.TTS, agentStage voice.FrameProcessor) (*voice.VoicePipeline, error) {
    // VAD detects speech vs silence
    vad, err := voice.NewVAD("silero", map[string]any{"threshold": 0.5, "sample_rate": 16000})
    if err != nil {
        return nil, err
    }

    return voice.NewPipeline(
        voice.WithTransport(conn),
        voice.WithVAD(vad),
        voice.WithSTT(stt.AsFrameProcessor(sttEngine,
            stt.WithLanguage("en"),
            stt.WithPunctuation(true),
        )),
        voice.WithLLM(agentStage),
        voice.WithTTS(tts.AsFrameProcessor(ttsEngine, 16000)),
    ), nil
}
```

Run it with `pipe.Run(ctx)`, which blocks until the context is cancelled or the transport fails.

## Production Considerations

### Latency

Voice applications are latency-sensitive. Target end-to-end latency under 500ms for real-time conversations:

- Use S2S providers (OpenAI Realtime) for the lowest latency
- Pre-buffer audio frames to reduce jitter
- Deploy close to your users (edge compute or regional deployment)
- Use the WebSocket transport (`transport.NewWebSocketTransport`) for persistent, low-overhead connections. The LiveKit, Daily, and Pipecat transports are placeholders that do not connect yet

### Observability

Track voice-specific metrics:

```go
span.SetAttributes(
    attribute.Float64("voice.stt_latency_ms", sttLatency),
    attribute.Float64("voice.tts_latency_ms", ttsLatency),
    attribute.Float64("voice.e2e_latency_ms", endToEndLatency),
    attribute.String("voice.stt_provider", "deepgram"),
    attribute.String("voice.tts_provider", "elevenlabs"),
)
```

### Resilience

- Use Beluga AI's `resilience` package (retries, circuit breakers) around STT/TTS calls for provider failover
- Buffer audio during brief network interruptions
- Implement graceful degradation: fall back to text-only mode if voice fails
- Monitor provider health and switch providers dynamically

### Scaling

- Voice sessions are stateful — use sticky sessions or session affinity at the load balancer
- Scale STT/TTS independently based on demand
- Use connection pooling for WebSocket transports
- For meeting transcription, process audio in parallel tracks (one per speaker)

## Related Resources

- [Voice AI Pipeline](/docs/guides/voice-ai/) for detailed voice configuration
- [Conversational AI Assistant](/docs/guides/conversational-ai/) for adding memory to voice agents
- [Production Agent Platform](/docs/guides/production-platform/) for deployment patterns
