---
title: Integrating with LiveKit and Vapi
description: "Connect a Beluga AI voice agent to WebRTC platforms like LiveKit and Vapi in Go — what works today, a WebSocket bridge pattern, and using Beluga as a custom LLM."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, LiveKit, Vapi, WebRTC, voice platform, WebSocket transport, custom LLM"
---

Production voice applications need infrastructure for WebRTC networking, STUN/TURN servers, jitter buffering, and room management. Building it from scratch is a multi-month effort that is tangential to your voice agent. Platforms like LiveKit and Vapi provide this infrastructure, so Beluga AI can focus on the intelligence layer: STT, LLM reasoning, TTS, and conversation management. This tutorial explains what Beluga supports today and shows two integration patterns that work now.

## Current Status

- Beluga does not have a voice "backend" package that manages rooms or sessions on these platforms.
- The `voice/transport/providers/livekit` package (registered as `"livekit"`) is a placeholder that does not connect to LiveKit: `transport.New("livekit", ...)` always returns an error wrapping `transport.ErrNotImplemented`. The `daily` and `pipecat` providers behave the same way.
- There is no Vapi provider.
- The working transport today is `transport.NewWebSocketTransport`, a WebSocket client that sends audio as binary messages and other frames as JSON.

## What You Will Build

1. A Beluga voice pipeline that connects over WebSocket to a media bridge, which relays audio to and from a LiveKit room.
2. A response handler that lets a hosted voice platform such as Vapi use Beluga as its LLM.

## Prerequisites

- A working STT/TTS configuration (see [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming))
- For LiveKit: a LiveKit server and a bridge process that forwards a participant's audio over WebSocket (built with LiveKit's server SDKs)
- For Vapi: a Vapi account and assistant

## Why Third-Party Platforms?

Beluga provides STT, TTS, and S2S capabilities, but production voice applications need infrastructure outside the scope of an AI framework:

- **WebRTC networking**: STUN/TURN servers, ICE candidates, and jitter buffers handle NAT traversal, firewalls, and packet reordering for real-time audio over the internet.
- **Room management**: multiple participants, track subscriptions, and media routing need a dedicated media server.
- **Global edge networks**: edge servers reduce the round-trip time between the user and the nearest processing node.
- **Recording and monitoring**: session recording, quality metrics, and debugging tools for diagnosing audio quality in production.

## Pattern 1: LiveKit Through a WebSocket Bridge

Until the LiveKit transport is functional, run a small bridge next to your LiveKit server. The bridge joins the room as a participant using LiveKit's server SDK, forwards the user's audio track as 16 kHz, 16-bit PCM binary WebSocket messages, and publishes binary messages it receives back into the room as the agent's audio track. Beluga connects to the bridge as a WebSocket client:

```go
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/transport"
	_ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

// runAgent connects to the bridge and runs a cascading pipeline over it.
// sttStage, llmStage, and ttsStage are voice.FrameProcessor values, for example
// stt.AsFrameProcessor(engine) and tts.AsFrameProcessor(engine, 16000).
func runAgent(ctx context.Context, sttStage, llmStage, ttsStage voice.FrameProcessor) error {
	ws, err := transport.NewWebSocketTransport(ctx, os.Getenv("BRIDGE_WS_URL"),
		transport.WithWSSampleRate(16000),
		transport.WithWSHeaders(http.Header{
			"Authorization": {"Bearer " + os.Getenv("BRIDGE_TOKEN")},
		}),
	)
	if err != nil {
		return err
	}
	defer ws.Close()

	vad, err := voice.NewVAD("silero", map[string]any{"threshold": 0.5, "sample_rate": 16000})
	if err != nil {
		return err
	}

	pipe := voice.NewPipeline(
		voice.WithTransport(ws),
		voice.WithVAD(vad),
		voice.WithSTT(sttStage),
		voice.WithLLM(llmStage),
		voice.WithTTS(ttsStage),
	)
	return pipe.Run(ctx)
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// Build your STT, LLM, and TTS stages here; see the Voice AI Pipeline Guide.
	var sttStage, llmStage, ttsStage voice.FrameProcessor
	if sttStage == nil || llmStage == nil || ttsStage == nil {
		log.Fatal("configure the STT, LLM, and TTS stages first")
	}

	if err := runAgent(ctx, sttStage, llmStage, ttsStage); err != nil && ctx.Err() == nil {
		log.Fatal(err)
	}
}
```

Run one agent connection per participant or room, depending on how your bridge maps audio streams. The bridge also must use an audio format the TTS stage can produce: the `cartesia` TTS provider returns raw PCM, while `elevenlabs` returns MP3, which the bridge would need to decode.

[Voice AI Pipeline Guide](/docs/guides/capabilities/voice/voice-ai) shows a complete pipeline, including an LLM stage built with `voice.FrameLoop`.

## Pattern 2: Beluga as the LLM Behind a Hosted Voice Platform

Platforms such as Vapi can run the whole telephony, STT, and TTS loop themselves and call out to a URL you host for each response (Vapi calls this a custom LLM). In this model, Beluga provides only the reasoning. It's a good fit when you want phone (PSTN, SIP) support without operating telephony infrastructure.

The exact request and response format, including whether responses must be streamed, is defined by the platform; check its documentation. The core of the handler converts the conversation into Beluga messages and generates a reply:

```go
import (
	"context"

	"github.com/lookatitude/beluga-ai/v2/llm"
	"github.com/lookatitude/beluga-ai/v2/schema"
)

// ChatMessage is one message in an OpenAI-style chat request body.
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// reply converts platform messages to Beluga messages and generates a response.
func reply(ctx context.Context, model llm.ChatModel, msgs []ChatMessage) (string, error) {
	history := make([]schema.Message, 0, len(msgs))
	for _, m := range msgs {
		switch m.Role {
		case "system":
			history = append(history, schema.NewSystemMessage(m.Content))
		case "assistant":
			history = append(history, schema.NewAIMessage(m.Content))
		default:
			history = append(history, schema.NewHumanMessage(m.Content))
		}
	}
	resp, err := model.Generate(ctx, history)
	if err != nil {
		return "", err
	}
	return resp.Text(), nil
}
```

To stream the reply token by token, use `model.Stream(ctx, history)` and forward each chunk's `Delta` in the platform's streaming format. You can also put a full Beluga agent (`agent.New` with tools and memory) behind the same handler.

## Architecture

```
Pattern 1:  User ◀─WebRTC─▶ LiveKit ◀─▶ Bridge ◀─WebSocket─▶ Beluga pipeline (VAD → STT → LLM → TTS)

Pattern 2:  Caller ◀─PSTN/WebRTC─▶ Vapi (STT, TTS) ──HTTP──▶ Beluga reply handler (LLM / agent)
```

## Verification

1. Pattern 1: start the bridge and a LiveKit room, run the agent, join the room, and speak. Check that the agent's audio track plays in the room.
2. Pattern 1: stop the bridge and confirm the agent exits with a transport error rather than hanging.
3. Pattern 2: call your handler with a sample request body and check the reply; then point a Vapi assistant at it and place a test call.

## Next Steps

- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Optimize VAD for your environment
- [Scalable Voice Backend](/docs/guides/capabilities/voice/scalable-backend) -- Scale to many concurrent sessions
- [Real-time STT Streaming](/docs/guides/capabilities/voice/stt-realtime-streaming) -- Streaming transcription
