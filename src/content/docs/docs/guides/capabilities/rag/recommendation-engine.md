---
title: AI Recommendation Engine
description: "Build semantic product recommendations with vector similarity to solve cold-start problems. Content-based recommendations from day one."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "recommendation engine AI, semantic recommendations, cold-start solution, vector similarity, e-commerce AI, Beluga AI, Go"
---

E-commerce platforms relying on traditional collaborative filtering face cold-start problems: new products have no purchase history to build recommendations from, and new users have no behavior data to match against. Collaborative filtering answers "users who bought X also bought Y" but cannot explain why or recommend based on product attributes. A new running shoe has zero purchase history, so collaborative filtering cannot recommend it until enough users have bought it — a circular problem.

A semantic recommendation engine uses vector embeddings to represent products and user preferences, enabling content-based recommendations that work from day one. By embedding product descriptions into vector space, the system understands semantic similarity ("lightweight trail runner" is similar to "minimalist hiking shoe") without any purchase data. This approach is complementary to collaborative filtering — the two signals can be combined for hybrid recommendations that leverage both content understanding and behavioral patterns.

## Solution Architecture

Beluga AI's vector store package provides similarity search at scale. The recommendation engine embeds product descriptions and user preferences into vector space, uses similarity search to find relevant products, and applies hybrid ranking that combines content-based and collaborative signals for optimal accuracy.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Product    │───▶│   Product    │───▶│ Vector Store │
│   Catalog    │    │   Embedder   │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
┌──────────────┐    ┌──────────────┐           │
│     User     │───▶│  User Pref   │           │
│   Behavior   │    │   Engine     │           │
└──────────────┘    └──────┬───────┘           │
                           │                   │
                           ▼                   ▼
                    ┌──────────────────────────┐
                    │   Similarity Search      │
                    │   + Hybrid Ranker        │
                    └──────┬───────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Personalized │
                    │Recommendations│
                    └──────────────┘
```

## Product Embedding

Generate semantic vectors for product catalog:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

type RecommendationEngine struct {
    embedder    embedding.Embedder
    vectorStore vectorstore.VectorStore
}

func NewRecommendationEngine(ctx context.Context) (*RecommendationEngine, error) {
    embedder, err := embedding.New("openai", config.ProviderConfig{
        Model:  "text-embedding-3-large",
        APIKey: os.Getenv("OPENAI_API_KEY"),
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: os.Getenv("DATABASE_URL"),
        Options: map[string]any{
            "table":     "products",
            "dimension": float64(3072),
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    return &RecommendationEngine{
        embedder:    embedder,
        vectorStore: store,
    }, nil
}

type ProductMetadata struct {
    ProductID   string
    Name        string
    Description string
    Category    string
    Price       float64
    Brand       string
    Tags        []string
}

// productDescription builds the rich text that gets embedded for a product.
func productDescription(product ProductMetadata) string {
    return fmt.Sprintf(
        "Product: %s\nBrand: %s\nCategory: %s\nDescription: %s\nTags: %s",
        product.Name,
        product.Brand,
        product.Category,
        product.Description,
        strings.Join(product.Tags, ", "),
    )
}

func (r *RecommendationEngine) IndexProduct(ctx context.Context, product ProductMetadata) error {
    description := productDescription(product)

    // Generate embedding
    vec, err := r.embedder.EmbedSingle(ctx, description)
    if err != nil {
        return fmt.Errorf("embed product: %w", err)
    }

    // Store in vector database
    doc := schema.Document{
        ID:      product.ProductID,
        Content: description,
        Metadata: map[string]any{
            "product_id": product.ProductID,
            "name":       product.Name,
            "category":   product.Category,
            "price":      product.Price,
            "brand":      product.Brand,
            "tags":       product.Tags,
        },
    }

    if err := r.vectorStore.Add(ctx, []schema.Document{doc}, [][]float32{vec}); err != nil {
        return fmt.Errorf("store product: %w", err)
    }

    return nil
}

func main() {
    ctx := context.Background()
    engine, err := NewRecommendationEngine(ctx)
    if err != nil {
        log.Fatal(err)
    }
    err = engine.IndexProduct(ctx, ProductMetadata{
        ProductID: "sku-1", Name: "Trail runner", Category: "shoes", Price: 120, Brand: "Acme",
    })
    if err != nil {
        log.Fatal(err)
    }
}
```

## User Preference Learning

Build user preference vectors from behavior:

```go
type UserPreferenceEngine struct {
    embedder embedding.Embedder
}

func NewUserPreferenceEngine(embedder embedding.Embedder) *UserPreferenceEngine {
    return &UserPreferenceEngine{embedder: embedder}
}

type UserBehavior struct {
    ViewedProducts    []string
    PurchasedProducts []string
    SearchQueries     []string
    ClickedCategories []string
}

func (u *UserPreferenceEngine) GetUserVector(ctx context.Context, userID string) ([]float32, error) {
    // Fetch user behavior
    behavior, err := u.fetchUserBehavior(ctx, userID)
    if err != nil {
        return nil, err
    }

    if len(behavior.PurchasedProducts) == 0 && len(behavior.ViewedProducts) == 0 {
        return nil, fmt.Errorf("insufficient user data for %s", userID)
    }

    // Build user preference description from behavior
    var preferences strings.Builder

    if len(behavior.SearchQueries) > 0 {
        preferences.WriteString("User searches: ")
        preferences.WriteString(strings.Join(behavior.SearchQueries, ", "))
        preferences.WriteString(". ")
    }

    if len(behavior.ClickedCategories) > 0 {
        preferences.WriteString("Interested in categories: ")
        preferences.WriteString(strings.Join(behavior.ClickedCategories, ", "))
        preferences.WriteString(". ")
    }

    if len(behavior.PurchasedProducts) > 0 {
        preferences.WriteString("Previously purchased: ")
        for _, productID := range behavior.PurchasedProducts {
            product := u.getProductInfo(ctx, productID)
            preferences.WriteString(fmt.Sprintf("%s, ", product.Name))
        }
    }

    // Generate preference embedding
    vec, err := u.embedder.EmbedSingle(ctx, preferences.String())
    if err != nil {
        return nil, fmt.Errorf("embed preferences: %w", err)
    }

    return vec, nil
}

func (u *UserPreferenceEngine) fetchUserBehavior(ctx context.Context, userID string) (*UserBehavior, error) {
    // Fetch from database or analytics system
    // Implementation depends on your data storage
    return &UserBehavior{}, nil
}

func (u *UserPreferenceEngine) getProductInfo(ctx context.Context, productID string) *ProductMetadata {
    // Fetch product details from your catalog
    return &ProductMetadata{}
}
```

## Personalized Recommendations

Generate recommendations using vector similarity:

```go
type Recommendation struct {
    ProductID string
    Name      string
    Category  string
    Price     float64
    Score     float64
    Reason    string
}

func (r *RecommendationEngine) GetRecommendations(ctx context.Context, userID string, limit int) ([]Recommendation, error) {
    // Get user preference vector
    userPrefs := NewUserPreferenceEngine(r.embedder)
    userVector, err := userPrefs.GetUserVector(ctx, userID)
    if err != nil {
        // Cold-start: use popular products or category-based recommendations
        return r.getColdStartRecommendations(ctx, limit)
    }

    // Search for similar products; fetch extra candidates for ranking
    results, err := r.vectorStore.Search(ctx, userVector, limit*2,
        vectorstore.WithThreshold(0.6),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    // Rank and filter
    return r.rankRecommendations(ctx, results, userID, limit), nil
}

// toRecommendation reads the metadata written by IndexProduct.
func toRecommendation(doc schema.Document, reason string) Recommendation {
    name, _ := doc.Metadata["name"].(string)
    category, _ := doc.Metadata["category"].(string)
    price, _ := doc.Metadata["price"].(float64)
    return Recommendation{
        ProductID: doc.ID,
        Name:      name,
        Category:  category,
        Price:     price,
        Score:     doc.Score, // similarity from the vector store
        Reason:    reason,
    }
}

func (r *RecommendationEngine) rankRecommendations(ctx context.Context, docs []schema.Document, userID string, limit int) []Recommendation {
    recommendations := make([]Recommendation, 0, len(docs))

    // Apply business logic and filters
    for _, doc := range docs {
        // Skip already purchased products
        if r.hasUserPurchased(ctx, userID, doc.ID) {
            continue
        }

        // Apply diversity, price range, and inventory filters here

        recommendations = append(recommendations, toRecommendation(doc, r.generateReason(doc)))

        if len(recommendations) >= limit {
            break
        }
    }

    return recommendations
}

func (r *RecommendationEngine) generateReason(doc schema.Document) string {
    // Generate human-readable reason for recommendation
    return fmt.Sprintf("Based on your interest in %v", doc.Metadata["category"])
}

func (r *RecommendationEngine) hasUserPurchased(ctx context.Context, userID, productID string) bool {
    // Check purchase history
    return false
}
```

## Cold-Start Handling

Recommend to new users using content similarity:

```go
func (r *RecommendationEngine) getColdStartRecommendations(ctx context.Context, limit int) ([]Recommendation, error) {
    // Strategy 1: Popular products
    // Strategy 2: New arrivals
    // Strategy 3: Trending in category

    // For this example, use popular products from your catalog
    popularProducts, err := r.getPopularProducts(ctx, limit)
    if err != nil {
        return nil, err
    }

    recommendations := make([]Recommendation, len(popularProducts))
    for i, product := range popularProducts {
        recommendations[i] = Recommendation{
            ProductID: product.ProductID,
            Name:      product.Name,
            Category:  product.Category,
            Price:     product.Price,
            Score:     1.0,
            Reason:    "Popular choice",
        }
    }

    return recommendations, nil
}

func (r *RecommendationEngine) GetSimilarProducts(ctx context.Context, product ProductMetadata, limit int) ([]Recommendation, error) {
    // VectorStore has no lookup-by-ID, so re-embed the product description
    // (or cache product vectors in your own store).
    vec, err := r.embedder.EmbedSingle(ctx, productDescription(product))
    if err != nil {
        return nil, fmt.Errorf("embed product: %w", err)
    }

    // Find similar products; +1 because the product itself will match
    results, err := r.vectorStore.Search(ctx, vec, limit+1,
        vectorstore.WithThreshold(0.7),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    recommendations := make([]Recommendation, 0, limit)
    for _, result := range results {
        // Skip the product itself
        if result.ID == product.ProductID {
            continue
        }

        recommendations = append(recommendations, toRecommendation(result, "Similar product"))

        if len(recommendations) >= limit {
            break
        }
    }

    return recommendations, nil
}
```

## Hybrid Ranking

Combine multiple signals for better recommendations:

```go
import (
    "context"
    "sort"

    "github.com/lookatitude/beluga-ai/v2/schema"
)

type HybridRanker struct {
    weights map[string]float64
}

func NewHybridRanker() *HybridRanker {
    return &HybridRanker{
        weights: map[string]float64{
            "semantic_similarity": 0.4,
            "popularity":          0.2,
            "user_affinity":       0.2,
            "freshness":           0.1,
            "price_match":         0.1,
        },
    }
}

func (h *HybridRanker) Rank(ctx context.Context, docs []schema.Document, userID string) []schema.Document {
    scored := make([]scoredDoc, len(docs))

    for i, doc := range docs {
        score := 0.0

        // Semantic similarity (Score is set by the vector store search)
        score += doc.Score * h.weights["semantic_similarity"]

        // Popularity (view count, purchase count)
        score += h.calculatePopularity(doc) * h.weights["popularity"]

        // User affinity (category match, brand preference)
        score += h.calculateUserAffinity(ctx, userID, doc) * h.weights["user_affinity"]

        // Freshness (newer products ranked higher)
        score += h.calculateFreshness(doc) * h.weights["freshness"]

        // Price match (user's typical price range)
        score += h.calculatePriceMatch(ctx, userID, doc) * h.weights["price_match"]

        scored[i] = scoredDoc{doc: doc, score: score}
    }

    // Sort by combined score
    sort.Slice(scored, func(i, j int) bool {
        return scored[i].score > scored[j].score
    })

    result := make([]schema.Document, len(scored))
    for i, s := range scored {
        result[i] = s.doc
        result[i].Score = s.score
    }

    return result
}

type scoredDoc struct {
    doc   schema.Document
    score float64
}

func (h *HybridRanker) calculatePopularity(doc schema.Document) float64 {
    // Implementation: combine view count, purchase count, rating
    return 0.5
}

func (h *HybridRanker) calculateUserAffinity(ctx context.Context, userID string, doc schema.Document) float64 {
    // Implementation: check category preferences, brand loyalty
    return 0.5
}

func (h *HybridRanker) calculateFreshness(doc schema.Document) float64 {
    // Implementation: time since product creation
    return 0.5
}

func (h *HybridRanker) calculatePriceMatch(ctx context.Context, userID string, doc schema.Document) float64 {
    // Implementation: compare to user's typical price range
    return 0.5
}
```

## Production Considerations

### Observability

Track recommendation quality and user engagement:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/metric"
)

var (
    tracer = otel.Tracer("recommendations")
    meter  = otel.Meter("recommendations")
)

func (r *RecommendationEngine) GetRecommendationsWithTracking(ctx context.Context, userID string, limit int) ([]Recommendation, error) {
    ctx, span := tracer.Start(ctx, "recommendation.get")
    defer span.End()

    span.SetAttributes(
        attribute.String("user.id", userID),
        attribute.Int("limit", limit),
    )

    start := time.Now()
    recommendations, err := r.GetRecommendations(ctx, userID, limit)
    duration := time.Since(start)

    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    span.SetAttributes(
        attribute.Int("recommendations.count", len(recommendations)),
        attribute.Float64("duration.ms", float64(duration.Milliseconds())),
    )

    // Create instruments once at startup in real code
    latency, err := meter.Int64Histogram("recommendation.duration", metric.WithUnit("ms"))
    if err == nil {
        latency.Record(ctx, duration.Milliseconds())
    }

    return recommendations, nil
}
```

### Caching

Cache recommendations for frequent users:

```go
import "github.com/lookatitude/beluga-ai/v2/cache"

type CachedRecommendationEngine struct {
    RecommendationEngine
    cache cache.Cache
}

func (c *CachedRecommendationEngine) GetRecommendations(ctx context.Context, userID string, limit int) ([]Recommendation, error) {
    cacheKey := fmt.Sprintf("rec:%s:%d", userID, limit)

    // Check cache
    cached, ok, err := c.cache.Get(ctx, cacheKey)
    if err != nil {
        return nil, fmt.Errorf("cache get: %w", err)
    }
    if ok {
        if recs, isRecs := cached.([]Recommendation); isRecs {
            return recs, nil
        }
    }

    // Generate recommendations
    recommendations, err := c.RecommendationEngine.GetRecommendations(ctx, userID, limit)
    if err != nil {
        return nil, err
    }

    // Cache for 5 minutes
    if err := c.cache.Set(ctx, cacheKey, recommendations, 5*time.Minute); err != nil {
        return nil, fmt.Errorf("cache set: %w", err)
    }

    return recommendations, nil
}
```

### A/B Testing

Track recommendation strategy performance:

```go
type ABTestingEngine struct {
    RecommendationEngine
    experiments map[string]RecommendationStrategy
}

type RecommendationStrategy interface {
    GetRecommendations(ctx context.Context, userID string, limit int) ([]Recommendation, error)
}

func (a *ABTestingEngine) GetRecommendations(ctx context.Context, userID string, limit int) ([]Recommendation, error) {
    // Assign user to experiment group
    variant := a.getVariant(userID)

    strategy := a.experiments[variant]
    recommendations, err := strategy.GetRecommendations(ctx, userID, limit)
    if err != nil {
        return nil, err
    }

    // Track which variant was served
    a.trackVariant(ctx, userID, variant)

    return recommendations, nil
}

func (a *ABTestingEngine) getVariant(userID string) string {
    // Hash-based assignment for consistent experience
    hash := hashUserID(userID)
    if hash%2 == 0 {
        return "semantic"
    }
    return "hybrid"
}
```

### Batch Updates

Update product embeddings efficiently:

```go
func (r *RecommendationEngine) IndexBatch(ctx context.Context, products []ProductMetadata) error {
    batchSize := 100

    for i := 0; i < len(products); i += batchSize {
        end := min(i+batchSize, len(products))
        batch := products[i:end]

        // Generate descriptions
        descriptions := make([]string, len(batch))
        for j, product := range batch {
            descriptions[j] = productDescription(product)
        }

        // One embedding call per batch
        embeddings, err := r.embedder.Embed(ctx, descriptions)
        if err != nil {
            return err
        }

        // Create documents
        docs := make([]schema.Document, len(batch))
        for j, product := range batch {
            docs[j] = schema.Document{
                ID:      product.ProductID,
                Content: descriptions[j],
                Metadata: map[string]any{
                    "product_id": product.ProductID,
                    "name":       product.Name,
                    "category":   product.Category,
                    "price":      product.Price,
                },
            }
        }

        // Batch store: documents and embeddings are parallel slices
        if err := r.vectorStore.Add(ctx, docs, embeddings); err != nil {
            return err
        }
    }

    return nil
}
```

## Related Resources

- [Vector Store Guide](/docs/reference/providers/vectorstore/) for scaling strategies
- [Embedding Guide](/docs/reference/providers/embedding/) for embedding optimization
- [Knowledge QA System](/docs/guides/capabilities/rag/knowledge-qa/) for similarity patterns
- [Enterprise RAG](/docs/guides/capabilities/rag/enterprise-rag/) for RAG pipeline patterns
