---
title: Pinecone Serverless Vector Store
description: "Integrate Pinecone Serverless with Beluga AI for fully managed, auto-scaling vector storage with pay-per-use pricing in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Pinecone Serverless, vector store, Beluga AI, managed vector database, auto-scaling, similarity search Go, serverless AI"
---

Traditional vector databases require provisioning pods, managing replicas, and predicting capacity. Pinecone Serverless removes this operational complexity entirely -- indexes scale automatically based on usage, and you pay only for the operations you perform. This makes it well suited for applications with unpredictable traffic patterns or teams that want to focus on application logic rather than infrastructure management.

Choose Pinecone Serverless when you want zero-ops vector storage, pay-per-use pricing, and do not need the advanced filtering capabilities of databases like Qdrant.

## Overview

Beluga AI's `VectorStore` interface abstracts vector database operations behind a unified API. The Pinecone provider registers via `init()` and supports add, search, and delete operations against Pinecone Serverless indexes.

Key capabilities:
- Auto-scaling serverless indexes with no pod management
- Pay-per-use pricing based on operations and storage
- Metadata filtering for scoped similarity search
- OpenTelemetry instrumentation for observability

## Prerequisites

- Go 1.26 or later
- Beluga AI framework installed
- Pinecone account with API key ([pinecone.io](https://www.pinecone.io))
- A serverless index created in the Pinecone console

## Installation

Install the Beluga AI module:

```bash
go get github.com/lookatitude/beluga-ai/v2
```

### Pinecone Setup

1. Sign in to the [Pinecone console](https://app.pinecone.io)
2. Create a new index with type **Serverless**
3. Set the dimension to match your embedding model (e.g., 1536 for OpenAI `text-embedding-3-small`)
4. Note your API key and the index **host** URL shown on the index page (for example `https://my-index-abc123.svc.us-east-1-aws.pinecone.io`)

Set the required environment variables:

```bash
export PINECONE_API_KEY="your-api-key"
export PINECONE_INDEX_HOST="https://my-index-abc123.svc.us-east-1-aws.pinecone.io"
export OPENAI_API_KEY="your-openai-key"
```

## Configuration

The Pinecone provider is configured with a `config.ProviderConfig`:

| Field | Description | Default | Required |
|--------|-------------|---------|----------|
| `APIKey` | Pinecone API key | - | Yes |
| `BaseURL` | Index host URL from the Pinecone console | - | Yes |
| `Options["namespace"]` | Namespace for document isolation | default namespace | No |

The index dimension is fixed when you create the index in Pinecone; it must match your embedding model.

## Usage

### Basic Vector Store

Create a Pinecone vector store, add documents, and run similarity search:

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
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pinecone"
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

    // Create a Pinecone vector store
    store, err := vectorstore.New("pinecone", config.ProviderConfig{
        APIKey:  os.Getenv("PINECONE_API_KEY"),
        BaseURL: os.Getenv("PINECONE_INDEX_HOST"),
        Options: map[string]any{"namespace": "docs"},
    })
    if err != nil {
        log.Fatalf("Failed to create store: %v", err)
    }

    // Embed and add documents
    docs := []schema.Document{
        {ID: "doc1", Content: "Machine learning is transforming industries.", Metadata: map[string]any{"category": "tech"}},
        {ID: "doc2", Content: "Go is known for its simplicity and performance.", Metadata: map[string]any{"category": "programming"}},
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
    queryVec, err := embedder.EmbedSingle(ctx, "programming languages")
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

Use metadata filters to scope searches to specific document categories:

```go
results, err := store.Search(ctx, queryVec, 5,
    vectorstore.WithFilter(map[string]any{"category": "tech"}),
)
if err != nil {
    log.Fatalf("Filtered search failed: %v", err)
}
```

### Serverless Index Behavior

Serverless indexes differ from pod-based indexes:

- **Auto-scaling**: No pod type or replica configuration required
- **Pay-per-use**: Charges based on read/write operations and storage
- **Cold start**: Infrequently accessed indexes may have higher initial latency

No additional configuration is needed beyond the standard options above.

## Advanced Topics

### OpenTelemetry Instrumentation

Add tracing to Pinecone operations for production observability:

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
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pinecone"
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

    tracer := otel.Tracer("beluga.vectorstore.pinecone")
    ctx, span := tracer.Start(ctx, "pinecone.ingest",
        trace.WithAttributes(
            attribute.String("provider", "pinecone"),
            attribute.String("index_host", os.Getenv("PINECONE_INDEX_HOST")),
        ),
    )
    defer span.End()

    store, err := vectorstore.New("pinecone", config.ProviderConfig{
        APIKey:  os.Getenv("PINECONE_API_KEY"),
        BaseURL: os.Getenv("PINECONE_INDEX_HOST"),
        Options: map[string]any{"namespace": "docs"},
    })
    if err != nil {
        span.RecordError(err)
        log.Fatalf("Failed to create store: %v", err)
    }

    docs := []schema.Document{
        {ID: "doc3", Content: "AI is revolutionizing technology.", Metadata: map[string]any{"category": "ai", "source": "doc1"}},
        {ID: "doc4", Content: "Serverless computing scales automatically.", Metadata: map[string]any{"category": "cloud", "source": "doc2"}},
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

When using Pinecone Serverless in production:

- **Batch operations**: Group document additions into batches to reduce per-operation costs.
- **Rate limiting**: Implement backoff and retry logic for API rate limits. Beluga's `resilience` package provides built-in retry and circuit breaker support.
- **Index dimension limits**: Verify that your embedding model dimension matches the index configuration exactly.
- **Monitoring**: Track usage and costs in the Pinecone dashboard. Combine with OpenTelemetry traces for end-to-end visibility.
- **Backup**: Pinecone Serverless does not provide built-in backup. Maintain a source-of-truth data pipeline for re-indexing.

## Troubleshooting

### Index Not Found

The index name does not exist or is misspelled. Verify available indexes:

```bash
curl -X GET "https://api.pinecone.io/indexes" \
  -H "Api-Key: $PINECONE_API_KEY"
```

### Invalid API Key

The API key does not belong to the project that owns the index. Confirm that `PINECONE_API_KEY` and `PINECONE_INDEX_HOST` come from the same Pinecone project.

### Dimension Mismatch

The embedding vector dimension does not match the index configuration. Ensure the embedder's output dimension matches the dimension set when the index was created (e.g., 1536 for `text-embedding-3-small`).

## Related Resources

- [Vector Stores Overview](/docs/reference/providers/vectorstore/) -- All supported vector store providers
- [Qdrant Cloud Integration](/docs/guides/production/integrations/qdrant-cloud) -- Managed Qdrant clusters
- [RAG Tutorial](/docs/guides/capabilities/rag/rag-pipeline/) -- Build end-to-end RAG applications
