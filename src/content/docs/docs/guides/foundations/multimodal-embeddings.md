---
title: Multimodal Embeddings Tutorial
description: "Build cross-modal search in Go with Beluga AI: embed text with the embedding providers and bring images into the same vector space through vision-LLM descriptions."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, multimodal embeddings, vector space, cross-modal search, embedding providers"
---

Traditional search is limited to text matching. Multimodal embeddings project text, images, and other modalities into the same high-dimensional vector space, enabling cross-modal retrieval: search a product catalog of images using text queries, or find documents that relate to an uploaded photo. This shared representation works because embedding models learn to map semantically similar content to nearby points in vector space, regardless of the original modality.

Beluga AI's `embedding.Embedder` is text-in, vector-out: none of the bundled embedding providers accept image input today. This tutorial builds the text side of a cross-modal pipeline and shows the common way to bring images into the same space: ask a vision-capable LLM to describe each image, then embed the description with the same embedder you use for text.

## What You Will Build

An embedding pipeline that embeds text documents and image descriptions into one vector space, then computes similarity scores between a text query and both kinds of content.

## Prerequisites

- A Google Cloud API key with the Generative Language API enabled (or another embedding provider)
- A vision-capable chat model (for example OpenAI `gpt-4o`) for the image-description step
- Understanding of the [RAG pipeline](/docs/recipes/rag/)

## The Embedder Interface

Beluga AI's embedding interface in the `rag/embedding` package has a batch method, a single-text convenience method, and a way to read the vector size. The interface follows the same registry pattern as LLM providers, so embedding providers are created with `embedding.New()` and discovered with `embedding.List()`.

```go
type Embedder interface {
    Embed(ctx context.Context, texts []string) ([][]float32, error)
    EmbedSingle(ctx context.Context, text string) ([]float32, error)
    Dimensions() int
}
```

The same methods embed documents and queries. If your model expects different prefixes for the two (some retrieval-tuned models want `query: ` and `passage: `), add the prefix to the text before you call `Embed`.

## Step 1: Initialize the Embedding Provider

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/google"
)

func main() {
    ctx := context.Background()

    embedder, err := embedding.New("google", config.ProviderConfig{
        APIKey: os.Getenv("GOOGLE_API_KEY"),
        Model:  "text-embedding-004",
    })
    if err != nil {
        log.Fatalf("create embedder: %v", err)
    }

    // Embed text documents
    texts := []string{
        "A golden retriever playing in a park",
        "Financial quarterly report Q3 2025",
        "Kubernetes deployment configuration",
    }

    vectors, err := embedder.Embed(ctx, texts)
    if err != nil {
        log.Fatalf("embed documents: %v", err)
    }

    for i, v := range vectors {
        fmt.Printf("Text %d: %d dimensions\n", i, len(v))
    }
}
```

## Step 2: Embed Queries

Use `EmbedSingle` for a search query. Embed queries with the same model you used for the documents, so both land in the same vector space.

```go
queryVector, err := embedder.EmbedSingle(ctx, "dog playing outside")
if err != nil {
    log.Fatalf("embed query: %v", err)
}

fmt.Printf("Query vector: %d dimensions\n", len(queryVector))
```

## Step 3: Batch Processing for Performance

Embedding one document at a time is slow because each call incurs HTTP round-trip overhead. Processing documents in batches amortizes this overhead and takes advantage of the embedding model's ability to process multiple inputs in a single forward pass. The batch size should balance throughput against API rate limits and memory constraints.

```go
func batchEmbed(ctx context.Context, embedder embedding.Embedder, texts []string, batchSize int) ([][]float32, error) {
    var allVectors [][]float32

    for i := 0; i < len(texts); i += batchSize {
        end := i + batchSize
        if end > len(texts) {
            end = len(texts)
        }

        batch := texts[i:end]
        vectors, err := embedder.Embed(ctx, batch)
        if err != nil {
            return nil, fmt.Errorf("batch %d-%d: %w", i, end, err)
        }
        allVectors = append(allVectors, vectors...)
    }

    return allVectors, nil
}
```

## Step 4: Bring Images into the Same Space

Because the embedder only takes text, describe each image with a vision-capable chat model and embed the description. A `schema.HumanMessage` can carry a `schema.ImagePart` alongside the text instruction.

```go
func describeImage(ctx context.Context, model llm.ChatModel, img []byte, mimeType string) (string, error) {
    msg := &schema.HumanMessage{Parts: []schema.ContentPart{
        schema.TextPart{Text: "Describe this image in one or two sentences for search indexing."},
        schema.ImagePart{Data: img, MimeType: mimeType},
    }}

    resp, err := model.Generate(ctx, []schema.Message{msg})
    if err != nil {
        return "", fmt.Errorf("describe image: %w", err)
    }
    return resp.Text(), nil
}
```

Embed the returned description with `embedder.Embed` together with your text documents, and store a reference to the original image in the document metadata so search results can point back to it.

## Step 5: Compute Cosine Similarity

Compare vectors to find semantic matches. Cosine similarity measures the angle between two vectors, producing a value between -1 and 1 where 1 means identical direction (maximum similarity). This metric is preferred over Euclidean distance for embeddings because it is invariant to vector magnitude — two vectors pointing in the same direction are similar regardless of their length.

```go
import "math"

func cosineSimilarity(a, b []float32) float64 {
    if len(a) != len(b) {
        return 0
    }

    var dot, normA, normB float64
    for i := range a {
        dot += float64(a[i]) * float64(b[i])
        normA += float64(a[i]) * float64(a[i])
        normB += float64(b[i]) * float64(b[i])
    }

    if normA == 0 || normB == 0 {
        return 0
    }
    return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}
```

Usage:

```go
// Compare query to each document
for i, docVec := range vectors {
    score := cosineSimilarity(queryVector, docVec)
    fmt.Printf("Similarity to doc %d: %.4f\n", i, score)
}
```

## Step 6: Choosing the Right Model

| Model | Dimensions | Best For |
|:---|:---|:---|
| OpenAI text-embedding-3-large | 3072 | High accuracy, general purpose |
| OpenAI text-embedding-3-small | 1536 | Cost-effective, general purpose |
| Google text-embedding-004 | 768 | Cross-language |
| Ollama nomic-embed-text | 768 | Local, privacy-sensitive, free |

Always use the same model for both document indexing and query embedding. Mixing models produces incompatible vector spaces because each model learns a different mapping from text to vectors.

## Verification

1. Embed a list of 100 texts using batch processing — measure the time versus sequential embedding.
2. Compute similarity between semantically related texts — verify scores above 0.7.
3. Compute similarity between unrelated texts — verify lower scores.

## Next Steps

- [Fine-tuning Embedding Strategies](/docs/guides/foundations/finetuning-embeddings) — Optimize retrieval performance
- [In-memory Vector Store](/docs/guides/foundations/inmemory-vectorstore) — Store and search embeddings locally
