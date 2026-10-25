---
title: Semantic Search and Recommendations
description: "Build intelligent search and recommendation engines with vector embeddings and similarity search. Meaning-based retrieval at scale."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "semantic search, vector embeddings, recommendation engine, similarity search, personalized search, Beluga AI, Go, e-commerce"
---

Traditional keyword-based search fails to understand user intent and semantic relationships. A user searching for "affordable running shoes" will miss products described as "budget-friendly jogging footwear" because the terms do not overlap, even though the intent is identical. Similarly, recommendation systems based solely on purchase history and metadata (category, price range) miss deeper content relationships — they cannot understand that a customer who bought a hiking backpack might want trail-running shoes.

Beluga AI provides a complete semantic search and recommendation pipeline using vector embeddings for meaning-based retrieval at scale. Vector embeddings map both queries and content into a shared semantic space where similarity is measured by meaning rather than term overlap. This approach handles synonyms, paraphrases, and conceptual relationships without explicit synonym dictionaries or ontology engineering.

## Solution Architecture

Beluga AI's RAG pipeline provides everything needed for semantic search: embedders convert text to vectors, vector stores index embeddings for fast similarity search, and retrievers implement advanced strategies. The same infrastructure powers both search and personalized recommendations — the difference is only in what gets embedded (content for search, user profiles for recommendations) and how queries are constructed.

```mermaid
graph TB
    A[User Query] --> B[Query Embedding]
    B --> C[Vector Store<br>Similarity Search]
    C --> D[Retriever<br>Rank & Filter]
    D --> E[Search Results]

    F[User History] --> G[Recommendation<br>Engine]
    G --> C
    G --> E

    H[Content<br>Indexing] --> I[Document<br>Embedding]
    I --> C
```

## Content Indexing Pipeline

Index content by generating embeddings and storing them in a vector database:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

type ContentItem struct {
    ID       string
    Text     string
    Type     string
    Category string
}

type SearchService struct {
    embedder    embedding.Embedder
    vectorStore vectorstore.VectorStore
}

func NewSearchService(ctx context.Context) (*SearchService, error) {
    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-small",
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    // pgvector reads the connection string from BaseURL.
    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: os.Getenv("POSTGRES_CONNECTION_STRING"),
        Options: map[string]any{
            "table":     "content_embeddings",
            "dimension": float64(1536),
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    return &SearchService{
        embedder:    embedder,
        vectorStore: store,
    }, nil
}

func (s *SearchService) IndexContent(ctx context.Context, items []ContentItem) error {
    texts := make([]string, len(items))
    for i, item := range items {
        texts[i] = item.Text
    }

    // Generate embeddings in one batch call
    embeddings, err := s.embedder.Embed(ctx, texts)
    if err != nil {
        return fmt.Errorf("embed documents: %w", err)
    }

    // Create documents with metadata
    docs := make([]schema.Document, len(items))
    for i, item := range items {
        docs[i] = schema.Document{
            ID:      item.ID,
            Content: item.Text,
            Metadata: map[string]any{
                "type":     item.Type,
                "category": item.Category,
            },
        }
    }

    // Store documents and their embeddings
    if err := s.vectorStore.Add(ctx, docs, embeddings); err != nil {
        return fmt.Errorf("store documents: %w", err)
    }

    log.Printf("Indexed %d items", len(items))
    return nil
}

func main() {
    ctx := context.Background()
    svc, err := NewSearchService(ctx)
    if err != nil {
        log.Fatal(err)
    }
    err = svc.IndexContent(ctx, []ContentItem{
        {ID: "shoe-1", Text: "Budget-friendly jogging footwear", Type: "product", Category: "shoes"},
    })
    if err != nil {
        log.Fatal(err)
    }
}
```

## Semantic Search

Perform meaning-based search by embedding the query and finding similar documents:

```go
type SearchResult struct {
    ID      string
    Content string
    Score   float64
    Type    string
}

func (s *SearchService) Search(ctx context.Context, query string, k int) ([]SearchResult, error) {
    // Generate query embedding
    queryEmbedding, err := s.embedder.EmbedSingle(ctx, query)
    if err != nil {
        return nil, fmt.Errorf("embed query: %w", err)
    }

    // Retrieve similar documents; each result carries its similarity in Score
    docs, err := s.vectorStore.Search(ctx, queryEmbedding, k,
        vectorstore.WithThreshold(0.7),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    // Convert to search results
    results := make([]SearchResult, len(docs))
    for i, doc := range docs {
        docType, _ := doc.Metadata["type"].(string)
        results[i] = SearchResult{
            ID:      doc.ID,
            Content: doc.Content,
            Score:   doc.Score,
            Type:    docType,
        }
    }

    return results, nil
}
```

## Hybrid Search with Retriever

Use Beluga AI's hybrid retriever to combine vector similarity with BM25 keyword matching. `retriever.NewHybridRetriever` fuses both result lists with Reciprocal Rank Fusion. Beluga AI does not bundle a BM25 index, so you pass in your own keyword backend through the `retriever.BM25Searcher` interface:

```go
import (
    "github.com/lookatitude/beluga-ai/v2/rag/retriever"
)

// bm25 is your keyword index (Elasticsearch, OpenSearch, Typesense, ...)
// wrapped to satisfy retriever.BM25Searcher:
//   Search(ctx context.Context, query string, k int) ([]schema.Document, error)
func (s *SearchService) HybridSearch(ctx context.Context, bm25 retriever.BM25Searcher, query string, k int) ([]schema.Document, error) {
    ret := retriever.NewHybridRetriever(s.vectorStore, s.embedder, bm25,
        retriever.WithHybridRRFK(60), // RRF constant; 60 is the standard value
    )

    docs, err := ret.Retrieve(ctx, query, retriever.WithTopK(k))
    if err != nil {
        return nil, fmt.Errorf("retrieve: %w", err)
    }

    return docs, nil
}
```

## Personalized Recommendations

Build a recommendation engine using user interaction history and item similarity:

```go
type Recommendation struct {
    ItemID string
    Score  float64
    Reason string
}

func (s *SearchService) GetRecommendations(ctx context.Context, userID string, count int) ([]Recommendation, error) {
    // Get the user's interaction history (application-specific)
    history, err := getUserHistory(userID)
    if err != nil {
        return nil, err
    }
    if len(history.LikedTexts) == 0 {
        return nil, nil
    }

    // Build a preference vector by averaging embeddings of liked items
    liked, err := s.embedder.Embed(ctx, history.LikedTexts)
    if err != nil {
        return nil, fmt.Errorf("embed liked items: %w", err)
    }
    preferenceVector := make([]float32, s.embedder.Dimensions())
    for _, vec := range liked {
        for i := range preferenceVector {
            preferenceVector[i] += vec[i]
        }
    }
    for i := range preferenceVector {
        preferenceVector[i] /= float32(len(liked))
    }

    // Find similar items
    docs, err := s.vectorStore.Search(ctx, preferenceVector, count*2,
        vectorstore.WithThreshold(0.6),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    // Filter out items the user has already seen
    recommendations := []Recommendation{}
    for _, doc := range docs {
        if contains(history.SeenItems, doc.ID) {
            continue
        }

        recommendations = append(recommendations, Recommendation{
            ItemID: doc.ID,
            Score:  doc.Score,
            Reason: "Similar to items you liked",
        })

        if len(recommendations) >= count {
            break
        }
    }

    return recommendations, nil
}
```

## Multi-Modal Search

Extend search to images by storing image vectors in the same vector store. Beluga AI's `embedding.Embedder` is text-only, so image embeddings (for example from a CLIP model) are produced outside the framework and then searched with `VectorStore.Search`:

```go
// embedImage calls your multimodal embedding model (for example a CLIP
// service you host). Beluga AI's embedding.Embedder interface is text-only,
// so image vectors come from outside the framework.
func (s *SearchService) ImageSearch(ctx context.Context, imageURL string, k int) ([]SearchResult, error) {
    imageEmbedding, err := embedImage(ctx, imageURL)
    if err != nil {
        return nil, fmt.Errorf("embed image: %w", err)
    }

    // The vector store does not care where a vector came from, as long as
    // the dimension matches the index.
    docs, err := s.vectorStore.Search(ctx, imageEmbedding, k)
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    results := make([]SearchResult, len(docs))
    for i, doc := range docs {
        results[i] = SearchResult{
            ID:      doc.ID,
            Content: doc.Content,
            Score:   doc.Score,
        }
    }

    return results, nil
}
```

## Production Considerations

### Batch Indexing

Process large document collections efficiently:

```go
func (s *SearchService) IndexBatch(ctx context.Context, items []ContentItem) error {
    batchSize := 100
    for i := 0; i < len(items); i += batchSize {
        end := min(i+batchSize, len(items))
        batch := items[i:end]

        if err := s.IndexContent(ctx, batch); err != nil {
            return fmt.Errorf("index batch %d: %w", i/batchSize, err)
        }

        log.Printf("Indexed batch %d/%d", (i/batchSize)+1, (len(items)+batchSize-1)/batchSize)
    }
    return nil
}
```

### Observability

Track search performance and quality:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

func (s *SearchService) SearchWithTracing(ctx context.Context, query string, k int) ([]SearchResult, error) {
    tracer := otel.Tracer("search-service")
    ctx, span := tracer.Start(ctx, "search.query")
    defer span.End()

    span.SetAttributes(
        attribute.String("search.query", query),
        attribute.Int("search.top_k", k),
    )

    start := time.Now()
    results, err := s.Search(ctx, query, k)
    duration := time.Since(start)

    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    span.SetAttributes(
        attribute.Int("search.results_count", len(results)),
        attribute.Float64("search.duration_ms", float64(duration.Milliseconds())),
    )

    return results, nil
}
```

### Scaling

- **Horizontal scaling**: Deploy multiple search service instances. Each instance can handle independent queries.
- **Vector store scaling**: Use pgvector with read replicas or managed services like Pinecone for automatic scaling.
- **Embedding caching**: Cache embeddings for frequently queried terms to reduce API calls.
- **Index optimization**: Tune HNSW parameters for your document count and query patterns.

### Configuration

```yaml
search:
  embeddings:
    provider: "openai"
    model: "text-embedding-3-small"
    batch_size: 100

  vectorstore:
    provider: "pgvector"
    connection_string: "${POSTGRES_CONNECTION_STRING}"
    table_name: "content_embeddings"
    dimensions: 1536

  retrieval:
    default_k: 10
    score_threshold: 0.7
    timeout: 30s

  recommendations:
    max_recommendations: 10
    similarity_threshold: 0.6
```

## Related Resources

- [RAG Pipeline Guide](/docs/guides/rag-pipeline/) for complete RAG setup
- [Enterprise RAG](/docs/guides/enterprise-rag/) for production RAG patterns
- [Vector Store Integration](/docs/guides/production/integrations/vector-stores/) for provider-specific configuration
