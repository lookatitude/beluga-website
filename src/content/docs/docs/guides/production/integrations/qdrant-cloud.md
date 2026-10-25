---
title: Qdrant Cloud Vector Store
description: "Integrate Qdrant Cloud managed clusters with Beluga AI for high-performance vector storage, filtering, and similarity search in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Qdrant Cloud, vector database, Beluga AI, managed vector store, similarity search, HNSW index, Go vector search"
---

Self-hosted vector databases require capacity planning, index tuning, and operational maintenance. Qdrant Cloud eliminates this by providing fully managed clusters with automatic scaling, backups, and monitoring. Qdrant is built specifically for vector search (unlike general-purpose databases with vector extensions), which means it provides advanced features like payload-based filtering, multi-vector support, and quantization out of the box.

Choose Qdrant Cloud when you need a dedicated vector database with rich filtering capabilities, want managed infrastructure with no operational overhead, or need HNSW-based approximate nearest neighbor search that scales with your data.

## Overview

Beluga AI's `VectorStore` interface abstracts vector database operations behind a unified API. The Qdrant provider registers via `init()` and supports add, search, and delete operations against Qdrant Cloud clusters. Qdrant offers HNSW-based approximate nearest neighbor search with rich metadata filtering.

Key capabilities:
- Managed clusters with configurable sizing and replication
- HNSW indexing for fast approximate nearest neighbor search
- Rich payload-based metadata filtering
- Collections auto-created on first use
- OpenTelemetry instrumentation for observability

## Prerequisites

- Go 1.26 or later
- Beluga AI framework installed
- Qdrant Cloud account ([cloud.qdrant.io](https://cloud.qdrant.io))
- A Qdrant cluster with its URL and API key

## Installation

Install the Beluga AI module:

```bash
go get github.com/lookatitude/beluga-ai/v2
```

### Qdrant Cloud Setup

1. Sign in to the [Qdrant Cloud console](https://cloud.qdrant.io)
2. Create a new cluster
3. Note the cluster URL (e.g., `https://xyz.us-east-1-0.aws.cloud.qdrant.io`) and API key

Set the required environment variables:

```bash
export QDRANT_URL="https://your-cluster.qdrant.io"
export QDRANT_API_KEY="your-api-key"
export OPENAI_API_KEY="your-openai-key"
```

## Configuration

The Qdrant provider can be built directly with `qdrant.New(baseURL, opts...)` or through the registry with `vectorstore.New("qdrant", config.ProviderConfig{...})`:

| Option (`qdrant.New`) | `ProviderConfig` field | Description | Default | Required |
|--------|--------|-------------|---------|----------|
| `baseURL` argument | `BaseURL` | Qdrant cluster URL | - | Yes |
| `qdrant.WithAPIKey` | `APIKey` | Qdrant API key | - | Yes (for cloud) |
| `qdrant.WithCollection` | `Options["collection"]` | Collection name | `documents` | No |
| `qdrant.WithDimension` | `Options["dimension"]` (float64) | Vector dimension used by `EnsureCollection` | `1536` | No |

## Usage

### Basic Vector Store

Create a Qdrant vector store, add documents, and run similarity search:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/qdrant"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func main() {
    ctx := context.Background()

    // Create an OpenAI embedder
    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-small",
    })
    if err != nil {
        log.Fatalf("Failed to create embedder: %v", err)
    }

    // Create a Qdrant vector store
    store := qdrant.New(os.Getenv("QDRANT_URL"),
        qdrant.WithAPIKey(os.Getenv("QDRANT_API_KEY")),
        qdrant.WithCollection("my-documents"),
        qdrant.WithDimension(1536),
    )

    // Create the collection if it does not exist yet.
    if err := store.EnsureCollection(ctx); err != nil {
        log.Fatalf("Failed to ensure collection: %v", err)
    }

    // Embed and add documents
    docs := []schema.Document{
        {ID: "7f0c1d9e-1b2a-4c3d-8e4f-000000000001", Content: "Machine learning is a subset of AI.", Metadata: map[string]any{"topic": "ml"}},
        {ID: "7f0c1d9e-1b2a-4c3d-8e4f-000000000002", Content: "Go is a programming language.", Metadata: map[string]any{"topic": "programming"}},
    }

    texts := make([]string, len(docs))
    for i, d := range docs {
        texts[i] = d.Content
    }
    embeddings, err := embedder.Embed(ctx, texts)
    if err != nil {
        log.Fatalf("Failed to embed documents: %v", err)
    }

    err = store.Add(ctx, docs, embeddings)
    if err != nil {
        log.Fatalf("Failed to add documents: %v", err)
    }

    fmt.Printf("Added %d documents\n", len(docs))

    // Search by query
    queryVec, err := embedder.EmbedSingle(ctx, "artificial intelligence")
    if err != nil {
        log.Fatalf("Failed to embed query: %v", err)
    }

    results, err := store.Search(ctx, queryVec, 5)
    if err != nil {
        log.Fatalf("Search failed: %v", err)
    }

    fmt.Printf("Found %d results\n", len(results))
    for i, result := range results {
        fmt.Printf("  %d. %s\n", i+1, result.Content)
    }
}
```

### Metadata Filtering

Use payload-based metadata filters to scope searches:

```go
results, err := store.Search(ctx, queryVec, 5,
    vectorstore.WithFilter(map[string]any{"topic": "ml"}),
)
if err != nil {
    log.Fatalf("Filtered search failed: %v", err)
}
```

### Collection Management

The Beluga Qdrant store does not create collections implicitly: call `store.EnsureCollection(ctx)` (cosine distance, size from `qdrant.WithDimension`) before the first `Add`, as in the example above. Qdrant point IDs must be UUIDs or unsigned integers, so set `schema.Document.ID` accordingly. To create a collection with other parameters, use the Qdrant Go client directly:

```go
import (
    "github.com/qdrant/go-client/qdrant"
)

func createCollection(ctx context.Context, client *qdrant.Client, name string, dim int) error {
    _, err := client.CreateCollection(ctx, &qdrant.CreateCollection{
        CollectionName: name,
        VectorsConfig: &qdrant.VectorsConfig{
            Config: &qdrant.VectorsConfig_Params{
                Params: &qdrant.VectorParams{
                    Size:     uint64(dim),
                    Distance: qdrant.Distance_Cosine,
                },
            },
        },
    })
    return err
}
```

## Advanced Topics

### OpenTelemetry Instrumentation

Add tracing to Qdrant operations for production observability:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"
    "time"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/qdrant"
    "github.com/lookatitude/beluga-ai/v2/schema"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

func main() {
    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()

    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-small",
    })
    if err != nil {
        log.Fatalf("Failed to create embedder: %v", err)
    }

    tracer := otel.Tracer("beluga.vectorstore.qdrant")
    ctx, span := tracer.Start(ctx, "qdrant.ingest",
        trace.WithAttributes(
            attribute.String("provider", "qdrant"),
            attribute.String("collection", "my-documents"),
        ),
    )
    defer span.End()

    store := qdrant.New(os.Getenv("QDRANT_URL"),
        qdrant.WithAPIKey(os.Getenv("QDRANT_API_KEY")),
        qdrant.WithCollection("my-documents"),
        qdrant.WithDimension(1536),
    )

    // Create the collection if it does not exist yet.
    if err := store.EnsureCollection(ctx); err != nil {
        span.RecordError(err)
        log.Fatalf("Failed to ensure collection: %v", err)
    }

    docs := []schema.Document{
        {ID: "7f0c1d9e-1b2a-4c3d-8e4f-000000000003", Content: "Machine learning enables computers to learn.", Metadata: map[string]any{"topic": "ml", "source": "doc1"}},
        {ID: "7f0c1d9e-1b2a-4c3d-8e4f-000000000004", Content: "Go is statically typed and compiled.", Metadata: map[string]any{"topic": "programming", "source": "doc2"}},
    }

    texts := make([]string, len(docs))
    for i, d := range docs {
        texts[i] = d.Content
    }
    embeddings, err := embedder.Embed(ctx, texts)
    if err != nil {
        span.RecordError(err)
        log.Fatalf("Failed to embed documents: %v", err)
    }

    err = store.Add(ctx, docs, embeddings)
    if err != nil {
        span.RecordError(err)
        log.Fatalf("Failed to add documents: %v", err)
    }

    span.SetAttributes(attribute.Int("documents_added", len(docs)))
    fmt.Printf("Successfully added %d documents\n", len(docs))
}
```

### Production Considerations

When using Qdrant Cloud in production:

- **Cluster sizing**: Select a cluster size appropriate for your document volume and query throughput. Monitor resource utilization in the Qdrant Cloud dashboard.
- **HNSW tuning**: Configure HNSW index parameters (`m`, `ef_construct`) for your accuracy/performance tradeoff. Higher values improve recall at the cost of memory and indexing speed.
- **Timeouts**: The store uses `http.DefaultClient`, which has no timeout. Pass a client with a timeout via `qdrant.WithHTTPClient(&http.Client{Timeout: 30 * time.Second})`, and bound each call with a context deadline.
- **Retry logic**: Use Beluga's `resilience` package for automatic retry with backoff on transient failures.
- **Monitoring**: Combine Qdrant Cloud metrics with OpenTelemetry traces for end-to-end observability.

## Troubleshooting

### Connection Refused

The cluster URL is invalid or the cluster is not accessible. Verify connectivity:

```bash
curl https://your-cluster.qdrant.io/collections
```

### Unauthorized

The API key is invalid or missing. Confirm that `QDRANT_API_KEY` matches the key generated in the Qdrant Cloud console.

### Collection Not Found

Collections are not created automatically. Call `store.EnsureCollection(ctx)` before the first add, or create the collection with the Qdrant Go client as shown in the [Collection Management](#collection-management) section.

## Related Resources

- [Vector Stores Overview](/docs/guides/production/integrations/vector-stores) -- All supported vector store providers
- [Pinecone Serverless Integration](/docs/guides/production/integrations/pinecone-serverless) -- Serverless vector storage
- [RAG Tutorial](/docs/guides/rag-pipeline) -- Build end-to-end RAG applications
