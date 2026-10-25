---
title: Automated Outbound Calling
description: "Automate outbound calls for appointment reminders, consent verification, and surveys. Scale from 200 to 2,000+ calls per day."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "automated outbound calling, voice automation, appointment reminders, survey calls, Beluga AI, Go, telephony AI use case"
---

Sales and operations teams often need to make thousands of outbound calls daily for appointment reminders, consent verification, and simple surveys. Manual calling is expensive ($15-25 per agent-hour), inconsistent (agents deviate from scripts and forget follow-ups), and lacks a reliable audit trail for compliance-sensitive outcomes like consent confirmations. The economics break down at scale: a team of 10 agents can handle roughly 200 calls per day, but demand often exceeds 2,000.

This use case demonstrates automating outbound calls using Beluga AI's voice pipeline with STT/TTS for scripted interactions. STT and TTS are used as separate components (rather than S2S) because the call flow is scripted with explicit branching logic — the system needs to inspect the transcribed text to decide which script branch to follow next.

## Solution Architecture

```mermaid
graph TB
    Scheduler[Job Scheduler] --> Worker[Outbound Worker]
    Worker --> CRM[CRM]
    Worker --> Pipeline[Voice Pipeline]
    Pipeline --> STT[STT]
    Pipeline --> TTS[TTS]
    Pipeline --> Tel[Telephony]
    Tel --> Contact[Contact]
    Worker --> Disposition[Disposition Store]
```

A job scheduler triggers outbound sessions per contact. Each worker creates a voice pipeline that handles the call through STT/TTS, executing the appropriate script (reminder, consent, or survey). On call completion or timeout, the worker records the disposition.

The worker-based architecture separates scheduling from call execution, allowing independent scaling. Workers are stateless except for the active call, which means they can be horizontally scaled to match call volume without coordination overhead.

## Implementation

### Outbound Call Session

The caller wraps STT and TTS engines and exposes per-script methods (e.g., `ExecuteReminder`). Each method follows a synthesize-listen-branch pattern: play the prompt via TTS, listen for a response via streaming STT, and branch based on the transcribed text. The `iter.Seq2[[]byte, error]` audio input and the `io.Writer` audio output let the caller work with any audio path — WebSocket, telephony media stream, or test fixture.

```go
package main

import (
    "context"
    "fmt"
    "io"
    "iter"
    "log"
    "os"
    "strings"
    "time"

    "github.com/lookatitude/beluga-ai/v2/voice/stt"
    "github.com/lookatitude/beluga-ai/v2/voice/telephony"
    "github.com/lookatitude/beluga-ai/v2/voice/tts"

    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/deepgram"
    _ "github.com/lookatitude/beluga-ai/v2/voice/tts/providers/cartesia"
)

// OutboundCaller manages automated outbound calls.
type OutboundCaller struct {
    sttEngine stt.STT
    ttsEngine tts.TTS
    voice     string
}

func NewOutboundCaller() (*OutboundCaller, error) {
    sttEngine, err := stt.New("deepgram", stt.Config{
        Model: "nova-2",
        Extra: map[string]any{"api_key": os.Getenv("DEEPGRAM_API_KEY")},
    })
    if err != nil {
        return nil, fmt.Errorf("create stt engine: %w", err)
    }

    // Cartesia returns raw 16-bit PCM, which is easy to re-encode for telephony.
    ttsEngine, err := tts.New("cartesia", tts.Config{
        SampleRate: 8000,
        Extra:      map[string]any{"api_key": os.Getenv("CARTESIA_API_KEY")},
    })
    if err != nil {
        return nil, fmt.Errorf("create tts engine: %w", err)
    }

    return &OutboundCaller{
        sttEngine: sttEngine,
        ttsEngine: ttsEngine,
        voice:     os.Getenv("CARTESIA_VOICE_ID"),
    }, nil
}

// ExecuteReminder plays the reminder to audioOut and listens on audioIn.
func (c *OutboundCaller) ExecuteReminder(ctx context.Context, contact Contact, audioIn iter.Seq2[[]byte, error], audioOut io.Writer) (Disposition, error) {
    // Play reminder prompt
    audio, err := c.ttsEngine.Synthesize(ctx,
        fmt.Sprintf("Hello %s, this is a reminder about your appointment on %s at %s. "+
            "Please say confirm or reschedule.", contact.Name, contact.Date, contact.Time),
        tts.WithVoice(c.voice),
    )
    if err != nil {
        return DispositionFailed, fmt.Errorf("synthesize: %w", err)
    }
    if _, err := audioOut.Write(audio); err != nil {
        return DispositionFailed, fmt.Errorf("play prompt: %w", err)
    }

    // Listen for response
    transcripts := c.sttEngine.TranscribeStream(ctx, audioIn,
        stt.WithLanguage("en"),
        stt.WithPunctuation(true),
    )

    for event, err := range transcripts {
        if err != nil {
            return DispositionFailed, fmt.Errorf("transcribe: %w", err)
        }

        if !event.IsFinal {
            continue
        }

        if containsAny(event.Text, "confirm", "yes") {
            confirmAudio, err := c.ttsEngine.Synthesize(ctx,
                "Your appointment is confirmed. Goodbye.",
                tts.WithVoice(c.voice),
            )
            if err != nil {
                return DispositionFailed, fmt.Errorf("synthesize: %w", err)
            }
            if _, err := audioOut.Write(confirmAudio); err != nil {
                return DispositionFailed, fmt.Errorf("play confirmation: %w", err)
            }
            return DispositionConfirmed, nil
        }

        if containsAny(event.Text, "reschedule", "cancel") {
            return DispositionReschedule, nil
        }
    }

    return DispositionNoResponse, nil
}

func containsAny(text string, words ...string) bool {
    lower := strings.ToLower(text)
    for _, w := range words {
        if strings.Contains(lower, w) {
            return true
        }
    }
    return false
}
```

### Placing the Call

The `voice/telephony` package defines the provider interface for call control, with the standard registry (`telephony.Register`, `telephony.New`, `telephony.List`):

```go
type TelephonyProvider interface {
    PlaceCall(ctx context.Context, req CallRequest) (*Call, error)
    HangUp(ctx context.Context, callID string) error
}
```

Beluga does not ship a telephony provider. Implement `TelephonyProvider` for your carrier (Twilio, Telnyx, a SIP trunk) and register it; the carrier's media stream (for example a WebSocket carrying call audio) then becomes `audioIn` and `audioOut` for `ExecuteReminder`. A worker places the call like this:

```go
func callContact(ctx context.Context, tel telephony.TelephonyProvider, caller *OutboundCaller, contact Contact, phone string,
    media func(callID string) (iter.Seq2[[]byte, error], io.Writer, error)) (Disposition, error) {
    call, err := tel.PlaceCall(ctx, telephony.CallRequest{
        To:      phone,
        From:    os.Getenv("OUTBOUND_CALLER_ID"),
        Timeout: 30 * time.Second,
    })
    if err != nil {
        return DispositionFailed, fmt.Errorf("place call: %w", err)
    }
    defer func() {
        if err := tel.HangUp(context.WithoutCancel(ctx), call.ID); err != nil {
            log.Printf("hang up %s: %v", call.ID, err)
        }
    }()

    audioIn, audioOut, err := media(call.ID) // your carrier's media stream for this call
    if err != nil {
        return DispositionFailed, fmt.Errorf("open media: %w", err)
    }
    return caller.ExecuteReminder(ctx, contact, audioIn, audioOut)
}
```

### Disposition and Retries

```go
type Disposition string

const (
    DispositionConfirmed  Disposition = "confirmed"
    DispositionReschedule Disposition = "reschedule"
    DispositionNoResponse Disposition = "no_response"
    DispositionBusy       Disposition = "busy"
    DispositionFailed     Disposition = "failed"
)

type Contact struct {
    ID   string
    Name string
    Date string
    Time string
}
```

Write disposition immediately on call end. Use a retry policy for no-answer and busy dispositions (for example, retry twice with exponential backoff).

## Deployment Considerations

- **Concurrent sessions**: Limit concurrent outbound sessions to match telephony provider capacity
- **Worker scaling**: Scale outbound workers independently based on call volume
- **Compliance**: Log consent outcomes and optionally record calls for compliance
- **Do Not Call**: Integrate DNC list checks before initiating calls
- **Observability**: Instrument call outcomes, STT/TTS latency, and telephony events with OpenTelemetry

## Lessons Learned

- **Short, scripted flows**: Reminders and consent work better with narrow prompts and clear yes/no responses
- **Disposition immediately**: Write outcome as soon as the call ends to simplify retries and reporting
- **Start with one flow**: Begin with reminders; add consent and surveys once the pipeline is stable

## Related Resources

- [Voice-Enabled IVR](/docs/guides/voice-ivr/) for inbound voice routing
- [Voice Sessions Overview](/docs/guides/voice-sessions-overview/) for session management patterns
- [Voice AI Applications](/docs/guides/voice-applications/) for full voice pipeline architecture
