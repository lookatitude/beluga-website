---
title: "Memory TTL and Cleanup"
description: "Recipe for expiring old conversation memory in Go using TTL policies — bound storage growth, ensure GDPR compliance, and optimize search performance."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, memory TTL, Go memory cleanup, data retention, GDPR compliance, storage optimization, TTL policy recipe"
---

## Problem

You need to automatically expire and clean up old conversation memory based on time-to-live (TTL) policies, preventing memory from growing unbounded and ensuring privacy compliance by removing stale data.

Memory systems without TTL enforcement face three problems. First, storage costs grow linearly with time as entries accumulate. Second, search performance degrades as the number of entries increases, because more candidates must be evaluated. Third, privacy regulations (GDPR, CCPA) may require automatic data deletion after a retention period. TTL-based cleanup addresses all three concerns: it bounds storage growth, keeps search sets manageable, and provides automatic compliance with data retention policies.

## Solution

Implement a TTL-based cleanup system that tracks memory creation times, periodically checks for expired entries, and removes them while preserving recent and important context. Each memory entry is tagged with a creation timestamp and an expiration time. A background goroutine periodically scans entries and removes expired ones. Priority-based TTL extension allows important sessions (e.g., active support conversations) to live longer than default sessions.

## Code Example

```go
package main

import (
    "context"
    "fmt"
    "log"
    "sync"
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/codes"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/memory"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

var tracer = otel.Tracer("beluga.memory.ttl_cleanup")

// MemoryFactory creates a fresh memory.Memory for a new session.
type MemoryFactory func() (memory.Memory, error)

// MemoryEntry is one session's memory plus its TTL metadata.
type MemoryEntry struct {
    Memory     memory.Memory
    CreatedAt  time.Time
    AccessedAt time.Time
    ExpiresAt  time.Time
    Priority   int // Higher priority entries expire later
}

// TTLMemoryWrapper keeps one memory.Memory per session and expires idle sessions.
type TTLMemoryWrapper struct {
    newMemory     MemoryFactory
    ttl           time.Duration
    entries       map[string]*MemoryEntry
    mu            sync.Mutex
    cleanupTicker *time.Ticker
    stopCh        chan struct{}
}

// NewTTLMemoryWrapper creates a new TTL wrapper.
func NewTTLMemoryWrapper(factory MemoryFactory, ttl time.Duration, cleanupInterval time.Duration) *TTLMemoryWrapper {
    wrapper := &TTLMemoryWrapper{
        newMemory: factory,
        ttl:       ttl,
        entries:   make(map[string]*MemoryEntry),
        stopCh:    make(chan struct{}),
    }

    wrapper.cleanupTicker = time.NewTicker(cleanupInterval)
    go wrapper.cleanupLoop(context.Background())

    return wrapper
}

// entryFor returns the live entry for a session, creating it if absent and
// clearing it if it has expired. Callers must hold tmw.mu.
func (tmw *TTLMemoryWrapper) entryFor(ctx context.Context, sessionID string) (*MemoryEntry, bool, error) {
    now := time.Now()
    expired := false
    if entry, ok := tmw.entries[sessionID]; ok {
        if now.Before(entry.ExpiresAt) {
            entry.AccessedAt = now
            return entry, false, nil
        }
        if err := entry.Memory.Clear(ctx); err != nil {
            return nil, false, err
        }
        delete(tmw.entries, sessionID)
        expired = true
    }

    mem, err := tmw.newMemory()
    if err != nil {
        return nil, expired, err
    }
    entry := &MemoryEntry{Memory: mem, CreatedAt: now, AccessedAt: now, ExpiresAt: now.Add(tmw.ttl)}
    tmw.entries[sessionID] = entry
    return entry, expired, nil
}

// Save stores a conversation turn for the session. The session's expiry is
// set when it is created; use ExtendTTL or SetPriority to lengthen it.
func (tmw *TTLMemoryWrapper) Save(ctx context.Context, sessionID string, input, output schema.Message) error {
    ctx, span := tracer.Start(ctx, "ttl_memory.save")
    defer span.End()

    tmw.mu.Lock()
    defer tmw.mu.Unlock()

    entry, _, err := tmw.entryFor(ctx, sessionID)
    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
        return err
    }
    if err := entry.Memory.Save(ctx, input, output); err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
        return err
    }

    span.SetAttributes(
        attribute.String("session_id", sessionID),
        attribute.String("expires_at", entry.ExpiresAt.Format(time.RFC3339)),
    )
    span.SetStatus(codes.Ok, "turn saved with TTL")
    return nil
}

// Load returns the session's messages, or nothing if the session expired.
func (tmw *TTLMemoryWrapper) Load(ctx context.Context, sessionID, query string) ([]schema.Message, error) {
    ctx, span := tracer.Start(ctx, "ttl_memory.load")
    defer span.End()

    tmw.mu.Lock()
    defer tmw.mu.Unlock()

    entry, expired, err := tmw.entryFor(ctx, sessionID)
    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
        return nil, err
    }
    span.SetAttributes(attribute.Bool("expired", expired))

    msgs, err := entry.Memory.Load(ctx, query)
    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
        return nil, err
    }
    span.SetStatus(codes.Ok, "messages loaded")
    return msgs, nil
}

// cleanupLoop periodically cleans up expired entries.
func (tmw *TTLMemoryWrapper) cleanupLoop(ctx context.Context) {
    for {
        select {
        case <-tmw.cleanupTicker.C:
            tmw.cleanupExpired(ctx)
        case <-tmw.stopCh:
            return
        }
    }
}

// cleanupExpired clears and removes expired sessions.
func (tmw *TTLMemoryWrapper) cleanupExpired(ctx context.Context) {
    ctx, span := tracer.Start(ctx, "ttl_memory.cleanup")
    defer span.End()

    tmw.mu.Lock()
    defer tmw.mu.Unlock()

    now := time.Now()
    expired := 0
    for key, entry := range tmw.entries {
        if now.After(entry.ExpiresAt) {
            if err := entry.Memory.Clear(ctx); err != nil {
                span.RecordError(err)
                continue // keep the entry and retry on the next tick
            }
            delete(tmw.entries, key)
            expired++
        }
    }

    span.SetAttributes(
        attribute.Int("expired_count", expired),
        attribute.Int("remaining_count", len(tmw.entries)),
    )
}

// ExtendTTL extends the TTL for a session.
func (tmw *TTLMemoryWrapper) ExtendTTL(ctx context.Context, sessionID string, additionalTTL time.Duration) error {
    _, span := tracer.Start(ctx, "ttl_memory.extend")
    defer span.End()

    tmw.mu.Lock()
    defer tmw.mu.Unlock()

    entry, exists := tmw.entries[sessionID]
    if !exists {
        return fmt.Errorf("session %s not found", sessionID)
    }

    entry.ExpiresAt = entry.ExpiresAt.Add(additionalTTL)

    span.SetAttributes(
        attribute.String("session_id", sessionID),
        attribute.String("new_expires_at", entry.ExpiresAt.Format(time.RFC3339)),
    )
    span.SetStatus(codes.Ok, "TTL extended")
    return nil
}

// SetPriority sets priority for an entry (higher priority = longer TTL).
func (tmw *TTLMemoryWrapper) SetPriority(sessionID string, priority int) {
    tmw.mu.Lock()
    defer tmw.mu.Unlock()

    if entry, exists := tmw.entries[sessionID]; exists {
        entry.Priority = priority
        entry.ExpiresAt = entry.ExpiresAt.Add(time.Duration(priority) * time.Hour)
    }
}

// Stop stops the cleanup goroutine.
func (tmw *TTLMemoryWrapper) Stop() {
    close(tmw.stopCh)
    if tmw.cleanupTicker != nil {
        tmw.cleanupTicker.Stop()
    }
}

func main() {
    ctx := context.Background()

    // Each session gets its own recall memory.
    factory := func() (memory.Memory, error) {
        return memory.New("recall", config.ProviderConfig{Provider: "recall"})
    }
    ttlMemory := NewTTLMemoryWrapper(factory, 24*time.Hour, 1*time.Hour)
    defer ttlMemory.Stop()

    err := ttlMemory.Save(ctx, "session-123",
        schema.NewHumanMessage("Hello"),
        schema.NewAIMessage("Hi!"),
    )
    if err != nil {
        log.Fatalf("Failed to save: %v", err)
    }

    msgs, err := ttlMemory.Load(ctx, "session-123", "")
    if err != nil {
        log.Fatalf("Failed to load: %v", err)
    }
    fmt.Printf("Loaded %d messages\n", len(msgs))
}
```

## Explanation

1. **TTL tracking** -- Each session gets its own `memory.Memory`, associated with a creation time and an expiration time. When entries are loaded, the wrapper checks the TTL before returning data. Expired sessions are cleared with `Memory.Clear` and replaced by a fresh memory, ensuring stale data is never served. This provides automatic data lifecycle management without requiring callers to manage expiration themselves.

2. **Periodic cleanup** -- A background goroutine periodically scans all entries and removes expired ones. This prevents the entry map from growing unbounded even if entries are never accessed (and thus never checked lazily). The cleanup interval should balance between responsiveness (removing expired entries promptly) and overhead (lock contention from frequent scans).

3. **Access-based timestamps** -- When entries are accessed, their `AccessedAt` timestamp is updated. This information can be used for more sophisticated TTL policies, such as extending the TTL for frequently-accessed sessions or implementing LRU-style eviction. The access tracking adds minimal overhead since it piggybacks on the existing lock acquisition.

4. **Priority-based TTL** -- High-priority sessions (e.g., active support conversations, VIP users) can have their TTL extended automatically via `SetPriority`. Each priority level adds one hour to the expiration time. This balances memory efficiency with preserving valuable context for important interactions.

## Variations

### Lazy Expiration

Check expiration only on access instead of running a background cleanup, reducing overhead for small deployments:

```go
func (tmw *TTLMemoryWrapper) LoadWithLazyExpiration(ctx context.Context, sessionID, query string) ([]schema.Message, error) {
    // Check expiration on load only
}
```

### Gradual Expiration

Gradually reduce priority instead of hard expiration, preserving summaries of expired conversations:

```go
func (tmw *TTLMemoryWrapper) GradualExpiration(ctx context.Context) {
    // Reduce priority over time
}
```

## Related Recipes

- [Window-Based Context Recovery](/docs/recipes/memory/memory-context-recovery/) -- Recover context from sliding windows
- [Conversation Expiry Logic](/docs/recipes/memory/conversation-expiry/) -- Expire inactive conversations
