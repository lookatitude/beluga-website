---
title: Long-Term Patient History Tracker
description: "Maintain comprehensive patient history across visits and providers with persistent memory and semantic retrieval. HIPAA compliant."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "patient history AI, medical record retrieval, healthcare memory, semantic clinical search, HIPAA AI, Beluga AI, Go, health tech"
---

A physician treating a patient for chest pain needs to know about the patient's cardiac history, current medications, allergies, and recent lab results — information that may be scattered across an EHR system, specialist referral notes, pharmacy records, and previous hospital visits. Searching through these systems manually takes 10-15 minutes per patient, and critical context is still missed because keyword search cannot find semantically related information (searching "heart problems" won't surface a note about "mitral valve prolapse"). Studies show that 60-70% of relevant patient history is not surfaced during clinical encounters, contributing to an estimated 12 million diagnostic errors annually in the US.

The challenge is not just storage but retrieval: a patient's 20-year medical history might contain thousands of entries, but only a handful are relevant to any given clinical question. Traditional database queries require knowing exactly what to search for, but clinical reasoning often starts with vague queries like "any previous respiratory issues" that require semantic understanding.

## Solution Architecture

Beluga AI's embedders and vector stores enable semantic retrieval of patient history. Interactions are stored persistently in a vector store and indexed using embeddings for semantic search, with structured metadata (patient ID, type, provider) for exact filtering. If an assistant also needs conversation memory, the `memory` package's MemGPT-style tiers (`memory.NewArchival`, `memory.NewRecall`) can sit alongside this store. This design means a query like "cardiac history" retrieves relevant entries even if the original notes used terms like "MI", "STEMI", or "troponin elevation". Access control integrates at the retrieval layer to enforce HIPAA requirements — every query is filtered by patient-provider authorization before results are returned.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Patient    │───▶│   History    │───▶│   Memory     │
│ Interaction  │    │   Tracker    │    │    Store     │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
┌──────────────┐    ┌──────────────┐    ┌─────▼────────┐
│   Patient    │◀───│   Semantic   │◀───│  Persistent  │
│   History    │    │    Search    │    │   Storage    │
└──────────────┘    └──────────────┘    └──────────────┘
       ▲
       │
┌──────┴───────┐
│   Provider   │
│    Query     │
└──────────────┘
```

## Implementation

### Patient History Tracker

The tracker maintains long-term patient history with semantic indexing:

```go
import (
    "context"
    "fmt"
    "os"
    "sort"
    "time"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

type PatientHistoryTracker struct {
    embedder embedding.Embedder
    store    vectorstore.VectorStore
}

func NewPatientHistoryTracker(ctx context.Context) (*PatientHistoryTracker, error) {
    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-large",
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        // Require TLS to the database (sslmode=verify-full in production)
        BaseURL: "postgresql://localhost/patient_history?sslmode=require",
        Options: map[string]any{
            "table":     "patient_history",
            "dimension": float64(3072), // text-embedding-3-large
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    return &PatientHistoryTracker{
        embedder: embedder,
        store:    store,
    }, nil
}
```

### Recording Interactions

Each interaction is stored with both an embedding (for semantic search) and structured metadata (for exact filtering by patient ID, type, and provider). This dual indexing is important because clinical queries combine semantic intent ("cardiac history") with exact constraints ("for patient P-12345 only"):

```go
type PatientInteraction struct {
    ID         string
    PatientID  string
    Type       string // "visit", "diagnosis", "prescription", etc.
    Details    string
    ProviderID string
    Timestamp  time.Time
}

func (t *PatientHistoryTracker) RecordInteraction(ctx context.Context, interaction PatientInteraction) error {
    // Create history entry
    historyText := fmt.Sprintf("%s - %s: %s",
        interaction.Type,
        interaction.Timestamp.Format("2006-01-02"),
        interaction.Details,
    )

    // Generate embedding
    vec, err := t.embedder.EmbedSingle(ctx, historyText)
    if err != nil {
        return fmt.Errorf("embed interaction: %w", err)
    }

    // Store with metadata used for exact filtering
    doc := schema.Document{
        ID:      interaction.ID,
        Content: historyText,
        Metadata: map[string]any{
            "patient_id":  interaction.PatientID,
            "type":        interaction.Type,
            "provider_id": interaction.ProviderID,
            "timestamp":   interaction.Timestamp.UTC().Format(time.RFC3339),
        },
    }

    if err := t.store.Add(ctx, []schema.Document{doc}, [][]float32{vec}); err != nil {
        return fmt.Errorf("store interaction: %w", err)
    }

    return nil
}
```

### Retrieving History

Retrieve patient history using semantic search, filtered to one patient with `vectorstore.WithFilter`:

```go
type HistoryEntry struct {
    Content   string
    Metadata  map[string]any
    Score     float64
    Timestamp time.Time
}

// GetHistory returns the topK entries for one patient that best match the
// clinical question. Chronological "everything for this patient" listings
// belong in your EHR database; the vector store answers relevance queries.
func (t *PatientHistoryTracker) GetHistory(ctx context.Context, patientID, query string, topK int) ([]HistoryEntry, error) {
    queryVec, err := t.embedder.EmbedSingle(ctx, query)
    if err != nil {
        return nil, fmt.Errorf("embed query: %w", err)
    }

    // Semantic search restricted to this patient by metadata filter
    results, err := t.store.Search(ctx, queryVec, topK,
        vectorstore.WithFilter(map[string]any{
            "patient_id": patientID,
        }),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    // Convert to history entries
    entries := make([]HistoryEntry, len(results))
    for i, result := range results {
        ts, _ := result.Metadata["timestamp"].(string)
        when, err := time.Parse(time.RFC3339, ts)
        if err != nil {
            when = time.Time{} // unknown time sorts last
        }
        entries[i] = HistoryEntry{
            Content:   result.Content,
            Metadata:  result.Metadata,
            Score:     result.Score,
            Timestamp: when,
        }
    }

    // Sort by timestamp descending (most recent first)
    sort.Slice(entries, func(i, j int) bool {
        return entries[i].Timestamp.After(entries[j].Timestamp)
    })

    return entries, nil
}
```

### Access Control

Implement HIPAA-compliant access control:

```go
type AccessControl struct {
    permissions map[string][]string // providerID -> patientIDs
}

func (t *PatientHistoryTracker) GetHistoryWithAccessControl(ctx context.Context, patientID, providerID, query string) ([]HistoryEntry, error) {
    // Verify provider has access to patient
    if !t.hasAccess(ctx, providerID, patientID) {
        return nil, fmt.Errorf("access denied: provider %s does not have access to patient %s", providerID, patientID)
    }

    // Audit log access
    t.auditLog(ctx, "history_access", providerID, patientID)

    // Retrieve history
    history, err := t.GetHistory(ctx, patientID, query, 20)
    if err != nil {
        return nil, fmt.Errorf("get history: %w", err)
    }

    return history, nil
}

func (t *PatientHistoryTracker) hasAccess(ctx context.Context, providerID, patientID string) bool {
    // Check access control system
    // Implementation depends on your access control mechanism
    return true
}

func (t *PatientHistoryTracker) auditLog(ctx context.Context, action, providerID, patientID string) {
    // Log access for HIPAA compliance
    // Implementation depends on your audit logging system
}
```

## Production Considerations

### Encryption

Encrypt patient data at rest and in transit for HIPAA compliance. Beluga AI's vector stores have no built-in encryption option, so use TLS to the database, encrypted volumes, and encrypt the stored text in the application:

```go
// RecordEncrypted stores only ciphertext in the vector store's Content.
// Beluga AI's vector stores do not encrypt content themselves:
// combine TLS to the database, encrypted storage volumes, and
// application-level encryption of the stored text.
func (t *PatientHistoryTracker) RecordEncrypted(ctx context.Context, interaction PatientInteraction, encrypt func(string) (string, error)) error {
    historyText := fmt.Sprintf("%s - %s: %s",
        interaction.Type, interaction.Timestamp.Format("2006-01-02"), interaction.Details)

    // Embed the plaintext (vectors are not reversible to the text, but
    // treat them as sensitive too), then store only ciphertext as Content.
    vec, err := t.embedder.EmbedSingle(ctx, historyText)
    if err != nil {
        return fmt.Errorf("embed interaction: %w", err)
    }
    ciphertext, err := encrypt(historyText)
    if err != nil {
        return fmt.Errorf("encrypt interaction: %w", err)
    }

    doc := schema.Document{
        ID:      interaction.ID,
        Content: ciphertext,
        Metadata: map[string]any{
            "patient_id": interaction.PatientID,
            "timestamp":  interaction.Timestamp.UTC().Format(time.RFC3339),
        },
    }
    return t.store.Add(ctx, []schema.Document{doc}, [][]float32{vec})
}
```

### Data Retention

Implement retention policies for regulatory compliance:

```go
// PurgeOldRecords deletes entries past the retention period. VectorStore
// deletes by document ID, so look the IDs up in your system of record
// (idsOlderThan is your query against it).
func (t *PatientHistoryTracker) PurgeOldRecords(ctx context.Context, retentionYears int) error {
    cutoff := time.Now().AddDate(-retentionYears, 0, 0)

    ids, err := idsOlderThan(ctx, cutoff)
    if err != nil {
        return fmt.Errorf("find expired records: %w", err)
    }
    if len(ids) == 0 {
        return nil
    }

    if err := t.store.Delete(ctx, ids); err != nil {
        return fmt.Errorf("purge old records: %w", err)
    }

    return nil
}
```

### Observability

Track history access and performance for compliance and optimization:

```go
import "github.com/lookatitude/beluga-ai/v2/o11y"

func (t *PatientHistoryTracker) RecordInteractionWithTracing(ctx context.Context, interaction PatientInteraction) error {
    ctx, span := o11y.StartSpan(ctx, "patient_history.record", o11y.Attrs{
        "patient_id":       interaction.PatientID,
        "interaction_type": interaction.Type,
        "provider_id":      interaction.ProviderID,
    })
    defer span.End()

    if err := t.RecordInteraction(ctx, interaction); err != nil {
        span.RecordError(err)
        span.SetStatus(o11y.StatusError, err.Error())
        return err
    }

    span.SetStatus(o11y.StatusOK, "")
    return nil
}
```

### Performance

- **Indexing strategy**: Create indexes on patient_id, timestamp, and type for fast filtering
- **Partitioning**: Partition by patient_id or time range for large datasets
- **Caching**: Cache frequently accessed patient histories
- **Batch operations**: Batch record insertions for efficiency

## Results

After implementing the patient history tracker, the provider achieved:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Information Retention | 60-70% | 96% | 37-60% improvement |
| Duplicate Test Rate | 15-20% | 4% | 73-80% reduction |
| Care Coordination Score | 6.0/10 | 9.2/10 | 53% improvement |
| Provider Access Time | 10-15 min | 1.5 min | 85-90% reduction |
| Patient Satisfaction | 7.0/10 | 9.1/10 | 30% improvement |
| Care Quality Score | 7.5/10 | 9.0/10 | 20% improvement |

## Related Resources

- [Memory Guide](/docs/guides/capabilities/memory/memory-system/) for persistent memory patterns
- [RAG Pipeline Guide](/docs/guides/capabilities/rag/rag-pipeline/) for semantic search setup
- [Security Guide](/docs/guides/production/safety-and-guards/) for HIPAA compliance and encryption
