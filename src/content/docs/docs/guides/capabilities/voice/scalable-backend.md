---
title: Building a Scalable Voice Backend
description: "Deploy a production-ready voice backend in Go with concurrent session management, health monitoring, configurable STT/TTS pipelines, and graceful draining."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, voice backend, scalable, concurrent sessions, health checks, production"
---

Production voice applications must handle many concurrent sessions with predictable latency, graceful degradation, and operational visibility. A single voice agent serving one user at a time works for prototyping, but production deployments need session isolation, concurrency limits, health checks, and the ability to drain sessions during deployments.

Beluga provides the per-session building blocks: `voice.VoicePipeline` runs one conversation over a transport, and `voice.VoiceSession` tracks its state and turns. It does not include a multi-session backend or session manager. This tutorial builds one in application code: a small session manager with a concurrency limit, a session list, a health endpoint for the load balancer, and graceful draining.

## What You Will Build

A voice service that starts one pipeline per session on request, rejects sessions beyond a configured capacity, reports health and capacity over HTTP, and drains sessions on shutdown.

## Prerequisites

- Go 1.26 or later
- API keys for your chosen STT, LLM, and TTS providers
- A media source each session can connect to over WebSocket (a media bridge or telephony media stream; see [Integrating with LiveKit and Vapi](/docs/guides/capabilities/voice/livekit-vapi))

## Step 1: The Session Manager

The manager holds a semaphore of session slots. The limit protects the service from overload: each session holds audio buffers, a WebSocket connection, and provider connections for STT, TTS, or S2S. With a limit, the service rejects work it cannot serve with acceptable latency instead of degrading every session.

```go
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/transport"
)

// ErrAtCapacity is returned when the manager cannot accept another session.
var ErrAtCapacity = errors.New("voice backend at capacity")

// PipelineFactory builds the stages for one session. Stages such as VAD
// detectors keep per-stream state, so build fresh ones per session.
type PipelineFactory func(ctx context.Context, t voice.Transport, sess *voice.VoiceSession) (*voice.VoicePipeline, error)

// SessionManager runs one voice pipeline per session with a concurrency limit.
type SessionManager struct {
	build    PipelineFactory
	slots    chan struct{}
	timeout  time.Duration
	draining chan struct{}
	drainOne sync.Once

	mu       sync.Mutex
	sessions map[string]*managedSession
	wg       sync.WaitGroup
}

type managedSession struct {
	voice  *voice.VoiceSession
	cancel context.CancelFunc
}

// NewSessionManager allows at most maxSessions concurrent sessions, each
// limited to maxDuration.
func NewSessionManager(build PipelineFactory, maxSessions int, maxDuration time.Duration) *SessionManager {
	return &SessionManager{
		build:    build,
		slots:    make(chan struct{}, maxSessions),
		timeout:  maxDuration,
		draining: make(chan struct{}),
		sessions: make(map[string]*managedSession),
	}
}
```

The `PipelineFactory` is where you choose the pipeline for each session: a cascading `voice.NewPipeline` (STT, LLM, TTS), or a pipeline with an S2S processor. Use the cascade when you need text in the middle (logging, guardrails, a custom LLM or agent); use S2S when end-to-end latency matters most.

## Step 2: Start Sessions

`Start` takes a free slot or fails fast with `ErrAtCapacity`, connects the session's transport, builds its pipeline, and runs it in a goroutine. The session gets its own context with a maximum duration, detached from the HTTP request that started it.

```go
// Start dials the media URL for a new session and runs its pipeline in the
// background. It fails fast with ErrAtCapacity when no slot is free.
func (m *SessionManager) Start(ctx context.Context, id, mediaURL string) error {
	select {
	case <-m.draining:
		return errors.New("voice backend is draining")
	default:
	}
	select {
	case m.slots <- struct{}{}:
	default:
		return ErrAtCapacity
	}

	// The session outlives the request that started it.
	sessCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), m.timeout)
	release := func() {
		cancel()
		<-m.slots
	}

	ws, err := transport.NewWebSocketTransport(sessCtx, mediaURL)
	if err != nil {
		release()
		return fmt.Errorf("connect media: %w", err)
	}
	vs := voice.NewSession(id)
	pipe, err := m.build(sessCtx, ws, vs)
	if err != nil {
		release()
		if closeErr := ws.Close(); closeErr != nil {
			log.Printf("session %s: close transport: %v", id, closeErr)
		}
		return fmt.Errorf("build pipeline: %w", err)
	}

	m.mu.Lock()
	m.sessions[id] = &managedSession{voice: vs, cancel: cancel}
	m.mu.Unlock()

	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		defer release()
		defer func() {
			m.mu.Lock()
			delete(m.sessions, id)
			m.mu.Unlock()
			if err := ws.Close(); err != nil {
				log.Printf("session %s: close transport: %v", id, err)
			}
		}()
		if err := pipe.Run(sessCtx); err != nil && sessCtx.Err() == nil {
			log.Printf("session %s ended with error: %v", id, err)
		}
	}()
	return nil
}
```

## Step 3: Session Lifecycle, Capacity, and Health

Listing and closing sessions gives operators visibility (which sessions are active, in which state) and control. The health handler tells the load balancer whether this instance can take new sessions, so traffic shifts away from full or draining instances.

```go
// SessionInfo is the operational view of one session.
type SessionInfo struct {
	ID    string             `json:"id"`
	State voice.SessionState `json:"state"`
	Turns int                `json:"turns"`
}

// List returns the active sessions and their state.
func (m *SessionManager) List() []SessionInfo {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]SessionInfo, 0, len(m.sessions))
	for id, s := range m.sessions {
		out = append(out, SessionInfo{ID: id, State: s.voice.CurrentState(), Turns: s.voice.TurnCount()})
	}
	return out
}

// Close ends one session.
func (m *SessionManager) Close(id string) error {
	m.mu.Lock()
	s, ok := m.sessions[id]
	m.mu.Unlock()
	if !ok {
		return fmt.Errorf("session %s not found", id)
	}
	s.cancel()
	return nil
}

// Active returns the number of running sessions.
func (m *SessionManager) Active() int { return len(m.slots) }

// Drain stops accepting sessions and waits for running ones to finish or for
// ctx to expire, then cancels whatever is left.
func (m *SessionManager) Drain(ctx context.Context) {
	m.drainOne.Do(func() { close(m.draining) })
	done := make(chan struct{})
	go func() { m.wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-ctx.Done():
		m.mu.Lock()
		for _, s := range m.sessions {
			s.cancel()
		}
		m.mu.Unlock()
		<-done
	}
}

// HealthHandler reports readiness for a load balancer: 503 while draining or full.
func (m *SessionManager) HealthHandler(w http.ResponseWriter, _ *http.Request) {
	status := map[string]any{"active": m.Active(), "capacity": cap(m.slots)}
	code := http.StatusOK
	select {
	case <-m.draining:
		status["draining"] = true
		code = http.StatusServiceUnavailable
	default:
		if m.Active() >= cap(m.slots) {
			code = http.StatusServiceUnavailable
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if err := json.NewEncoder(w).Encode(status); err != nil {
		log.Printf("health: encode: %v", err)
	}
}
```

## Step 4: Wire It Up

The factory builds fresh stages per session: VAD detectors and turn-tracking stages keep per-stream state, so don't share them between sessions. On `SIGTERM`, the service stops accepting sessions, lets running calls finish for a grace period, then cancels the rest.

```go
import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/lookatitude/beluga-ai/v2/voice"
	_ "github.com/lookatitude/beluga-ai/v2/voice/vad/providers/silero"
)

func main() {
	build := func(ctx context.Context, t voice.Transport, sess *voice.VoiceSession) (*voice.VoicePipeline, error) {
		vad, err := voice.NewVAD("silero", map[string]any{"threshold": 0.5})
		if err != nil {
			return nil, err
		}
		stt, llm, tts, err := newStages(ctx) // your STT, LLM, and TTS FrameProcessors
		if err != nil {
			return nil, err
		}
		return voice.NewPipeline(
			voice.WithTransport(t),
			voice.WithVAD(vad),
			voice.WithSTT(stt),
			voice.WithLLM(llm),
			voice.WithTTS(tts),
			voice.WithSession(sess),
		), nil
	}

	mgr := NewSessionManager(build, 100, 30*time.Minute)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", mgr.HealthHandler)
	mux.HandleFunc("POST /sessions", func(w http.ResponseWriter, r *http.Request) {
		id, mediaURL := r.FormValue("id"), r.FormValue("media_url")
		if err := mgr.Start(r.Context(), id, mediaURL); err != nil {
			code := http.StatusBadGateway
			if errors.Is(err, ErrAtCapacity) {
				code = http.StatusServiceUnavailable
			}
			http.Error(w, err.Error(), code)
			return
		}
		w.WriteHeader(http.StatusAccepted)
	})

	srv := &http.Server{Addr: ":8080", Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatal(err)
		}
	}()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()

	// Stop taking sessions, give running calls up to 2 minutes to finish.
	drainCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	mgr.Drain(drainCtx)
	if err := srv.Shutdown(drainCtx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}
```

`newStages` is your function that creates the STT, LLM, and TTS processors for a session, for example `stt.AsFrameProcessor(engine)`, an LLM stage built with `voice.FrameLoop`, and `tts.AsFrameProcessor(engine, sampleRate)`. See [Voice AI Pipeline Guide](/docs/guides/capabilities/voice/voice-ai) for a complete example.

## Architecture

```
                    ┌──────────────────────────────┐
POST /sessions ───▶ │  SessionManager              │
GET  /healthz  ───▶ │   - slots (capacity limit)   │
                    │   - Start / List / Close     │
                    │   - Drain                    │
                    │         │                    │
                    │         ▼  one per session   │
                    │  voice.VoicePipeline         │
                    │   WebSocket transport        │
                    │   VAD → STT → LLM → TTS      │
                    └──────────────────────────────┘
```

## Scaling Out

- **Horizontal scaling**: run several instances behind a load balancer that uses `/healthz` for readiness. Each instance enforces its own limit.
- **Capacity sizing**: measure CPU, memory, and provider rate limits per session under load, then set the limit below the point where latency degrades.
- **Provider limits**: STT, TTS, and LLM providers have their own concurrency and rate limits; the instance limit times the instance count must stay within them.
- **Observability**: export active-session counts, rejections, and session durations as metrics, and log per-session errors with the session ID.

## Verification

1. Start the service and check that `GET /healthz` returns 200 with `active: 0`.
2. Start a session with `POST /sessions` and confirm `active` increments.
3. End the media connection and confirm the session disappears from `List` and `active` decrements.
4. Start sessions beyond the limit and confirm the extra requests get 503.
5. Send `SIGTERM` and confirm `/healthz` returns 503 while running sessions finish.

## Next Steps

- [LiveKit and Vapi Integration](/docs/guides/capabilities/voice/livekit-vapi) -- Connect sessions to WebRTC platforms
- [Native S2S with Amazon Nova](/docs/guides/capabilities/voice/s2s-amazon-nova) -- S2S session handling
- [Sensitivity Tuning](/docs/guides/capabilities/voice/sensitivity-tuning) -- Tune the VAD in your pipeline
