---
title: Hybrid Search Implementation
description: "Combine vector search and BM25 keyword search with Reciprocal Rank Fusion in Go — build production-grade hybrid retrieval with Beluga AI's retriever interface."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, tutorial, hybrid search, vector search, BM25, RRF, retrieval, RAG"
---

Vector search excels at semantic similarity ("canine" matches "dog") but fails at exact matches like error codes or product IDs. Keyword search (BM25) excels at exact matches but fails at synonyms. Neither method alone provides reliable retrieval across all query types. Hybrid search combines both methods using **Reciprocal Rank Fusion (RRF)** to produce a single, highly relevant result list that captures both semantic understanding and exact matching.

Beluga AI v2 uses hybrid search as the default retrieval strategy because it consistently outperforms either approach alone across diverse query types.

## What You Will Build

A hybrid retriever that queries both vector and keyword backends in parallel, fuses the results with RRF, and returns a unified ranked list.

## Prerequisites

- Understanding of [In-memory Vector Store](/docs/guides/foundations/inmemory-vectorstore)
- A vector store and a keyword search backend (or a mock)

## Why Hybrid Search

| Search Type | Strengths | Weaknesses |
|:---|:---|:---|
| Vector | Concepts, synonyms, paraphrases | Exact IDs, codes, proper nouns |
| Keyword (BM25) | Exact matches, filtering | Synonyms, paraphrases |
| Hybrid | Both | Slightly more complex |

## Step 1: Define the Retriever Interface

The `Retriever` interface is intentionally minimal -- a single method that takes a query string and returns ranked documents. Both vector search and keyword search backends implement this interface, allowing the hybrid retriever to treat them uniformly. This follows the same interface-first design pattern used across Beluga AI.

The snippets in Steps 1-5 are parts of one file that hand-builds hybrid retrieval so you can see how it works. Beluga AI ships the same strategy ready-made as `retriever.NewHybridRetriever`; Step 6 shows that version.

```go
import (
    "context"
    "sort"

    "github.com/lookatitude/beluga-ai/v2/schema"
)

// Retriever searches for relevant documents.
type Retriever interface {
    Retrieve(ctx context.Context, query string, topK int) ([]schema.Document, error)
}
```

## Step 2: Build the Hybrid Retriever

The hybrid retriever queries both backends and fuses the results. Each backend is asked for `topK * 2` results (over-fetching) because RRF may re-rank documents from one list above documents from the other -- having a larger candidate pool gives the fusion algorithm more material to work with, producing a better final ranking.

```go
// HybridRetriever combines vector and keyword search.
type HybridRetriever struct {
    vectorRetriever  Retriever
    keywordRetriever Retriever
}

func NewHybridRetriever(vector, keyword Retriever) *HybridRetriever {
    return &HybridRetriever{
        vectorRetriever:  vector,
        keywordRetriever: keyword,
    }
}

func (h *HybridRetriever) Retrieve(ctx context.Context, query string, topK int) ([]schema.Document, error) {
    // Query both backends (could be parallelized with goroutines)
    vecDocs, err := h.vectorRetriever.Retrieve(ctx, query, topK*2)
    if err != nil {
        return nil, fmt.Errorf("vector search: %w", err)
    }

    keyDocs, err := h.keywordRetriever.Retrieve(ctx, query, topK*2)
    if err != nil {
        return nil, fmt.Errorf("keyword search: %w", err)
    }

    // Fuse results
    fused := reciprocalRankFusion(vecDocs, keyDocs)

    // Return top K
    if len(fused) > topK {
        fused = fused[:topK]
    }

    return fused, nil
}
```

## Step 3: Implement Reciprocal Rank Fusion

RRF is the key to making hybrid search work. Unlike simple score averaging, RRF does not require calibrated similarity scores -- it works purely on rank positions. This is important because vector similarity scores (0.0 to 1.0) and BM25 scores (unbounded positive values) are not directly comparable. The RRF formula `1 / (k + rank + 1)` assigns each document a score based on its position in each list, then sums the scores across all lists. Documents that rank highly in both lists receive the highest combined scores.

The constant `k = 60` is the standard value from the original RRF paper. It controls how quickly scores decay with rank position -- higher values make the ranking more uniform (less difference between rank 1 and rank 10), while lower values amplify the advantage of top-ranked results.

```go
import "fmt"

const rrfK = 60.0 // Standard RRF constant

type scoredDoc struct {
    doc   schema.Document
    score float64
}

func reciprocalRankFusion(lists ...[]schema.Document) []schema.Document {
    scores := make(map[string]*scoredDoc)

    for _, list := range lists {
        for rank, doc := range list {
            key := docKey(doc)
            if _, ok := scores[key]; !ok {
                scores[key] = &scoredDoc{doc: doc}
            }
            // RRF formula: 1 / (k + rank + 1)
            scores[key].score += 1.0 / (rrfK + float64(rank) + 1.0)
        }
    }

    // Sort by descending score
    result := make([]scoredDoc, 0, len(scores))
    for _, sd := range scores {
        result = append(result, *sd)
    }
    sort.Slice(result, func(i, j int) bool {
        return result[i].score > result[j].score
    })

    // Extract documents with scores
    docs := make([]schema.Document, len(result))
    for i, sd := range result {
        sd.doc.Score = sd.score
        docs[i] = sd.doc
    }

    return docs
}

func docKey(doc schema.Document) string {
    if doc.ID != "" {
        return doc.ID
    }
    return doc.Content // Fallback to content hash
}
```

## Step 4: Parallel Retrieval

Since vector search and keyword search are independent operations targeting different backends, running them concurrently cuts latency roughly in half. Each search runs in its own goroutine, and a `sync.WaitGroup` synchronizes completion. The error handling follows a fail-fast pattern: if either backend fails, the entire operation returns an error rather than returning partial results that could mislead the downstream model.

```go
import "sync"

func (h *HybridRetriever) RetrieveParallel(ctx context.Context, query string, topK int) ([]schema.Document, error) {
    var vecDocs, keyDocs []schema.Document
    var vecErr, keyErr error
    var wg sync.WaitGroup

    wg.Add(2)
    go func() {
        defer wg.Done()
        vecDocs, vecErr = h.vectorRetriever.Retrieve(ctx, query, topK*2)
    }()
    go func() {
        defer wg.Done()
        keyDocs, keyErr = h.keywordRetriever.Retrieve(ctx, query, topK*2)
    }()
    wg.Wait()

    if vecErr != nil {
        return nil, fmt.Errorf("vector search: %w", vecErr)
    }
    if keyErr != nil {
        return nil, fmt.Errorf("keyword search: %w", keyErr)
    }

    fused := reciprocalRankFusion(vecDocs, keyDocs)
    if len(fused) > topK {
        fused = fused[:topK]
    }

    return fused, nil
}
```

## Step 5: Use in a RAG Pipeline

The hybrid retriever integrates into a standard RAG pipeline as a drop-in replacement for any single retriever. The query "error code ERR_CONNECTION_REFUSED" demonstrates hybrid search's strength: vector search finds semantically related troubleshooting docs, while keyword search finds exact matches for the error code string. RRF combines both, giving the model comprehensive context for generating an accurate answer.

```go
func main() {
    ctx := context.Background()

    hybrid := NewHybridRetriever(vectorRetriever, keywordRetriever)

    // Retrieve relevant documents
    docs, err := hybrid.Retrieve(ctx, "error code ERR_CONNECTION_REFUSED", 5)
    if err != nil {
        fmt.Printf("Search error: %v\n", err)
        return
    }

    // Build context for the LLM
    var context string
    for _, doc := range docs {
        context += fmt.Sprintf("---\n%s\n", doc.Content)
    }

    // Generate answer using retrieved context
    msgs := []schema.Message{
        schema.NewSystemMessage("Answer based on the following context:\n" + context),
        schema.NewHumanMessage("How do I fix ERR_CONNECTION_REFUSED?"),
    }

    resp, err := model.Generate(ctx, msgs)
    if err != nil {
        fmt.Printf("Generate error: %v\n", err)
        return
    }
    fmt.Println(resp.Text())
}
```

## Step 6: Use the Built-in Hybrid Retriever

The `rag/retriever` package ships hybrid retrieval out of the box. `retriever.NewHybridRetriever` takes a `vectorstore.VectorStore`, an `embedding.Embedder` and a `retriever.BM25Searcher`, runs the dense and keyword searches, and fuses them with RRF (`k = 60` by default; change it with `retriever.WithHybridRRFK`). Beluga AI does not bundle a BM25 index, so you supply one that satisfies the one-method `BM25Searcher` interface, typically backed by Elasticsearch, OpenSearch or Typesense. The example below uses a naive term-count searcher and the in-memory embedder and store so that it runs without external services.

To fuse any set of retrievers (not only vector + BM25), use `retriever.NewEnsembleRetriever(retrievers, retriever.NewRRFStrategy(60))`.

```go
package main

import (
    "context"
    "fmt"
    "log"
    "sort"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/retriever"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/inmemory"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/inmemory"
)

// termSearcher is a toy keyword index that satisfies retriever.BM25Searcher.
// Replace it with a real BM25 engine in production.
type termSearcher struct {
    docs []schema.Document
}

func (t *termSearcher) Search(_ context.Context, query string, k int) ([]schema.Document, error) {
    terms := strings.Fields(strings.ToLower(query))
    var hits []schema.Document
    for _, d := range t.docs {
        content := strings.ToLower(d.Content)
        score := 0
        for _, term := range terms {
            score += strings.Count(content, term)
        }
        if score > 0 {
            d.Score = float64(score)
            hits = append(hits, d)
        }
    }
    sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
    if len(hits) > k {
        hits = hits[:k]
    }
    return hits, nil
}

func main() {
    ctx := context.Background()

    emb, err := embedding.New("inmemory", config.ProviderConfig{})
    if err != nil {
        log.Fatalf("embedder: %v", err)
    }
    store, err := vectorstore.New("inmemory", config.ProviderConfig{})
    if err != nil {
        log.Fatalf("vector store: %v", err)
    }

    docs := []schema.Document{
        {ID: "1", Content: "ERR_CONNECTION_REFUSED means nothing is listening on the target port."},
        {ID: "2", Content: "Check that the service is running and the firewall allows the port."},
        {ID: "3", Content: "Printers need fresh toner every few months."},
    }
    texts := make([]string, len(docs))
    for i, d := range docs {
        texts[i] = d.Content
    }
    vecs, err := emb.Embed(ctx, texts)
    if err != nil {
        log.Fatalf("embed: %v", err)
    }
    if err := store.Add(ctx, docs, vecs); err != nil {
        log.Fatalf("add: %v", err)
    }

    hybrid := retriever.NewHybridRetriever(store, emb, &termSearcher{docs: docs},
        retriever.WithHybridRRFK(60),
    )

    results, err := hybrid.Retrieve(ctx, "ERR_CONNECTION_REFUSED", retriever.WithTopK(2))
    if err != nil {
        log.Fatalf("retrieve: %v", err)
    }
    for _, d := range results {
        fmt.Printf("%.4f  %s\n", d.Score, d.Content)
    }
}
```

## Verification

1. Search for a generic concept ("how to fix printer") -- vector search should contribute more.
2. Search for an exact error code ("Error X99-Z") -- keyword search should contribute more.
3. Hybrid results should rank relevant documents highly for both query types.

## Next Steps

- [Multi-query Retrieval](/docs/guides/capabilities/rag/multiquery-chains) -- Expand queries for better recall
- [pgvector Sharding](/docs/guides/foundations/pgvector-sharding) -- Scale the vector backend
