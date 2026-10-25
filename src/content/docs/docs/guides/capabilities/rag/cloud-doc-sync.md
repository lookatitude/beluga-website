---
title: Automated Cloud Document Sync for RAG
description: "Maintain real-time RAG knowledge bases by auto-syncing documents from S3, GCS, and Azure Blob with ETag change detection."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "cloud document sync, RAG real-time, S3 ingestion, document pipeline, change detection, Beluga AI, Go, knowledge base sync"
---

A technology company needed to maintain a real-time knowledge base by automatically syncing documents from cloud storage (S3, GCS, Azure Blob) into their RAG system. The core problem is that RAG systems are only as good as their indexed data — stale embeddings from outdated documents produce wrong answers with high confidence, which is more damaging than no answer at all. Manual document ingestion led to 3-5 day delays, 15-20% stale data in RAG indexes, and missed updates from 50+ cloud buckets.

An automated cloud sync system with change detection enables near real-time RAG updates with less than 5 minute latency. The system uses ETag-based change detection rather than re-indexing everything, which means only modified documents are re-processed through the embedding pipeline. This incremental approach keeps costs proportional to change volume, not total document count.

## Solution Architecture

Beluga AI's `cloudstorage` loader reads objects from S3, GCS and Azure Blob through one `loader.DocumentLoader`, choosing the provider from the URL scheme (`s3://`, `gs://`, `az://`). Listing buckets and reading ETags is done with each cloud's own SDK or bucket notifications. The sync system monitors cloud buckets for changes via webhooks and polling, tracks file ETags to detect modifications, and incrementally processes only changed documents through the RAG pipeline.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    Cloud     │───▶│    Change    │───▶│     Sync     │
│   Storage    │    │   Detector   │    │ Coordinator  │
│   Buckets    │    │              │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Vector     │◀───│  Embeddings  │◀───│   Document   │
│    Store     │    │              │    │    Loader    │
│              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Cloud Storage Adapters

One `cloudstorage` loader covers all three providers.

```go
import (
    "context"
    "fmt"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"

    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/cloudstorage"
)

// CloudLoaderConfig configures cloud storage access.
type CloudLoaderConfig struct {
    Provider  string // "s3", "gcs", "azure"
    Bucket    string
    Prefix    string
    AccessKey string
    SecretKey string
    Region    string
}

// CreateCloudLoader creates the "cloudstorage" document loader. One loader
// handles S3, GCS and Azure Blob; the provider is picked from the URL
// scheme (s3://, gs://, az://) passed to Load.
func CreateCloudLoader(ctx context.Context, cfg CloudLoaderConfig) (loader.DocumentLoader, error) {
    return loader.New("cloudstorage", config.ProviderConfig{
        APIKey: cfg.AccessKey,
        Options: map[string]any{
            "secret_key": cfg.SecretKey,
            "region":     cfg.Region,
        },
    })
}

// ObjectURL builds the URL the loader expects for one object.
func ObjectURL(cfg CloudLoaderConfig, key string) (string, error) {
    scheme := map[string]string{"s3": "s3://", "gcs": "gs://", "azure": "az://"}[cfg.Provider]
    if scheme == "" {
        return "", fmt.Errorf("unsupported provider: %s", cfg.Provider)
    }
    return scheme + cfg.Bucket + "/" + strings.TrimPrefix(key, "/"), nil
}
```

## Change Detection

The change detector monitors buckets for new and modified files using ETags.

```go
import (
    "context"
    "iter"
    "log"
    "time"
)

// ChangeEvent represents a file change in cloud storage.
type ChangeEvent struct {
    Path     string // object key
    Bucket   string
    ETag     string
    Action   string // "added", "modified", "deleted"
    Provider string
}

// ObjectInfo is one entry from a bucket listing.
type ObjectInfo struct {
    Key  string
    ETag string
}

// ChangeDetector monitors cloud storage for changes.
type ChangeDetector struct {
    buckets      []CloudLoaderConfig
    tracker      *ChangeTracker
    pollInterval time.Duration
    // listObjects lists keys and ETags under cfg.Prefix using your cloud
    // SDK (S3 ListObjectsV2, GCS Objects.List, Azure ListBlobs). The
    // Beluga AI loader reads objects; it does not list buckets.
    listObjects func(ctx context.Context, cfg CloudLoaderConfig) ([]ObjectInfo, error)
}

// DetectChanges monitors buckets and emits change events.
func (d *ChangeDetector) DetectChanges(ctx context.Context) iter.Seq2[ChangeEvent, error] {
    return func(yield func(ChangeEvent, error) bool) {
        // Setup webhook listeners (bucket notifications) for real-time updates
        webhookEvents := make(chan ChangeEvent, 100)
        for _, bucket := range d.buckets {
            go d.listenWebhooks(ctx, bucket, webhookEvents)
        }

        // Poll as fallback
        ticker := time.NewTicker(d.pollInterval)
        defer ticker.Stop()

        for {
            select {
            case <-ctx.Done():
                return
            case event := <-webhookEvents:
                if !yield(event, nil) {
                    return
                }
            case <-ticker.C:
                for _, bucket := range d.buckets {
                    changes, err := d.pollBucket(ctx, bucket)
                    if err != nil {
                        if !yield(ChangeEvent{}, err) {
                            return
                        }
                        continue
                    }
                    for _, change := range changes {
                        if !yield(change, nil) {
                            return
                        }
                    }
                }
            }
        }
    }
}

func (d *ChangeDetector) pollBucket(ctx context.Context, cfg CloudLoaderConfig) ([]ChangeEvent, error) {
    objects, err := d.listObjects(ctx, cfg)
    if err != nil {
        return nil, err
    }

    var changes []ChangeEvent
    for _, obj := range objects {
        // Check if file has changed
        lastETag, exists := d.tracker.GetETag(obj.Key)
        if !exists || lastETag != obj.ETag {
            action := "modified"
            if !exists {
                action = "added"
            }
            changes = append(changes, ChangeEvent{
                Path:     obj.Key,
                Bucket:   cfg.Bucket,
                ETag:     obj.ETag,
                Action:   action,
                Provider: cfg.Provider,
            })
        }
    }
    log.Printf("bucket %s: %d changes", cfg.Bucket, len(changes))

    return changes, nil
}
```

## Change Tracker

The tracker stores file ETags to detect modifications.

```go
import (
    "sync"
)

// ChangeTracker stores file ETags for change detection.
type ChangeTracker struct {
    etags map[string]string
    mu    sync.RWMutex
}

func NewChangeTracker() *ChangeTracker {
    return &ChangeTracker{
        etags: make(map[string]string),
    }
}

func (ct *ChangeTracker) GetETag(path string) (string, bool) {
    ct.mu.RLock()
    defer ct.mu.RUnlock()

    etag, exists := ct.etags[path]
    return etag, exists
}

func (ct *ChangeTracker) UpdateETag(path string, etag string) {
    ct.mu.Lock()
    defer ct.mu.Unlock()

    ct.etags[path] = etag
}
```

## Sync Coordinator

The coordinator processes change events through the RAG pipeline.

```go
import (
    "sync"

    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/splitter"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
)

// SyncCoordinator orchestrates document sync workflow.
type SyncCoordinator struct {
    loader      loader.DocumentLoader       // the "cloudstorage" loader
    buckets     map[string]CloudLoaderConfig // bucket name -> config
    splitter    splitter.TextSplitter
    embedder    embedding.Embedder
    vectorStore vectorstore.VectorStore
    tracker     *ChangeTracker
    mu          sync.Mutex
    chunkIDs    map[string][]string // object key -> chunk IDs currently indexed (guarded by mu)
}

// ProcessChange handles a single change event.
func (c *SyncCoordinator) ProcessChange(ctx context.Context, event ChangeEvent) error {
    cfg, exists := c.buckets[event.Bucket]
    if !exists {
        return fmt.Errorf("unknown bucket: %s", event.Bucket)
    }

    // VectorStore has Add and Delete (no upsert), so remove the old
    // chunks of a changed or deleted object first.
    c.mu.Lock()
    old := c.chunkIDs[event.Path]
    delete(c.chunkIDs, event.Path)
    c.mu.Unlock()
    if len(old) > 0 {
        if err := c.vectorStore.Delete(ctx, old); err != nil {
            return fmt.Errorf("delete old chunks: %w", err)
        }
    }
    if event.Action == "deleted" {
        return nil
    }

    // Load document
    url, err := ObjectURL(cfg, event.Path)
    if err != nil {
        return err
    }
    docs, err := c.loader.Load(ctx, url)
    if err != nil {
        return fmt.Errorf("load document: %w", err)
    }

    // Split documents
    chunks, err := c.splitter.SplitDocuments(ctx, docs)
    if err != nil {
        return fmt.Errorf("split documents: %w", err)
    }

    // Generate embeddings; give each chunk a stable ID
    texts := make([]string, len(chunks))
    ids := make([]string, len(chunks))
    for i := range chunks {
        chunks[i].ID = fmt.Sprintf("%s#%d", event.Path, i)
        ids[i] = chunks[i].ID
        texts[i] = chunks[i].Content
    }

    embeddings, err := c.embedder.Embed(ctx, texts)
    if err != nil {
        return fmt.Errorf("generate embeddings: %w", err)
    }

    if err := c.vectorStore.Add(ctx, chunks, embeddings); err != nil {
        return fmt.Errorf("add to vector store: %w", err)
    }
    c.mu.Lock()
    c.chunkIDs[event.Path] = ids
    c.mu.Unlock()

    // Update change tracker
    c.tracker.UpdateETag(event.Path, event.ETag)

    return nil
}
```

## Batch Processing

Process multiple changes efficiently with controlled concurrency.

```go
// ProcessBatch handles multiple changes in parallel.
func (c *SyncCoordinator) ProcessBatch(ctx context.Context, events []ChangeEvent) error {
    var wg sync.WaitGroup
    semaphore := make(chan struct{}, 10) // Limit concurrency
    errors := make(chan error, len(events))

    for _, event := range events {
        wg.Add(1)
        semaphore <- struct{}{}

        go func(e ChangeEvent) {
            defer wg.Done()
            defer func() { <-semaphore }()

            if err := c.ProcessChange(ctx, e); err != nil {
                errors <- err
            }
        }(event)
    }

    wg.Wait()
    close(errors)

    // Collect errors
    var errs []error
    for err := range errors {
        errs = append(errs, err)
    }

    if len(errs) > 0 {
        return fmt.Errorf("batch processing failed: %v", errs)
    }

    return nil
}
```

## Production Considerations

### Webhook Reliability

Webhooks provide real-time updates but can be unreliable. Implement polling as a fallback mechanism to catch missed webhook events. Verify webhook signatures to prevent spoofing.

### Incremental Processing

Track ETags for all files to detect actual changes. This avoids reprocessing unchanged files, reducing API calls and processing time. Store ETags in a persistent database for durability across restarts.

### Rate Limiting

Cloud storage APIs have rate limits. Implement exponential backoff and request queuing to stay within limits. Batch operations where possible to reduce API call count.

### Error Handling

Handle transient failures with retries. Log failed sync operations for manual review. Consider dead letter queues for persistent failures.

### Observability

Track sync metrics with OpenTelemetry:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/metric"
)

func (c *SyncCoordinator) recordMetrics(ctx context.Context, bucket string, duration time.Duration, syncErr error) error {
    // Create instruments once at startup in real code
    meter := otel.Meter("cloud-sync")
    attrs := metric.WithAttributes(attribute.String("bucket", bucket))

    if syncErr != nil {
        counter, err := meter.Int64Counter("sync_errors_total")
        if err != nil {
            return err
        }
        counter.Add(ctx, 1, attrs)
        return nil
    }

    counter, err := meter.Int64Counter("sync_success_total")
    if err != nil {
        return err
    }
    counter.Add(ctx, 1, attrs)

    histogram, err := meter.Float64Histogram("sync_duration_seconds")
    if err != nil {
        return err
    }
    histogram.Record(ctx, duration.Seconds(), attrs)
    return nil
}
```

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Sync Latency (minutes) | 4320 | 5 | 99.9% reduction |
| Data Freshness | 80% | 99.2% | 24% improvement |
| Manual Interventions/month | 50+ | 0 | 100% reduction |
| Documents Synced/day | 500 | 6200 | 1140% increase |
| Sync Accuracy | 95% | 99.5% | 4.7% improvement |

## Related Resources

- [RAG Pipeline Guide](/docs/guides/rag-pipeline/) for document processing patterns
- [Legacy Archive Ingestion](/docs/guides/legacy-archive/) for batch ingestion patterns
- [Enterprise RAG](/docs/guides/enterprise-rag/) for complete RAG system setup
