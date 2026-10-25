---
title: Audio-Visual Product Search
description: "Enable customers to search for products using images and voice descriptions with multimodal AI. Bridge the search intent gap."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "multimodal product search, visual search AI, voice product search, image search e-commerce, Beluga AI, Go, retail AI"
---

Customers often know what they want but cannot describe it in search keywords. A shopper holding a competitor's product wants "something like this" — a query that text search cannot answer. Voice descriptions ("I'm looking for a blue ceramic vase, about 12 inches tall") contain rich detail that keyword matching ignores. E-commerce platforms lose sales at these moments because the gap between how customers think about products and how search systems index them is too wide.

Multimodal search bridges this gap by understanding products the way customers do — through visual appearance, spoken descriptions, and contextual text. The LLM extracts semantic features from images and audio, converts them to a unified text description, and vector similarity search finds products that match the meaning rather than the exact words.

## Solution Architecture

Beluga AI's `schema.ContentPart` interface supports text, images, and audio in a single message, letting the LLM process all modalities together. The system uses a vision-capable model (GPT-4o, Claude 3) to extract a semantic description from the multimodal query, then embeds that description and performs vector similarity search against the product catalog. This two-stage approach (LLM description + vector search) separates understanding from matching, making each stage independently improvable.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ User Query   │───▶│ Multimodal   │───▶│ Semantic     │
│ (Image +     │    │ LLM          │    │ Features     │
│  Voice +     │    │ (GPT-4o,     │    │ Extraction   │
│  Text)       │    │  Claude)     │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                                │
                                                ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Ranked       │◀───│ Relevance    │◀───│ Similarity   │
│ Results      │    │ Scoring      │    │ Search       │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Multimodal Query Processing

Process images, audio, and text in a unified query:

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
	"github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
)

// ProductSearch handles multimodal product search
type ProductSearch struct {
    model      llm.ChatModel
    vectorDB   VectorStore
    products   ProductCatalog
}

func NewProductSearch(ctx context.Context) (*ProductSearch, error) {
    // Use a multimodal model (GPT-4o, Claude 3, etc.)
    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",  // Vision-capable model
    })
    if err != nil {
        return nil, err
    }

    return &ProductSearch{
        model:    model,
        vectorDB: NewVectorStore(),
        products: LoadProductCatalog(),
    }, nil
}

// SearchMultimodal searches using image, audio, and text
func (s *ProductSearch) SearchMultimodal(ctx context.Context, imageData []byte, audioData []byte, textQuery string) ([]Product, error) {
    // Build multimodal message
    parts := []schema.ContentPart{}

    // Add text instruction
    if textQuery != "" {
        parts = append(parts, schema.TextPart{
            Text: fmt.Sprintf("Find products matching this description: %s", textQuery),
        })
    } else {
        parts = append(parts, schema.TextPart{
            Text: "Describe this product in detail, focusing on visual characteristics that would help find similar items.",
        })
    }

    // Add image if provided
    if len(imageData) > 0 {
        parts = append(parts, schema.ImagePart{
            Data:     imageData,
            MimeType: "image/jpeg",
        })
    }

    // Add audio if provided (for voice description)
    if len(audioData) > 0 {
        parts = append(parts, schema.AudioPart{
            Data:   audioData,
            Format: "mp3",
        })
    }

    msgs := []schema.Message{
        &schema.HumanMessage{Parts: parts},
    }

    // Get product description from LLM
    resp, err := s.model.Generate(ctx, msgs)
    if err != nil {
        return nil, fmt.Errorf("multimodal generation failed: %w", err)
    }

    description := resp.Text()

    // Use description for similarity search
    return s.findSimilarProducts(ctx, description)
}
```

## Similarity-Based Product Matching

Use vector similarity to find matching products:

```go
func (s *ProductSearch) findSimilarProducts(ctx context.Context, description string) ([]Product, error) {
    // Generate embedding for the description
    embedding, err := s.vectorDB.Embed(ctx, description)
    if err != nil {
        return nil, err
    }

    // Search vector database for similar products
    results, err := s.vectorDB.Search(ctx, embedding, 20)
    if err != nil {
        return nil, err
    }

    // Retrieve full product details
    products := make([]Product, 0, len(results))
    for _, result := range results {
        product, err := s.products.Get(result.ProductID)
        if err != nil {
            continue
        }
        product.RelevanceScore = result.Score
        products = append(products, product)
    }

    return products, nil
}
```

## Voice Query Support

Process voice queries with speech-to-text:

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/voice/stt"

    _ "github.com/lookatitude/beluga-ai/v2/voice/stt/providers/whisper" // OpenAI Whisper API
)

// SearchByVoice searches using voice input
func (s *ProductSearch) SearchByVoice(ctx context.Context, audioData []byte) ([]Product, error) {
    // Transcribe audio to text
    sttModel, err := stt.New("whisper", stt.Config{
        Extra: map[string]any{"api_key": os.Getenv("OPENAI_API_KEY")},
    })
    if err != nil {
        return nil, err
    }

    transcript, err := sttModel.Transcribe(ctx, audioData)
    if err != nil {
        return nil, fmt.Errorf("transcription failed: %w", err)
    }

    // Search using transcribed text
    return s.SearchMultimodal(ctx, nil, nil, transcript)
}
```

## Visual Search with Image Upload

Handle image-only search queries:

```go
// SearchByImage searches using image input
func (s *ProductSearch) SearchByImage(ctx context.Context, imageData []byte) ([]Product, error) {
    return s.SearchMultimodal(ctx, imageData, nil, "")
}

// Example HTTP handler
func (h *Handler) HandleImageSearch(w http.ResponseWriter, r *http.Request) {
    // Parse image upload
    file, _, err := r.FormFile("image")
    if err != nil {
        http.Error(w, "failed to read image", http.StatusBadRequest)
        return
    }
    defer file.Close()

    imageData, err := io.ReadAll(file)
    if err != nil {
        http.Error(w, "failed to read image data", http.StatusInternalServerError)
        return
    }

    // Search
    products, err := h.search.SearchByImage(r.Context(), imageData)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }

    // Return results
    w.Header().Set("Content-Type", "application/json")
    if err := json.NewEncoder(w).Encode(products); err != nil {
        http.Error(w, "failed to encode results", http.StatusInternalServerError)
    }
}
```

## Production Considerations

### Caching Multimodal Embeddings

Cache image and audio embeddings to reduce LLM API calls:

```go
type EmbeddingCache struct {
    cache *redis.Client
}

func (c *EmbeddingCache) GetOrCompute(ctx context.Context, key string, computeFn func() ([]float64, error)) ([]float64, error) {
    // Try cache first
    cached, err := c.cache.Get(ctx, key).Result()
    if err == nil {
        var embedding []float64
        if err := json.Unmarshal([]byte(cached), &embedding); err == nil {
            return embedding, nil
        }
        // Corrupt cache entry: fall through and recompute.
    }

    // Compute and cache
    embedding, err := computeFn()
    if err != nil {
        return nil, err
    }

    data, err := json.Marshal(embedding)
    if err != nil {
        return nil, err
    }
    if err := c.cache.Set(ctx, key, data, 24*time.Hour).Err(); err != nil {
        return nil, fmt.Errorf("cache embedding: %w", err)
    }

    return embedding, nil
}
```

### Result Ranking

Combine multiple signals for better relevance:

```go
func (s *ProductSearch) rankResults(products []Product, query string) []Product {
    for i := range products {
        score := 0.0

        // Vector similarity (0-1)
        score += products[i].RelevanceScore * 0.5

        // Popularity (0-1)
        score += products[i].PopularityScore * 0.2

        // Price relevance (0-1)
        score += computePriceRelevance(products[i].Price, query) * 0.1

        // Recency (0-1)
        score += computeRecencyScore(products[i].CreatedAt) * 0.2

        products[i].FinalScore = score
    }

    sort.Slice(products, func(i, j int) bool {
        return products[i].FinalScore > products[j].FinalScore
    })

    return products
}
```

### Rate Limiting and Cost Control

Limit expensive multimodal queries. Create one `resilience.RateLimiter` and share it across requests (a limiter built per call never throttles anything):

```go
import "github.com/lookatitude/beluga-ai/v2/resilience"

// Shared by every request: 10 queries per minute, at most 3 in flight.
var searchLimiter = resilience.NewRateLimiter(resilience.ProviderLimits{
    RPM:           10,
    MaxConcurrent: 3,
})

func (s *ProductSearch) SearchWithRateLimit(ctx context.Context, imageData []byte, audioData []byte, textQuery string) ([]Product, error) {
    // Allow blocks until a request slot is free or ctx is cancelled.
    if err := searchLimiter.Allow(ctx); err != nil {
        return nil, fmt.Errorf("rate limit: %w", err)
    }
    defer searchLimiter.Release()

    return s.SearchMultimodal(ctx, imageData, audioData, textQuery)
}
```

## Related Resources

- [Security Camera Analysis](/docs/guides/security-camera/) for video analysis patterns
- [Enterprise RAG](/docs/guides/enterprise-rag/) for semantic search setup
- [LLM Integration Guide](/docs/guides/llm/) for multimodal model configuration
