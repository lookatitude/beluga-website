---
title: "MongoDB Atlas Vector Store Provider"
description: "Vector search with MongoDB Atlas in Beluga AI. Unified document and vector database with Atlas Vector Search and metadata filtering in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "MongoDB Atlas, vector search, Atlas Vector Search, document database, metadata filtering, Go, Beluga AI"
---

:::note[Migrating from the Data API]
Earlier releases spoke the Atlas Data API, which MongoDB retired on 30 September 2025. The provider now uses the official MongoDB Go driver (`go.mongodb.org/mongo-driver/v2`), so `BaseURL` must be a MongoDB connection string (`mongodb://` or `mongodb+srv://`). A Data API URL is rejected with a `core.ErrInvalidInput` error, and `WithAPIKey` and `WithHTTPClient` are deprecated no-ops; put credentials in the connection string instead.
:::

The MongoDB Atlas provider implements the `vectorstore.VectorStore` interface using MongoDB Atlas Vector Search through the official Go driver. Search runs the `$vectorSearch` aggregation stage with metadata filtering; the similarity function (cosine, dot product, or Euclidean) is set by the Atlas vector index definition.

Choose MongoDB Atlas when your application already uses MongoDB and you want to add vector search alongside your existing document data. Atlas Vector Search integrates with MongoDB's aggregation pipeline, allowing you to combine vector similarity with traditional document queries without managing a separate vector database.

## Installation

```bash
go get github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/mongodb
```

## Quick Start

```go
package main

import (
    "context"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/mongodb"
)

func main() {
    store, err := vectorstore.New("mongodb", config.ProviderConfig{
        BaseURL: os.Getenv("MONGODB_URI"), // mongodb+srv://user:pass@cluster0.example.mongodb.net
        Options: map[string]any{
            "database":   "my_db",
            "collection": "documents",
            "index":      "vector_index",
        },
    })
    if err != nil {
        log.Fatal(err)
    }

    ctx := context.Background()

    docs := []schema.Document{
        {ID: "doc1", Content: "Go is a statically typed language", Metadata: map[string]any{"lang": "en"}},
    }
    embeddings := [][]float32{make([]float32, 1536)}

    err = store.Add(ctx, docs, embeddings)
    if err != nil {
        log.Fatal(err)
    }
}
```

## Configuration

| Parameter | Type | Default | Description |
|---|---|---|---|
| `BaseURL` | `string` | (required) | MongoDB connection string (`mongodb://` or `mongodb+srv://`), including credentials |
| `Options["database"]` | `string` | `beluga` | Database name |
| `Options["collection"]` | `string` | `documents` | Collection name |
| `Options["index"]` | `string` | `vector_index` | Atlas Vector Search index name |

## Prerequisites

1. Create a MongoDB Atlas cluster and a database user
2. Copy the cluster's connection string (`mongodb+srv://...`)
3. Create an Atlas Vector Search index on the `embedding` field, and declare every `metadata.<key>` you filter on as a filter field:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "metadata.lang"
    }
  ]
}
```

## Direct Construction

```go
import (
    mongostore "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/mongodb"
)

store := mongostore.New(
    os.Getenv("MONGODB_URI"),
    mongostore.WithDatabase("production"),
    mongostore.WithCollection("docs"),
    mongostore.WithIndex("prod_vector_index"),
)
defer store.Close(ctx)
```

`New` connects lazily. If the URI is not a MongoDB connection string, every method on the returned store fails with `core.ErrInvalidInput`; use `NewFromConfig` to get that error at construction time. Stores created by `New` or `NewFromConfig` own their client, so call `Close` to disconnect it.

## Metadata Filtering

Metadata filters are applied to the `metadata` field path:

```go
results, err := store.Search(ctx, queryVec, 10,
    vectorstore.WithFilter(map[string]any{
        "lang": "en",
    }),
)
```

This translates to a `$vectorSearch` filter on `metadata.lang`. Filter keys must be plain identifiers and values must be scalars, and each key must be declared as a filter field in the vector index.

## Search with Threshold

```go
results, err := store.Search(ctx, queryVec, 10,
    vectorstore.WithThreshold(0.7),
)
for _, doc := range results {
    fmt.Printf("ID: %s, Score: %.4f, Content: %s\n", doc.ID, doc.Score, doc.Content)
}
```

## Document Structure

Documents are stored with the following structure:

```json
{
  "_id": "doc1",
  "content": "Document text content",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "lang": "en",
    "category": "technical"
  }
}
```

## Existing Client

To reuse a `*mongo.Client` you already manage, wrap a collection handle with `NewWithCollection`. The caller owns the client, `WithDatabase` and `WithCollection` are ignored, and `Close` is a no-op:

```go
import (
    "go.mongodb.org/mongo-driver/v2/mongo"
    "go.mongodb.org/mongo-driver/v2/mongo/options"

    mongostore "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/mongodb"
)

client, err := mongo.Connect(options.Client().ApplyURI(os.Getenv("MONGODB_URI")))
if err != nil {
    log.Fatal(err)
}
defer client.Disconnect(ctx)

store := mongostore.NewWithCollection(
    client.Database("my_db").Collection("documents"),
    mongostore.WithIndex("vector_index"),
)
```
