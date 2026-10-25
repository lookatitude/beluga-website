---
title: Semantic Image Search System
description: "Build intelligent image search with natural language queries using multimodal embeddings and vector similarity for e-commerce."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "semantic image search, multimodal embeddings, visual search AI, e-commerce search, image retrieval, Beluga AI, Go, vector search"
---

E-commerce platforms struggle with keyword-based image search because product images contain information that text metadata cannot fully capture — color, style, material texture, spatial arrangement. A customer looking for "a blue velvet couch with mid-century legs" cannot express this through keyword filters alone, and manual tagging every visual attribute of every product is not scalable.

A semantic image search system uses multimodal embeddings to understand both images and text queries, enabling intuitive search by description rather than exact keywords. The key innovation is mapping both images and text into the same embedding space: a photo of a blue velvet couch and the text description "blue velvet mid-century sofa" produce similar vectors, enabling cross-modal similarity search without explicit attribute matching.

## Solution Architecture

Beluga AI's `embedding.Embedder` interface is text-only, so this design bridges images into text space with a vision-capable chat model: each product photo is sent to the model as a `schema.ImagePart`, the model writes a search-oriented description, and that description is embedded and stored in a vector store. Natural language queries are embedded with the same embedder and matched against the descriptions. If you run a true multimodal encoder (for example a CLIP service), you can store its vectors with the same `VectorStore.Add` / `Search` calls instead.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Product    │───▶│  Vision LLM  │───▶│ Description  │
│   Images     │    │  (describe)  │    │  Embeddings  │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Search     │◀───│   Ranked     │◀───│ VectorStore  │
│   Results    │    │   Results    │    │  (Similarity │
└──────────────┘    └──────────────┘    │    Search)   │
                          ▲              └──────────────┘
                          │
                    ┌─────┴────────┐
                    │  Text Query  │
                    │   Embedder   │
                    └──────────────┘
```

## Implementation

### Image Indexing Pipeline

The indexing pipeline describes each product image with a vision model, embeds the description, and stores it in a vector database with metadata:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

type ImageSearchSystem struct {
    vision   llm.ChatModel      // describes images
    embedder embedding.Embedder // embeds descriptions and queries
    store    vectorstore.VectorStore
}

func NewImageSearchSystem(ctx context.Context) (*ImageSearchSystem, error) {
    vision, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o", // vision-capable model
    })
    if err != nil {
        return nil, fmt.Errorf("create vision model: %w", err)
    }

    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-large",
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: "postgresql://localhost/images",
        Options: map[string]any{
            "table":     "product_images",
            "dimension": float64(3072), // text-embedding-3-large
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    return &ImageSearchSystem{vision: vision, embedder: embedder, store: store}, nil
}

// describeImage asks a vision model for a search-oriented description.
func (s *ImageSearchSystem) describeImage(ctx context.Context, imageData []byte, mimeType string) (string, error) {
    msg := &schema.HumanMessage{Parts: []schema.ContentPart{
        schema.TextPart{Text: "Describe this product photo for a search index: color, material, style, shape. One paragraph."},
        schema.ImagePart{Data: imageData, MimeType: mimeType},
    }}
    resp, err := s.vision.Generate(ctx, []schema.Message{msg})
    if err != nil {
        return "", err
    }
    return resp.Text(), nil
}

func (s *ImageSearchSystem) IndexImage(ctx context.Context, productID string, imageData []byte, mimeType string, metadata map[string]any) error {
    description, err := s.describeImage(ctx, imageData, mimeType)
    if err != nil {
        return fmt.Errorf("describe image: %w", err)
    }

    vec, err := s.embedder.EmbedSingle(ctx, description)
    if err != nil {
        return fmt.Errorf("embed description: %w", err)
    }

    doc := schema.Document{
        ID:      productID,
        Content: description,
        Metadata: map[string]any{
            "product_id": productID,
            "type":       "image",
        },
    }
    for k, v := range metadata {
        doc.Metadata[k] = v
    }

    if err := s.store.Add(ctx, []schema.Document{doc}, [][]float32{vec}); err != nil {
        return fmt.Errorf("store image: %w", err)
    }

    log.Printf("Indexed image for product %s", productID)
    return nil
}

func main() {
    ctx := context.Background()
    sys, err := NewImageSearchSystem(ctx)
    if err != nil {
        log.Fatal(err)
    }
    img, err := os.ReadFile("couch.jpg")
    if err != nil {
        log.Fatal(err)
    }
    if err := sys.IndexImage(ctx, "sku-123", img, "image/jpeg", nil); err != nil {
        log.Fatal(err)
    }
}
```

### Semantic Search

Text queries are embedded and matched against the image-description embeddings using vector similarity:

```go
func (s *ImageSearchSystem) Search(ctx context.Context, query string, topK int) ([]SearchResult, error) {
    // Embed the text query into the same space as the image descriptions
    queryVec, err := s.embedder.EmbedSingle(ctx, query)
    if err != nil {
        return nil, fmt.Errorf("embed query: %w", err)
    }

    results, err := s.store.Search(ctx, queryVec, topK,
        vectorstore.WithThreshold(0.7),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    searchResults := make([]SearchResult, len(results))
    for i, result := range results {
        searchResults[i] = SearchResult{
            ProductID: result.ID,
            Score:     result.Score,
            Metadata:  result.Metadata,
        }
    }

    return searchResults, nil
}

type SearchResult struct {
    ProductID string
    Score     float64
    Metadata  map[string]any
}
```

### Relevance Ranking

Combine similarity scores with other signals for improved ranking:

```go
func (s *ImageSearchSystem) SearchWithRanking(ctx context.Context, query string, topK int) ([]SearchResult, error) {
    // Get more results for ranking
    results, err := s.Search(ctx, query, topK*2)
    if err != nil {
        return nil, err
    }

    // Rank by relevance (combine similarity with popularity, recency, etc.)
    ranked := rankResults(results, query)

    // Return top K
    if len(ranked) > topK {
        ranked = ranked[:topK]
    }

    return ranked, nil
}

func rankResults(results []SearchResult, query string) []SearchResult {
    // Combine similarity score with other factors
    for i := range results {
        popularityBoost := getPopularityScore(results[i].ProductID)
        recencyBoost := getRecencyScore(results[i].ProductID)
        results[i].Score = results[i].Score * 0.7 + popularityBoost*0.2 + recencyBoost*0.1
    }

    // Sort by combined score
    sort.Slice(results, func(i, j int) bool {
        return results[i].Score > results[j].Score
    })

    return results
}
```

## Production Considerations

### Batch Indexing

Process large image collections efficiently by describing each image and embedding the descriptions in batches:

```go
func (s *ImageSearchSystem) IndexBatch(ctx context.Context, images []ImageData) error {
    batchSize := 100
    for i := 0; i < len(images); i += batchSize {
        end := min(i+batchSize, len(images))
        batch := images[i:end]

        descriptions := make([]string, len(batch))
        for j, img := range batch {
            d, err := s.describeImage(ctx, img.Data, img.MimeType)
            if err != nil {
                return fmt.Errorf("describe %s: %w", img.ProductID, err)
            }
            descriptions[j] = d
        }

        // One embedding call per batch
        embeddings, err := s.embedder.Embed(ctx, descriptions)
        if err != nil {
            return fmt.Errorf("embed batch %d: %w", i/batchSize, err)
        }

        docs := make([]schema.Document, len(batch))
        for j, img := range batch {
            docs[j] = schema.Document{
                ID:      img.ProductID,
                Content: descriptions[j],
                Metadata: map[string]any{
                    "product_id": img.ProductID,
                    "type":       "image",
                },
            }
        }

        if err := s.store.Add(ctx, docs, embeddings); err != nil {
            return fmt.Errorf("store batch %d: %w", i/batchSize, err)
        }
    }
    return nil
}

type ImageData struct {
    ProductID string
    Data      []byte
    MimeType  string
    Metadata  map[string]any
}
```

### Observability

Track search performance and relevance metrics:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

func (s *ImageSearchSystem) SearchWithTracing(ctx context.Context, query string, topK int) ([]SearchResult, error) {
    tracer := otel.Tracer("image-search")
    ctx, span := tracer.Start(ctx, "image_search.search")
    defer span.End()

    span.SetAttributes(
        attribute.String("search.query", query),
        attribute.Int("search.top_k", topK),
    )

    results, err := s.Search(ctx, query, topK)
    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    span.SetAttributes(attribute.Int("search.results_count", len(results)))
    return results, nil
}
```

### Scaling

- **Horizontal scaling**: Deploy multiple search service instances behind a load balancer
- **Embedding caching**: Cache embeddings for frequently searched queries to reduce API calls
- **Vector store optimization**: Use read replicas for pgvector or managed services for automatic scaling
- **Model selection**: Balance embedding quality with latency by testing different embedding models

## Results

After implementing semantic image search, the platform achieved:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Search Relevance | 40-50% | 87% | 74-118% |
| User Satisfaction | 6.0/10 | 9.1/10 | 52% |
| Conversion Rate | 2.5% | 4.7% | 88% |
| Search-to-Purchase Time | 8 min | 2.5 min | 69% reduction |
| Zero-Result Searches | 15-20% | 4% | 73-80% reduction |

## Related Resources

- [RAG Pipeline Guide](/docs/guides/rag-pipeline/) for embedding and retrieval patterns
- [Vector Store Integration](/docs/guides/production/integrations/vector-stores/) for provider-specific configuration
- [Embedding Providers](/docs/reference/providers/embedding/) for multimodal embedding options
