---
title: "Scaling Concurrent Voice Streams"
description: "Recipe for supporting 100+ concurrent voice sessions in Go with capacity management, health checks, backpressure, and graceful degradation."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, voice scaling, Go concurrent sessions, capacity management, backpressure, health checks, voice infrastructure recipe"
---

## Problem

You need to support many concurrent voice sessions (100+) on a single backend instance without exhausting resources, hitting provider limits, or degrading latency. You must enforce capacity limits, handle backpressure, and fail gracefully when at capacity. Voice sessions consume significant resources: WebRTC or WebSocket connections, TTS/STT API rate limits, memory for audio buffers, and goroutines for frame processing. Without explicit capacity management, a surge of incoming sessions can overwhelm the backend, causing cascading failures, degraded quality for all users, or provider-side throttling that affects unrelated workloads.

Traditional load balancers alone do not solve this problem because they do not understand voice session semantics. A session that successfully establishes a connection might still fail mid-stream if the backend becomes overloaded. You need application-level capacity checks and health monitoring that account for active sessions, not just connection counts.

## Solution

Beluga AI has no voice "backend" object with built-in session limits: each voice session is a `voice.VoicePipeline` (or `voice.HybridPipeline`) that you construct and `Run` yourself. That makes admission control an application concern, which is where it belongs. Wrap pipeline creation in a small session manager that holds a semaphore sized to your capacity, checks component health through an `o11y.HealthRegistry` before admitting a session, and records active sessions and rejections with OpenTelemetry metrics.

The reasoning behind this pattern is defense in depth. Capacity limits depend on deployment-specific factors (hardware, provider quotas, SLAs), so the limit is a parameter you choose. Health checks catch degraded dependencies before they accept new sessions, reducing wasted setup overhead and improving user experience through fast failure.

## Code Example

```go
package main

import (
	"context"
	"errors"
	"log"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"

	"github.com/lookatitude/beluga-ai/v2/o11y"
	"github.com/lookatitude/beluga-ai/v2/voice"
	"github.com/lookatitude/beluga-ai/v2/voice/s2s"
	_ "github.com/lookatitude/beluga-ai/v2/voice/s2s/providers/openai"
)

var (
	tracer = otel.Tracer("beluga.voice.scaling")
	meter  = otel.Meter("beluga.voice.scaling")
)

var ErrAtCapacity = errors.New("voice: at capacity")

// SessionManager admits at most cap(slots) concurrent voice sessions.
type SessionManager struct {
	slots    chan struct{}
	engine   s2s.S2S
	health   *o11y.HealthRegistry
	active   metric.Int64UpDownCounter
	rejected metric.Int64Counter
}

func NewSessionManager(maxSessions int, engine s2s.S2S, health *o11y.HealthRegistry) (*SessionManager, error) {
	active, err := meter.Int64UpDownCounter("voice.sessions.active")
	if err != nil {
		return nil, err
	}
	rejected, err := meter.Int64Counter("voice.sessions.rejected")
	if err != nil {
		return nil, err
	}
	return &SessionManager{
		slots:    make(chan struct{}, maxSessions),
		engine:   engine,
		health:   health,
		active:   active,
		rejected: rejected,
	}, nil
}

// Serve runs one session on transport, or returns ErrAtCapacity immediately.
func (m *SessionManager) Serve(ctx context.Context, sessionID string, transport voice.Transport) error {
	ctx, span := tracer.Start(ctx, "voice.session")
	defer span.End()
	span.SetAttributes(attribute.String("session_id", sessionID))

	select {
	case m.slots <- struct{}{}:
	default:
		m.rejected.Add(ctx, 1, metric.WithAttributes(attribute.String("reason", "capacity")))
		span.SetStatus(codes.Error, "at capacity")
		return ErrAtCapacity
	}
	defer func() { <-m.slots }()

	for _, r := range m.health.CheckAll(ctx) {
		if r.Status == o11y.Unhealthy {
			m.rejected.Add(ctx, 1, metric.WithAttributes(attribute.String("reason", "unhealthy")))
			err := errors.New("voice: dependency unhealthy: " + r.Component)
			span.RecordError(err)
			span.SetStatus(codes.Error, "unhealthy")
			return err
		}
	}

	m.active.Add(ctx, 1)
	defer m.active.Add(ctx, -1)
	span.SetAttributes(attribute.Int("active_sessions", len(m.slots)))

	pipe := voice.NewPipeline(
		voice.WithTransport(transport),
		voice.WithLLM(s2s.AsFrameProcessor(m.engine)),
		voice.WithSession(voice.NewSession(sessionID)),
	)
	if err := pipe.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return err
	}
	span.SetStatus(codes.Ok, "")
	return nil
}

func main() {
	engine, err := s2s.New("openai_realtime", s2s.Config{
		Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
	})
	if err != nil {
		log.Fatalf("s2s: %v", err)
	}

	health := o11y.NewHealthRegistry()
	health.Register("s2s", o11y.HealthCheckerFunc(func(ctx context.Context) o11y.HealthResult {
		return o11y.HealthResult{Status: o11y.Healthy} // probe your provider here
	}))

	mgr, err := NewSessionManager(100, engine, health)
	if err != nil {
		log.Fatalf("manager: %v", err)
	}
	log.Printf("accepting up to %d sessions", cap(mgr.slots))
	// For each incoming connection: go mgr.Serve(ctx, id, transport)
}
```

## Explanation

1. **Capacity check** -- The buffered channel is a semaphore: a send succeeds only while fewer than `maxSessions` sessions hold a slot, and the `default` branch rejects immediately instead of blocking. The check happens before any provider connection is opened, avoiding wasted work. The limit is tied to your resources (CPU, bandwidth, provider concurrency quotas), which only the operator knows.

2. **Health check** -- Checking an `o11y.HealthRegistry` before starting a session avoids admitting sessions while a dependency is down and reduces cascading failures. A dependency may be unhealthy due to upstream provider failures (TTS API down), internal errors, or resource exhaustion. Fast failure gives the user an immediate error rather than a session that fails mid-stream, and prevents snowballing, where new sessions consume resources attempting to start.

3. **Metrics** -- Record active sessions and rejections via OpenTelemetry. The UpDownCounter tracks session lifecycle: increment on admit, decrement on exit. It feeds autoscaling policies (scale up when approaching capacity), dashboards, and alerts. Tagging rejections with a `reason` distinguishes capacity-limited rejections (expected under load) from health-driven ones.

**Key insight:** Capacity management is your application's job. Bound concurrency explicitly at session admission, and fail fast with a clear error rather than silently degrading every session.

:::note
The `livekit`, `daily`, and `pipecat` transports under `voice/transport/providers` are not implemented: they do not connect to the service, and `transport.New` returns an error wrapping `transport.ErrNotImplemented` for each of them. Use `voice/transport.NewWebSocketTransport` or your own `voice.Transport` implementation for real traffic.
:::

## Variations

### Queue Instead of Reject

When at capacity, enqueue create requests and process when a session closes. Use a worker pool and a queue (channel or job queue).

### Per-Tenant Limits

Maintain per-tenant active counts and enforce a lower cap per tenant while keeping the global semaphore.

### Graceful Shutdown

On shutdown, stop accepting new sessions and wait for active sessions to drain (or timeout) before exiting.

## Related Recipes

- **[Voice Backends Configuration](/docs/recipes/voice/voice-backends/)** -- Config and provider setup
- **[S2S Voice Metrics](/docs/recipes/voice/s2s-voice-metrics/)** -- Custom metrics for voice systems
- **[LLM Error Handling](/docs/recipes/llm/llm-error-handling/)** -- Similar error handling and retry patterns
