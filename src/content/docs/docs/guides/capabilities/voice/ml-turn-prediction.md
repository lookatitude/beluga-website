---
title: ML-Based Turn Prediction
description: "Predict turn ends in Go voice applications with a model instead of fixed rules — an LLM-based end-of-turn classifier, or your own ONNX model, wired into a Beluga AI voice pipeline."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, turn prediction, end of turn detection, semantic endpointing, voice AI, ONNX, LLM classifier"
---

Model-based turn prediction decides when a user has finished speaking using a trained model instead of fixed rules. Heuristics rely on silence duration and punctuation. Those signals are cheap to compute but miss conversational nuance: "I'd like to book a flight to..." followed by a pause is clearly unfinished, even though the user is silent. Models can use the content of the utterance (semantic endpointing) and, for audio models, prosodic cues such as trailing intonation.

Beluga does not ship a turn-detection model or an ONNX runtime. This tutorial shows how to plug one in behind a small interface, with two implementations: an LLM-based classifier built on Beluga's `llm` package, and an adapter for your own model, such as an ONNX model served by an inference service.

## What You Will Build

A `TurnPredictor` interface, an LLM-backed implementation, and a voice pipeline stage that asks the predictor whether an utterance is complete before forwarding it to the agent.

## Prerequisites

- Go 1.26 or later
- An LLM provider for `llm.New` (a small, fast model is best), or your own turn-detection model
- [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary) is recommended background; this page reuses its pipeline structure

## When to Use Model-Based Detection

Model-based detection is worth its cost when:

- Users speak naturally, with pauses, filler words, and trailing speech
- Heuristic rules produce too many premature or late turn ends
- You need to tell intentional pauses from end-of-turn silence

For structured speech (commands, short queries), the heuristic rules in [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary) are usually enough, with no extra latency or cost.

## Step 1: Define the Predictor Interface

Keep the model behind a one-method interface so you can swap implementations (LLM, ONNX, a vendor API) and test the pipeline with a fake:

```go
package turn

import "context"

// TurnPredictor estimates the probability that the user has finished their turn.
type TurnPredictor interface {
	// EndOfTurn returns a probability in [0, 1] for the transcript so far.
	EndOfTurn(ctx context.Context, transcript string) (float64, error)
}
```

## Step 2: An LLM-Based Predictor

A chat model can classify whether a transcript is a complete thought. Ask for a single number and parse it. Use a small model and a low temperature: this call sits on the latency-critical path.

```go
import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/llm"
	"github.com/lookatitude/beluga-ai/v2/schema"
)

// LLMTurnPredictor asks a chat model whether a transcript is a complete turn.
type LLMTurnPredictor struct {
	Model llm.ChatModel
}

var _ TurnPredictor = (*LLMTurnPredictor)(nil)

const turnPrompt = `You decide whether a voice-assistant user has finished speaking.
Reply with only a number between 0 and 1: the probability that the user's
utterance is a complete request or thought and they expect a reply now.
Trailing conjunctions, prepositions, or "um" mean the user is not done.`

func (p *LLMTurnPredictor) EndOfTurn(ctx context.Context, transcript string) (float64, error) {
	resp, err := p.Model.Generate(ctx, []schema.Message{
		schema.NewSystemMessage(turnPrompt),
		schema.NewHumanMessage(transcript),
	}, llm.WithTemperature(0), llm.WithMaxTokens(5))
	if err != nil {
		return 0, fmt.Errorf("turn prediction: %w", err)
	}
	prob, err := strconv.ParseFloat(strings.TrimSpace(resp.Text()), 64)
	if err != nil {
		return 0, fmt.Errorf("turn prediction: unexpected reply %q: %w", resp.Text(), err)
	}
	return min(max(prob, 0), 1), nil
}
```

Create the model as usual, for example `llm.New("openai", config.ProviderConfig{APIKey: os.Getenv("OPENAI_API_KEY"), Model: "gpt-4o-mini"})`.

## Step 3: An Adapter for Your Own Model

Dedicated turn-detection models, often exported to ONNX, are faster and cheaper than an LLM call. Beluga has no ONNX runtime, so the simplest integration is to serve the model from an inference service and call it over HTTP. The request and response shapes below are an example; match them to your service:

```go
import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
)

// HTTPTurnPredictor calls a model-serving endpoint that returns {"probability": 0.87}.
type HTTPTurnPredictor struct {
	URL    string
	Client *http.Client
}

var _ TurnPredictor = (*HTTPTurnPredictor)(nil)

func (p *HTTPTurnPredictor) EndOfTurn(ctx context.Context, transcript string) (float64, error) {
	body, err := json.Marshal(map[string]string{"text": transcript})
	if err != nil {
		return 0, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.URL, bytes.NewReader(body))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.Client.Do(req)
	if err != nil {
		return 0, fmt.Errorf("turn model: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("turn model: status %d", resp.StatusCode)
	}

	var out struct {
		Probability float64 `json:"probability"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return 0, fmt.Errorf("turn model: decode: %w", err)
	}
	return out.Probability, nil
}
```

Set a short `Client.Timeout` (for example 150 ms) so a slow model never stalls the conversation. When choosing a model, consider:

| Factor       | Guidance                                                    |
|--------------|-------------------------------------------------------------|
| Input        | Text-only models need a transcript; audio models need PCM at the model's sample rate |
| Latency      | Target well under 100 ms per prediction, including the network hop |
| Accuracy     | Evaluate on transcripts from your own domain                |
| Language     | Multilingual models vs. language-specific models            |

## Step 4: Gate Turns in the Pipeline

The pipeline stage works like the `turnStage` in [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary#step-3-buffer-transcripts-until-the-turn-is-complete). It buffers transcript text and, on each `voice.SignalEndOfUtterance` from the VAD, asks the predictor whether the turn is complete. If the predictor fails, it falls back to ending the turn, so an outage costs accuracy, not availability:

```go
import (
	"context"
	"log"
	"strings"

	"github.com/lookatitude/beluga-ai/v2/voice"
)

// predictedTurnStage forwards one text frame per turn, as judged by p.
func predictedTurnStage(p TurnPredictor, threshold float64) voice.FrameProcessor {
	var buf strings.Builder

	return voice.FrameLoop(func(ctx context.Context, f voice.Frame) ([]voice.Frame, error) {
		switch {
		case f.Type == voice.FrameText:
			if buf.Len() > 0 {
				buf.WriteByte(' ')
			}
			buf.WriteString(f.Text())
			return nil, nil
		case f.Signal() == voice.SignalEndOfUtterance:
			text := strings.TrimSpace(buf.String())
			if text == "" {
				return nil, nil
			}
			prob, err := p.EndOfTurn(ctx, text)
			if err != nil {
				log.Printf("turn predictor failed, ending turn: %v", err)
				prob = 1
			}
			if prob < threshold {
				return nil, nil // the user is probably not done; keep listening
			}
			buf.Reset()
			return []voice.Frame{voice.NewTextFrame(text), f}, nil
		default:
			return []voice.Frame{f}, nil
		}
	})
}
```

Wire it after STT, as in the sentence-boundary guide: `voice.WithSTT(voice.Chain(stt.AsFrameProcessor(engine), predictedTurnStage(predictor, 0.5)))`. Keep a short VAD silence (300 ms or so) so the predictor is consulted quickly; the model, not a long silence window, now prevents premature replies.

One limitation of this design: if the predictor says "not done" and the user then stays silent, nothing triggers a new check until more speech arrives. Add a maximum wait in your application, for example a timer that forwards the buffered transcript after 1.5 s of silence.

## Step 5: Threshold Tuning

The threshold sets how confident the predictor must be before the agent replies:

- **Lower (0.3-0.4)**: replies sooner, but may cut in on mid-sentence pauses. Suits fast-paced service bots handling simple queries.
- **Default (0.5)**: balanced for general conversation.
- **Higher (0.6-0.8)**: waits for clear turn ends. Suits tutoring or coaching, where premature replies are disruptive.

## Verification

1. Unit-test `predictedTurnStage` with a fake `TurnPredictor` that returns fixed probabilities.
2. Run the LLM predictor on a set of complete ("Book a flight to Lisbon.") and incomplete ("Book a flight to") transcripts and check the probabilities separate cleanly.
3. Measure predictor latency at p50 and p95; it adds directly to response time.
4. Compare premature and late turn ends against the heuristic rules on recorded conversations.

## Next Steps

- [Sentence-Boundary Turn Detection](/docs/guides/capabilities/voice/sentence-boundary) -- Heuristic alternative for simpler use cases
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Combine turn detection with VAD tuning
- [Custom Silero VAD](/docs/guides/capabilities/voice/custom-silero-vad) -- Configure voice activity detection
