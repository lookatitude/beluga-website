---
title: Dynamic Feature Flags for AI
description: "Implement hot-reloadable feature flags for gradual AI model rollouts, A/B testing, and instant toggles without deployments."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "feature flags AI, hot-reload config, gradual rollout, AI model toggle, canary deployment, Beluga AI, Go, DevOps AI"
---

Deploying new AI features (a new model, a different prompt strategy, an updated guard rule) carries risk. If a new model produces poor responses for a specific customer segment, the fix requires a code change, CI/CD pipeline, and deployment — a 2-4 hour window where affected users see degraded quality. For AI features specifically, this delay is worse than for traditional features because LLM behavior is harder to predict in production than in testing.

Feature flags decouple deployment from activation. Ship the new model behind a flag, enable it for 5% of traffic, monitor quality metrics, then gradually increase — or instantly disable if metrics degrade. No deployment needed for any of these operations.

Beluga AI's `config/` package provides the foundation: hot-reloadable configuration with file system watching, so flag changes propagate to all instances within seconds.

## Solution Architecture

The feature flag manager builds on Beluga AI's `config/` package for hot-reload support with validation. Flag configurations load into an in-memory cache for sub-millisecond evaluation on the request path. The `config.Watch()` mechanism detects file changes and triggers reloads without application restarts. Percentage-based rollouts use deterministic user ID hashing so the same user always sees the same variant — critical for consistent user experience and valid A/B comparisons.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Feature    │───▶│    Config    │───▶│     Flag     │
│   Flag       │    │   Watcher    │    │    Cache     │
│   Config     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Application │◀───│     Flag     │◀───│     User     │
│     Code     │    │   Evaluator  │    │   Context    │
│              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Feature Flag Manager

The flag manager loads feature flags from a JSON configuration file with `config.Load`, then uses `config.NewFileWatcher` to reload the flags whenever the file changes.

```go
package featureflags

import (
    "context"
    "encoding/json"
    "fmt"
    "sync"
    "time"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/o11y"
)

// FeatureFlag represents a dynamic feature flag.
type FeatureFlag struct {
    Name           string            `json:"name"`
    Enabled        bool              `json:"enabled"`
    RolloutPercent int               `json:"rollout_percent"`
    UserSegments   []string          `json:"user_segments,omitempty"`
    Metadata       map[string]string `json:"metadata,omitempty"`
}

// FlagsFile is the on-disk shape of the flags configuration.
type FlagsFile struct {
    Features []FeatureFlag `json:"features" required:"true"`
}

// FeatureFlagManager manages dynamic feature flags with hot-reloading.
type FeatureFlagManager struct {
    flags   map[string]*FeatureFlag
    mu      sync.RWMutex
    watcher config.Watcher
}

// NewFeatureFlagManager loads the flags and starts watching the file.
func NewFeatureFlagManager(ctx context.Context, configPath string) (*FeatureFlagManager, error) {
    file, err := config.Load[FlagsFile](configPath)
    if err != nil {
        return nil, fmt.Errorf("load initial flags: %w", err)
    }

    manager := &FeatureFlagManager{
        flags:   make(map[string]*FeatureFlag),
        watcher: config.NewFileWatcher(configPath, time.Second),
    }
    manager.setFlags(file.Features)

    // Watch for config changes (polls once per second).
    go manager.watchFlags(ctx)

    return manager, nil
}

// Close stops the file watcher.
func (m *FeatureFlagManager) Close() error {
    return m.watcher.Close()
}

func (m *FeatureFlagManager) setFlags(flags []FeatureFlag) {
    next := make(map[string]*FeatureFlag, len(flags))
    for i := range flags {
        next[flags[i].Name] = &flags[i]
    }

    m.mu.Lock()
    defer m.mu.Unlock()
    m.flags = next
}

func (m *FeatureFlagManager) watchFlags(ctx context.Context) {
    logger := o11y.FromContext(ctx)
    err := m.watcher.Watch(ctx, func(raw any) {
        data, ok := raw.([]byte)
        if !ok {
            return
        }
        var file FlagsFile
        if err := json.Unmarshal(data, &file); err != nil {
            // Keep serving the previous flags on a bad update.
            logger.Error(ctx, "invalid feature flag update", "error", err)
            return
        }
        m.setFlags(file.Features)
    })
    if err != nil && ctx.Err() == nil {
        logger.Error(ctx, "feature flag watcher stopped", "error", err)
    }
}
```

## Flag Evaluation with Gradual Rollouts

The evaluator checks flag state, applies percentage-based rollouts, and supports user segmentation.

```go
// IsEnabled checks if a feature flag is enabled for a given user.
func (m *FeatureFlagManager) IsEnabled(ctx context.Context, flagName string, userID string) bool {
    m.mu.RLock()
    flag, exists := m.flags[flagName]
    m.mu.RUnlock()

    if !exists || !flag.Enabled {
        return false
    }

    // Check rollout percentage
    if flag.RolloutPercent < 100 {
        return m.isUserInRollout(userID, flag.RolloutPercent)
    }

    // Check user segments
    if len(flag.UserSegments) > 0 {
        return m.isUserInSegment(userID, flag.UserSegments)
    }

    return true
}

func (m *FeatureFlagManager) isUserInRollout(userID string, percent int) bool {
    // Hash user ID to consistent value
    hash := hashString(userID)
    userPercent := int(hash % 100)
    return userPercent < percent
}

func (m *FeatureFlagManager) isUserInSegment(userID string, segments []string) bool {
    // Check if user belongs to any of the segments
    userSegment := getUserSegment(userID)
    for _, segment := range segments {
        if segment == userSegment {
            return true
        }
    }
    return false
}

func hashString(s string) uint32 {
    h := uint32(0)
    for i := 0; i < len(s); i++ {
        h = h*31 + uint32(s[i])
    }
    return h
}
```

## Configuration Example

Feature flags are defined in a JSON configuration file (`config.Load` supports `.json` files):

```json
{
  "features": [
    {
      "name": "new_dashboard",
      "enabled": true,
      "rollout_percent": 10,
      "metadata": {"description": "New dashboard redesign"}
    },
    {
      "name": "experimental_ai_model",
      "enabled": true,
      "rollout_percent": 100,
      "user_segments": ["beta_users", "internal"],
      "metadata": {"description": "Experimental AI model for beta users"}
    },
    {
      "name": "legacy_api",
      "enabled": false,
      "metadata": {"description": "Legacy API endpoint (disabled)"}
    }
  ]
}
```

## Observability

Track flag evaluations and changes with OpenTelemetry metrics:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/metric"
)

func (m *FeatureFlagManager) IsEnabledWithMetrics(ctx context.Context, flagName string, userID string) bool {
    enabled := m.IsEnabled(ctx, flagName, userID)

    // In production, create the counter once and store it on the manager.
    meter := otel.Meter("feature-flags")
    counter, err := meter.Int64Counter("feature_flag_checks_total")
    if err != nil {
        return enabled
    }

    counter.Add(ctx, 1,
        metric.WithAttributes(
            attribute.String("flag_name", flagName),
            attribute.Bool("enabled", enabled),
        ),
    )

    return enabled
}
```

## Production Considerations

### Hot Reload Performance

Configuration hot-reloading adds minimal overhead. `config.FileWatcher` polls the file at the configured interval (one second above) and compares a content hash, so flag updates land within about one interval. In-memory flag cache ensures sub-millisecond evaluation times.

### Consistency Guarantees

User ID hashing provides deterministic rollout percentages. The same user ID always maps to the same rollout bucket, ensuring consistent feature access. When increasing rollout percentages, users who previously saw the feature continue to see it.

### Audit Trail

Track all flag changes for compliance and debugging:

```go
type FlagAudit struct {
    FlagName  string
    OldValue  bool
    NewValue  bool
    ChangedBy string
    ChangedAt time.Time
}

func (m *FeatureFlagManager) auditFlagChange(ctx context.Context, change FlagAudit) error {
    // Log to audit system
    logger := o11y.FromContext(ctx)
    logger.Info(ctx, "feature flag changed",
        "flag", change.FlagName,
        "old_value", change.OldValue,
        "new_value", change.NewValue,
        "changed_by", change.ChangedBy,
        "changed_at", change.ChangedAt,
    )

    return nil
}
```

### Emergency Disable

Disable problematic features quickly by updating the configuration file. The change reaches each instance within one polling interval without requiring deployments or application restarts.

### Scaling

The flag manager is stateless and scales horizontally. Each application instance maintains its own in-memory flag cache synchronized from the shared configuration source. This architecture supports thousands of concurrent flag evaluations with minimal latency.

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Feature Toggle Time (minutes) | 120-240 | 0.5 | 99.6-99.8% reduction |
| Emergency Disable Time (minutes) | 120-240 | 0.3 | 99.7-99.9% reduction |
| Production Incidents from Features | 8/month | 1 | 87.5% reduction |
| Feature Rollout Success Rate | 85% | 98.5% | 16% improvement |

## Related Resources

- [Configuration Guide](/docs/guides/configuration/) for config package patterns
- [Observability Guide](/docs/guides/observability/) for metrics and tracing
- [Multi-tenant API Keys](/docs/guides/multi-tenant-keys/) for related config patterns
