---
title: Fine-Tuning Whisper for Industry Terms
description: "Improve STT accuracy for specialized vocabulary in Go — add Whisper prompt guidance with a custom Beluga AI STT engine and correct domain terms after transcription."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, Whisper, STT, vocabulary, prompt, custom STT provider, transcription correction"
---

Standard speech-to-text models often misrecognize domain-specific terminology, because they are trained on general speech corpora that underrepresent technical vocabulary. This tutorial shows two ways to improve accuracy without retraining a model: biasing Whisper with a vocabulary prompt through a custom Beluga STT engine, and correcting known terms after transcription.

## What You Will Build

A vocabulary-aware STT setup that correctly transcribes technical terms such as "Kubernetes", "gRPC", and "Beluga AI", which standard models often get wrong.

## Prerequisites

- OpenAI API key (for Whisper)
- A list of industry-specific terms relevant to your domain

## The Problem: Vocabulary Mismatch

When a general model meets a domain term, it approximates the closest-sounding common words. The error propagates: if STT produces "Cooper Netties" instead of "Kubernetes", downstream processing cannot recover the intent.

| Spoken term | Typical misrecognition |
|-------------|------------------------|
| gRPC        | "Gee RPS"              |
| Beluga AI   | "Blue guy eye"         |
| Kubernetes  | "Cooper Netties"       |
| pgvector    | "PG Vector"            |

## Step 1: Baseline Transcription with Whisper

Beluga's `whisper` provider calls the OpenAI Audio Transcriptions API:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
	_ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/whisper"
)

func main() {
	ctx := context.Background()

	engine, err := stt.New("whisper", stt.Config{
		Model:    "whisper-1",
		Language: "en",
		Extra:    map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
	})
	if err != nil {
		log.Fatalf("create STT engine: %v", err)
	}

	audio, err := os.ReadFile("deploy-instructions.wav")
	if err != nil {
		log.Fatalf("read audio: %v", err)
	}

	transcript, err := engine.Transcribe(ctx, audio)
	if err != nil {
		log.Fatalf("transcribe: %v", err)
	}
	fmt.Println("Transcript:", transcript)
}
```

The built-in engine sends `model`, `language`, and the audio file. It does not forward Whisper's `prompt` parameter, and Beluga's `deepgram` engine does not forward Deepgram's `keywords` parameter either. To use either feature, implement your own engine, as in the next step.

## Step 2: A Vocabulary-Aware Whisper Engine

Whisper's `prompt` parameter is treated as prior transcript text, so including the exact spelling of your domain terms biases the model toward them. Any type that implements `stt.STT` can be used wherever Beluga expects an STT engine, including `stt.AsFrameProcessor` in a voice pipeline. This engine adds the prompt to each request:

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"iter"
	"mime/multipart"
	"net/http"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/voice/stt"
)

// VocabWhisper is an stt.STT that sends a vocabulary prompt to Whisper.
type VocabWhisper struct {
	APIKey string
	Model  string
	Terms  []string
	Client *http.Client
}

var _ stt.STT = (*VocabWhisper)(nil)

// Transcribe uploads a WAV buffer with a prompt built from Terms.
func (w *VocabWhisper) Transcribe(ctx context.Context, audio []byte, opts ...stt.Option) (string, error) {
	cfg := stt.ApplyOptions(opts...)

	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	model := w.Model
	if cfg.Model != "" {
		model = cfg.Model
	}
	fields := map[string]string{
		"model":  model,
		"prompt": "The transcript involves " + strings.Join(w.Terms, ", ") + ".",
	}
	if cfg.Language != "" {
		fields["language"] = cfg.Language
	}
	for k, v := range fields {
		if err := form.WriteField(k, v); err != nil {
			return "", fmt.Errorf("write field %s: %w", k, err)
		}
	}
	part, err := form.CreateFormFile("file", "audio.wav")
	if err != nil {
		return "", fmt.Errorf("create form file: %w", err)
	}
	if _, err := part.Write(audio); err != nil {
		return "", fmt.Errorf("write audio: %w", err)
	}
	if err := form.Close(); err != nil {
		return "", fmt.Errorf("close form: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		"https://api.openai.com/v1/audio/transcriptions", &body)
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+w.APIKey)
	req.Header.Set("Content-Type", form.FormDataContentType())

	client := w.Client
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		msg, readErr := io.ReadAll(resp.Body)
		if readErr != nil {
			return "", fmt.Errorf("whisper: status %d", resp.StatusCode)
		}
		return "", fmt.Errorf("whisper: status %d: %s", resp.StatusCode, msg)
	}

	var out struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}
	return out.Text, nil
}

// TranscribeStream transcribes each chunk independently, because the Whisper
// API has no streaming mode.
func (w *VocabWhisper) TranscribeStream(ctx context.Context, audio iter.Seq2[[]byte, error], opts ...stt.Option) iter.Seq2[stt.TranscriptEvent, error] {
	return func(yield func(stt.TranscriptEvent, error) bool) {
		for chunk, err := range audio {
			if err != nil {
				yield(stt.TranscriptEvent{}, err)
				return
			}
			text, err := w.Transcribe(ctx, chunk, opts...)
			if err != nil {
				yield(stt.TranscriptEvent{}, err)
				return
			}
			if !yield(stt.TranscriptEvent{Text: text, IsFinal: true}, nil) {
				return
			}
		}
	}
}

func init() {
	stt.Register("whisper-vocab", func(cfg stt.Config) (stt.STT, error) {
		key, _ := cfg.Extra["api_key"].(string)
		if key == "" {
			return nil, fmt.Errorf("whisper-vocab: api_key is required in Extra")
		}
		terms, _ := cfg.Extra["terms"].([]string)
		model := cfg.Model
		if model == "" {
			model = "whisper-1"
		}
		return &VocabWhisper{APIKey: key, Model: model, Terms: terms}, nil
	})
}

func main() {}
```

Create it through the registry like any built-in provider:

```go
	engine, err := stt.New("whisper-vocab", stt.Config{
		Language: "en",
		Extra: map[string]any{
			"api_key": os.Getenv("OPENAI_API_KEY"),
			"terms":   []string{"Kubernetes", "gRPC", "pgvector", "Beluga AI"},
		},
	})
	if err != nil {
		log.Fatalf("create STT engine: %v", err)
	}
```

The prompt should contain the exact spellings you expect. Keep it short: Whisper only considers the last part of a long prompt. For multi-domain applications, keep one term list per industry and create an engine per domain, or add a per-request term option.

The same pattern works for Deepgram keyword boosting: implement `stt.STT` and add the `keywords` query parameter (for example `Kubernetes:2`) to the request. Excessive boost values cause false positives, where the model forces the keyword even when the speaker said something else.

## Step 3: Deterministic Post-Processing

Some misrecognitions are stable: the same audio always yields "Cooper Netties". A replacement table fixes these cheaply and adds no latency:

```go
import (
	"regexp"
)

// corrections maps observed misrecognitions to the intended term.
var corrections = []struct {
	pattern *regexp.Regexp
	term    string
}{
	{regexp.MustCompile(`(?i)\bcooper\s+netties\b`), "Kubernetes"},
	{regexp.MustCompile(`(?i)\bgee\s+rp[cs]\b`), "gRPC"},
	{regexp.MustCompile(`(?i)\bpg\s+vector\b`), "pgvector"},
}

// FixKnownTerms replaces known misrecognitions in a transcript.
func FixKnownTerms(transcript string) string {
	for _, c := range corrections {
		transcript = c.pattern.ReplaceAllString(transcript, c.term)
	}
	return transcript
}
```

Build the table from real transcripts: log the STT output for a test set and add a pattern for each recurring error.

## Step 4: LLM-Based Correction

When the acoustic similarity is too high for the STT model to disambiguate, an LLM can use the semantic context and the vocabulary list to correct terms:

```go
import (
	"context"
	"fmt"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/llm"
	"github.com/lookatitude/beluga-ai/v2/schema"
)

// CorrectTranscript uses an LLM to fix misrecognized domain terms. On error it
// returns the raw transcript along with the error, so callers can still proceed.
func CorrectTranscript(ctx context.Context, model llm.ChatModel, raw string, terms []string) (string, error) {
	resp, err := model.Generate(ctx, []schema.Message{
		schema.NewSystemMessage("Fix the spelling of technical terms in the transcript. " +
			"Change nothing else. Reply with the corrected transcript only. " +
			"Known terms: " + strings.Join(terms, ", ")),
		schema.NewHumanMessage(raw),
	}, llm.WithTemperature(0))
	if err != nil {
		return raw, fmt.Errorf("correction failed: %w", err)
	}
	return strings.TrimSpace(resp.Text()), nil
}
```

This adds the latency of an LLM call, so use it only where accuracy matters most. In real-time voice applications, consider running the correction asynchronously: answer from the uncorrected transcript and use the corrected one for logs, analytics, or follow-up turns.

## Verification

1. Record a sentence with technical terms: "Deploy the gRPC service to Kubernetes using Beluga."
2. Transcribe it with the built-in `whisper` engine and note the errors.
3. Transcribe it with `whisper-vocab` and compare.
4. Run the remaining errors through `FixKnownTerms` and `CorrectTranscript`, and check that correct words are left unchanged.

## Next Steps

- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) -- Low-latency streaming transcription
- [Cloning Voices with ElevenLabs](/docs/guides/capabilities/voice/elevenlabs-cloning) -- High-fidelity text-to-speech
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Balance VAD sensitivity for your environment
