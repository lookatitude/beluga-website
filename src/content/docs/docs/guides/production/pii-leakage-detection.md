---
title: Real-Time PII Leakage Detection
description: "Detect and prevent PII leakage in LLM requests and responses. HIPAA and GDPR compliance with bidirectional scanning guardrails."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "PII detection, data leakage prevention, HIPAA compliance AI, GDPR guard, SSN detection, Beluga AI, Go, privacy guardrails"
---

When a healthcare chatbot sends a patient's Social Security number to an LLM provider's API, the organization faces a HIPAA violation with penalties up to $1.8M per incident, mandatory breach notification to affected individuals, and potential loss of healthcare contracts. GDPR violations carry fines up to 4% of global annual revenue. The risk is not hypothetical — users routinely include PII in natural language queries ("My SSN is 123-45-6789, can you check my claim status?"), and without interception, this data reaches third-party servers where it may be logged, cached, or used for model training.

The challenge compounds with LLM responses: even if input is clean, the model might hallucinate PII patterns or echo back sensitive data from its context window. Both directions — request and response — require scanning, and the scanning must happen at the framework level rather than relying on application developers to remember to sanitize every call.

## Solution Architecture

Beluga AI's `guard/` package implements a three-stage pipeline designed specifically for this bidirectional threat: input guards scan requests before LLM calls, output guards scan responses before returning to users, and tool guards scan tool execution parameters. This three-stage architecture is essential because PII can enter the system at any point — user input, tool results, or LLM responses. Pattern matching handles structured PII (SSNs, credit cards, phone numbers) with high confidence, while optional ML classification catches unstructured PII (names mentioned in free text) that regex alone would miss.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ LLM Request  │───▶│ Input Guard  │───▶│ Pattern      │
│              │    │ (PII Check)  │    │ Matcher      │
└──────────────┘    └──────┬───────┘    └──────┬───────┘
                           │                   │
                           │                   ▼
                           │            ┌──────────────┐
                           │            │ ML           │
                           │            │ Classifier   │
                           │            └──────┬───────┘
                           │                   │
                           ▼                   ▼
                    ┌──────────────┐    ┌──────────────┐
                    │ Block        │◀───│ PII          │
                    │ Request      │    │ Detected?    │
                    └──────┬───────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Alert &      │
                    │ Audit Log    │
                    └──────────────┘
```

## PII Detection Implementation

Implement PII detection with pattern matching and audit logging:

```go
package main

import (
    "context"
    "regexp"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/metric"
    "go.opentelemetry.io/otel/trace"
)

// PIIType represents a type of PII
type PIIType string

const (
    PIITypeSSN          PIIType = "ssn"
    PIITypeEmail        PIIType = "email"
    PIITypePhone        PIIType = "phone"
    PIITypeCreditCard   PIIType = "credit_card"
    PIITypeMRN          PIIType = "medical_record_number"
    PIITypePatientID    PIIType = "patient_id"
)

// PIIDetection represents a detected PII instance
type PIIDetection struct {
    Type       PIIType
    Value      string  // Redacted value
    Confidence float64
    Location   string  // "input" or "output"
}

// PIIDetector detects PII in text
type PIIDetector struct {
    patterns          map[PIIType]*regexp.Regexp
    tracer            trace.Tracer
    detectionsCounter metric.Int64Counter
    blockedCounter    metric.Int64Counter
}

// NewPIIDetector creates a new PII detector
func NewPIIDetector(ctx context.Context) (*PIIDetector, error) {
    patterns := make(map[PIIType]*regexp.Regexp)

    // SSN pattern: XXX-XX-XXXX
    patterns[PIITypeSSN] = regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`)

    // Email pattern
    patterns[PIITypeEmail] = regexp.MustCompile(`\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`)

    // Phone pattern: (XXX) XXX-XXXX or XXX-XXX-XXXX
    patterns[PIITypePhone] = regexp.MustCompile(`\b(\(?\d{3}\)?[-.\s])\d{3}[-.\s]\d{4}\b`)

    // Credit card pattern
    patterns[PIITypeCreditCard] = regexp.MustCompile(`\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b`)

    // Medical Record Number pattern
    patterns[PIITypeMRN] = regexp.MustCompile(`\bMRN[:\s-]?\d{6,}\b`)

    meter := otel.GetMeterProvider().Meter("pii-detection")
    detectionsCounter, err := meter.Int64Counter("pii_detections_total")
    if err != nil {
        return nil, err
    }
    blockedCounter, err := meter.Int64Counter("pii_requests_blocked_total")
    if err != nil {
        return nil, err
    }

    return &PIIDetector{
        patterns:          patterns,
        tracer:            otel.Tracer("pii-detection"),
        detectionsCounter: detectionsCounter,
        blockedCounter:    blockedCounter,
    }, nil
}

// DetectPII detects PII in text
func (d *PIIDetector) DetectPII(ctx context.Context, text string, location string) ([]PIIDetection, error) {
    ctx, span := d.tracer.Start(ctx, "pii.detect")
    defer span.End()

    span.SetAttributes(
        attribute.String("location", location),
        attribute.Int("text_length", len(text)),
    )

    var detections []PIIDetection

    // Pattern-based detection
    for piiType, pattern := range d.patterns {
        matches := pattern.FindAllString(text, -1)
        for _, match := range matches {
            // Redact for logging (show only last 4 chars)
            redacted := d.redactPII(match, piiType)

            detections = append(detections, PIIDetection{
                Type:       piiType,
                Value:      redacted,
                Confidence: 1.0,
                Location:   location,
            })
        }
    }

    if len(detections) > 0 {
        span.SetAttributes(
            attribute.Int("detection_count", len(detections)),
        )

        d.detectionsCounter.Add(ctx, int64(len(detections)),
            metric.WithAttributes(
                attribute.String("location", location),
            ),
        )
    }

    return detections, nil
}

func (d *PIIDetector) redactPII(value string, piiType PIIType) string {
    if len(value) <= 4 {
        return "****"
    }
    return "****" + value[len(value)-4:]
}
```

## Guard Integration

Integrate PII detection with Beluga AI's guard pipeline:

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/guard"
    "github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
)

// PIIGuard implements guard.Guard (Name + Validate) using PIIDetector.
type PIIGuard struct {
    detector *PIIDetector
}

func NewPIIGuard(detector *PIIDetector) *PIIGuard {
    return &PIIGuard{detector: detector}
}

func (g *PIIGuard) Name() string { return "pii_detector" }

func (g *PIIGuard) Validate(ctx context.Context, input guard.GuardInput) (guard.GuardResult, error) {
    detections, err := g.detector.DetectPII(ctx, input.Content, input.Role)
    if err != nil {
        return guard.GuardResult{}, fmt.Errorf("pii detection failed: %w", err)
    }
    if len(detections) > 0 {
        g.detector.blockedCounter.Add(ctx, 1)
        return guard.GuardResult{
            Allowed: false,
            Reason:  fmt.Sprintf("PII detected: %d detection(s) found", len(detections)),
        }, nil
    }
    return guard.GuardResult{Allowed: true}, nil
}

// GuardedModel runs the guard pipeline on the prompt and the response
// around every Generate call.
type GuardedModel struct {
    model  llm.ChatModel
    guards *guard.Pipeline
}

func createGuardedModel(ctx context.Context) (*GuardedModel, error) {
    detector, err := NewPIIDetector(ctx)
    if err != nil {
        return nil, err
    }

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return nil, err
    }

    piiGuard := NewPIIGuard(detector)
    return &GuardedModel{
        model:  model,
        guards: guard.NewPipeline(guard.Input(piiGuard), guard.Output(piiGuard)),
    }, nil
}

func (g *GuardedModel) Generate(ctx context.Context, msgs []schema.Message) (string, error) {
    for _, msg := range msgs {
        for _, part := range msg.GetContent() {
            text, ok := part.(schema.TextPart)
            if !ok {
                continue
            }
            res, err := g.guards.ValidateInput(ctx, text.Text)
            if err != nil {
                return "", err
            }
            if !res.Allowed {
                return "", fmt.Errorf("input blocked by %s: %s", res.GuardName, res.Reason)
            }
        }
    }

    resp, err := g.model.Generate(ctx, msgs)
    if err != nil {
        return "", err
    }

    res, err := g.guards.ValidateOutput(ctx, resp.Text())
    if err != nil {
        return "", err
    }
    if !res.Allowed {
        return "", fmt.Errorf("output blocked by %s: %s", res.GuardName, res.Reason)
    }
    return resp.Text(), nil
}
```

For redaction instead of blocking, the built-in `guard.NewPIIRedactor(guard.DefaultPIIPatterns...)` returns the sanitized text in `GuardResult.Modified`.

## Production Considerations

### False Positive Tuning

Reduce false positives by refining regex patterns and implementing context-aware detection:

```go
// Require a separator after the area code so longer digit runs (zip+4,
// order numbers) are not matched. Go's regexp (RE2) has no lookahead.
patterns[PIITypePhone] = regexp.MustCompile(`\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b`)

// Avoid matching credit card test numbers
func isTestCreditCard(number string) bool {
    testPrefixes := []string{"4111111111111111", "5555555555554444"}
    for _, prefix := range testPrefixes {
        if number == prefix {
            return true
        }
    }
    return false
}
```

### Audit Logging

Log all PII detections for compliance audits:

```go
func (d *PIIDetector) auditLog(ctx context.Context, detections []PIIDetection, location string) {
    for _, detection := range detections {
        log := map[string]interface{}{
            "timestamp":  time.Now().UTC(),
            "pii_type":   detection.Type,
            "location":   detection.Location,
            "confidence": detection.Confidence,
            "value":      detection.Value,  // Redacted
        }
        // Send to audit log system
        auditLogger.Log(ctx, log)
    }
}
```

### Performance Optimization

Optimize detection for high-volume systems:

```go
// Compile patterns once at initialization
var compiledPatterns = compilePatterns()

// Use sync.Pool for temporary buffers
var bufferPool = sync.Pool{
    New: func() interface{} {
        return new(bytes.Buffer)
    },
}

// Batch process requests
func (d *PIIDetector) DetectBatch(ctx context.Context, texts []string) ([][]PIIDetection, error) {
    results := make([][]PIIDetection, len(texts))
    var wg sync.WaitGroup

    for i, text := range texts {
        wg.Add(1)
        go func(idx int, txt string) {
            defer wg.Done()
            results[idx], _ = d.DetectPII(ctx, txt, "input")
        }(i, text)
    }

    wg.Wait()
    return results, nil
}
```

## Related Resources

- [Guard Pipeline Guide](/docs/guides/safety/) for input/output validation patterns
- [Token Cost Attribution](/docs/guides/token-cost-attribution/) for user-level monitoring
- [Monitoring Dashboards](/docs/guides/monitoring-dashboards/) for observability setup
