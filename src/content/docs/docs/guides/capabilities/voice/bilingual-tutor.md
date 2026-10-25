---
title: Bilingual AI Conversation Tutor
description: "Build an AI language tutor with real-time voice conversations and pronunciation feedback. Affordable practice at a fraction of tutor cost."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "AI language tutor, bilingual voice AI, pronunciation feedback, speech-to-speech learning, language practice, Beluga AI, Go, EdTech"
---

Language learning platforms need affordable, always-available practice partners. The core constraint is that language fluency requires extensive conversational practice — researchers estimate 600-2,200 hours depending on the target language — but human tutors cost $30-50/hour, have limited availability, and cannot provide instant pronunciation feedback. Most learners cannot afford or schedule enough practice hours to achieve fluency.

A speech-to-speech (S2S) AI tutor enables natural voice conversations in the target language at a fraction of the cost, with real-time corrections and adaptive difficulty. S2S is chosen over separate STT+TTS because language tutoring demands the lowest possible latency — conversational pauses longer than 2 seconds break the flow of natural dialogue practice, and S2S eliminates the text-as-intermediate-representation overhead.

## Solution Architecture

```mermaid
graph TB
    A[Student Voice] --> B[S2S Provider]
    B --> C[Pronunciation Analyzer]
    C --> D[Feedback Generator]
    D --> E[Conversation Manager]
    E --> F[Level Adapter]
    F --> G[Response Generator]
    G --> B
    B --> H[Student Audio]
    I[Student Profile] --> F
    J[Learning Progress] --> E
```

The tutor uses Beluga AI's S2S provider for real-time speech-to-speech conversion. Audio flows through pronunciation analysis, which feeds corrections back into the conversation. The level adapter adjusts difficulty based on the student's performance profile.

The architecture routes pronunciation analysis through a tool function rather than a separate pipeline stage. This design allows the S2S model itself to decide when pronunciation feedback is appropriate (mid-conversation, not after every word), producing more natural tutoring interactions than a system that rigidly checks every utterance.

## Implementation

### S2S Tutor Setup

The tutor session is created through Beluga AI's S2S registry (`s2s.New("openai", s2s.Config{...})`) and configured with functional options on `Start`. The pronunciation checking tool is registered as a tool definition that the S2S model can invoke when it detects potential pronunciation issues. The event loop ranges over `session.Recv(ctx)` and handles audio output, tool calls, and transcript events in one place; tool results go back with `SendToolResult`. Pronunciation scoring itself (`analyzePronunciation`) is your own logic or service; Beluga does not include a pronunciation analyzer.

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/lookatitude/beluga-ai/v2/schema"
	"github.com/lookatitude/beluga-ai/v2/tool"
	"github.com/lookatitude/beluga-ai/v2/voice/s2s"

	_ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
)

type PronunciationInput struct {
	Word     string `json:"word" description:"The word to check pronunciation for" required:"true"`
	Language string `json:"language" description:"The target language" required:"true"`
}

// analyzePronunciation is your pronunciation-scoring logic or service.
var analyzePronunciation func(ctx context.Context, word, language string) (string, error)

func startTutorSession(ctx context.Context, studentID, targetLanguage string, speaker io.Writer) error {
	engine, err := s2s.New("openai", s2s.Config{
		Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
	})
	if err != nil {
		return fmt.Errorf("create s2s engine: %w", err)
	}

	pronunciationTool := tool.NewFuncTool[PronunciationInput](
		"check_pronunciation",
		"Analyze the student's pronunciation and provide feedback",
		func(ctx context.Context, input PronunciationInput) (*tool.Result, error) {
			feedback, err := analyzePronunciation(ctx, input.Word, input.Language)
			if err != nil {
				return tool.ErrorResult(err), nil
			}
			return tool.TextResult(feedback), nil
		},
	)

	session, err := engine.Start(ctx,
		s2s.WithVoice("alloy"),
		s2s.WithInstructions(fmt.Sprintf(
			"You are a patient, encouraging %s language tutor. "+
				"Conduct conversations at the student's level. "+
				"Gently correct grammar and pronunciation mistakes. "+
				"Use simple vocabulary and speak clearly.",
			targetLanguage,
		)),
		s2s.WithTools([]schema.ToolDefinition{
			tool.ToDefinition(pronunciationTool),
		}),
	)
	if err != nil {
		return fmt.Errorf("start session: %w", err)
	}
	defer session.Close()

	// Student audio is sent from your transport with session.SendAudio(ctx, pcm).
	for event, err := range session.Recv(ctx) {
		if err != nil {
			return fmt.Errorf("session: %w", err)
		}
		switch event.Type {
		case s2s.EventAudioOutput:
			if _, err := speaker.Write(event.Audio); err != nil {
				return fmt.Errorf("play audio: %w", err)
			}
		case s2s.EventToolCall:
			result := checkPronunciation(ctx, pronunciationTool, *event.ToolCall)
			if err := session.SendToolResult(ctx, result); err != nil {
				return fmt.Errorf("send tool result: %w", err)
			}
		case s2s.EventTranscript:
			trackProgress(ctx, studentID, event.Text)
		}
	}
	return nil
}

// checkPronunciation runs the tool for a model tool call and wraps the result.
func checkPronunciation(ctx context.Context, t tool.Tool, call schema.ToolCall) schema.ToolResult {
	var input map[string]any
	if err := json.Unmarshal([]byte(call.Arguments), &input); err != nil {
		return schema.ToolResult{CallID: call.ID, IsError: true,
			Content: []schema.ContentPart{schema.TextPart{Text: "invalid arguments: " + err.Error()}}}
	}
	res, err := t.Execute(ctx, input)
	if err != nil {
		return schema.ToolResult{CallID: call.ID, IsError: true,
			Content: []schema.ContentPart{schema.TextPart{Text: err.Error()}}}
	}
	return schema.ToolResult{CallID: call.ID, Content: res.Content, IsError: res.IsError}
}
```

### Adaptive Difficulty

The tutor tracks student performance and adapts conversation difficulty:

```go
type StudentProfile struct {
    Level           string // beginner, intermediate, advanced
    TargetLanguage  string
    VocabularySize  int
    AccuracyRate    float64
}

func trackProgress(ctx context.Context, studentID string, transcript string) {
    // Analyze transcript for vocabulary usage, grammar accuracy
    // Update student profile and adapt difficulty for next turn
}
```

## Deployment Considerations

- **Low latency**: S2S providers (OpenAI Realtime) provide the lowest end-to-end latency for natural conversations
- **Concurrent students**: Scale session infrastructure to handle peak concurrent users
- **Progress persistence**: Store student profiles and learning progress for session continuity
- **Multi-language**: Configure S2S instructions and pronunciation models per target language
- **Observability**: Track lesson metrics (duration, corrections, vocabulary coverage) with OpenTelemetry

## Lessons Learned

- **S2S for natural conversations**: Speech-to-speech provides the most natural interaction for language learning
- **Adaptive difficulty early**: Fixed difficulty had lower engagement; implement adaptation from the start
- **Pronunciation analysis**: Real-time feedback is the primary differentiator from static learning tools

## Related Resources

- [Hotel Concierge](/docs/guides/capabilities/voice/hotel-concierge/) for S2S voice conversation patterns
- [Voice AI Applications](/docs/guides/capabilities/voice/voice-applications/) for voice pipeline architecture
- [Voice Sessions Overview](/docs/guides/capabilities/voice/voice-sessions-overview/) for session management
