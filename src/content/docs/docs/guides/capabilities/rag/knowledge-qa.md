---
title: Enterprise Knowledge Q&A System
description: "Build scalable knowledge Q&A with semantic retrieval across millions of documents. Sub-second responses with source attribution."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "enterprise knowledge QA, semantic search, knowledge base AI, document retrieval, RAG Q&A, Beluga AI, Go, enterprise search"
---

Enterprises accumulate millions of documents across wikis, knowledge bases, and documentation systems. The scale itself creates a discovery problem: employees know the answer exists somewhere but cannot find it. Traditional keyword search delivers low accuracy because it matches terms, not meaning — a question like "what is our policy on remote work expenses?" will miss documents titled "Work From Home Reimbursement Guidelines" if the exact terms do not match.

A semantic knowledge Q&A system uses vector similarity search to find relevant context and generates accurate answers grounded in retrieved documents. Unlike a general-purpose chatbot that might hallucinate, the RAG approach ensures every answer is traceable to a specific source document, providing both accuracy and auditability.

## Solution Architecture

Beluga AI provides a complete RAG pipeline: document loaders ingest content, text splitters chunk it semantically, embedders convert text to vectors, vector stores index them for similarity search, and LLMs generate answers from retrieved context. The system scales to millions of documents with consistent sub-second response times.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Documents  │───▶│   Splitter   │───▶│   Embedder   │
│ (Millions)   │    │              │    │              │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Answer     │◀───│     LLM      │◀───│ Vector Store │
│  + Sources   │    │  (Generate)  │    │ (Similarity) │
└──────────────┘    └──────────────┘    └──────┬───────┘
                          ▲                     │
                          │                     │
                    ┌─────┴────────┐            │
                    │   Retrieved  │◀───────────┘
                    │   Context    │
                    └──────────────┘
```

## Document Ingestion

Load, chunk, embed, and store documents for search:

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
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/rag/splitter"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

type KnowledgeQASystem struct {
    embedder    embedding.Embedder
    vectorStore vectorstore.VectorStore
    model       llm.ChatModel
}

func NewKnowledgeQASystem(ctx context.Context) (*KnowledgeQASystem, error) {
    embedder, err := embedding.New("openai", config.ProviderConfig{
        Model:  "text-embedding-3-large",
        APIKey: os.Getenv("OPENAI_API_KEY"),
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    // Use a persistent vector store for scale
    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: os.Getenv("DATABASE_URL"),
        Options: map[string]any{
            "table":     "knowledge_base",
            "dimension": float64(3072), // text-embedding-3-large
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return nil, fmt.Errorf("create model: %w", err)
    }

    return &KnowledgeQASystem{
        embedder:    embedder,
        vectorStore: store,
        model:       model,
    }, nil
}

func (k *KnowledgeQASystem) IndexDocuments(ctx context.Context, docPaths []string) error {
    for _, path := range docPaths {
        if err := k.indexDocument(ctx, path); err != nil {
            log.Printf("index %s: %v", path, err) // continue with other documents
        }
    }
    return nil
}

func (k *KnowledgeQASystem) indexDocument(ctx context.Context, docPath string) error {
    // Load a plain-text or Markdown file ("text" and "markdown" loaders are built in)
    docLoader, err := loader.New("text", config.ProviderConfig{})
    if err != nil {
        return fmt.Errorf("create loader: %w", err)
    }

    docs, err := docLoader.Load(ctx, docPath)
    if err != nil {
        return fmt.Errorf("load documents: %w", err)
    }

    // Split into chunks
    textSplitter := splitter.NewRecursiveSplitter(
        splitter.WithChunkSize(1000),
        splitter.WithChunkOverlap(200),
    )

    chunks, err := textSplitter.SplitDocuments(ctx, docs)
    if err != nil {
        return fmt.Errorf("split documents: %w", err)
    }

    // Generate embeddings in one batch
    texts := make([]string, len(chunks))
    for i, chunk := range chunks {
        texts[i] = chunk.Content
    }

    embeddings, err := k.embedder.Embed(ctx, texts)
    if err != nil {
        return fmt.Errorf("embed documents: %w", err)
    }

    // Store chunks with their embeddings
    if err := k.vectorStore.Add(ctx, chunks, embeddings); err != nil {
        return fmt.Errorf("store documents: %w", err)
    }

    return nil
}

func main() {
    ctx := context.Background()
    qa, err := NewKnowledgeQASystem(ctx)
    if err != nil {
        log.Fatal(err)
    }
    if err := qa.IndexDocuments(ctx, []string{"docs/handbook.md"}); err != nil {
        log.Fatal(err)
    }
}
```

## Question Answering

Retrieve relevant context and generate grounded answers:

```go
import (
    "context"
    "fmt"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

type Answer struct {
    Question string
    Answer   string
    Sources  []Source
}

type Source struct {
    Title   string
    Content string
    URL     string
}

func (k *KnowledgeQASystem) AnswerQuestion(ctx context.Context, question string) (*Answer, error) {
    // Generate query embedding
    queryEmbedding, err := k.embedder.EmbedSingle(ctx, question)
    if err != nil {
        return nil, fmt.Errorf("embed question: %w", err)
    }

    // Retrieve the 5 most relevant chunks above a similarity threshold
    results, err := k.vectorStore.Search(ctx, queryEmbedding, 5,
        vectorstore.WithThreshold(0.7),
    )
    if err != nil {
        return nil, fmt.Errorf("similarity search: %w", err)
    }

    if len(results) == 0 {
        return &Answer{
            Question: question,
            Answer:   "I couldn't find relevant information to answer this question.",
        }, nil
    }

    // Build context from retrieved documents
    var contextText strings.Builder
    sources := make([]Source, len(results))

    for i, result := range results {
        contextText.WriteString(result.Content)
        contextText.WriteString("\n\n")

        title, _ := result.Metadata["title"].(string)
        url, _ := result.Metadata["url"].(string)
        sources[i] = Source{Title: title, Content: result.Content, URL: url}
    }

    // Generate answer using LLM
    msgs := []schema.Message{
        schema.NewSystemMessage("You are a helpful assistant that answers questions based on provided context. " +
            "If the context doesn't contain enough information, say so clearly."),
        schema.NewHumanMessage(fmt.Sprintf(
            "Context:\n%s\n\nQuestion: %s\n\nProvide a clear, accurate answer based only on the context above.",
            contextText.String(),
            question,
        )),
    }

    resp, err := k.model.Generate(ctx, msgs)
    if err != nil {
        return nil, fmt.Errorf("generate answer: %w", err)
    }

    return &Answer{
        Question: question,
        Answer:   resp.Text(),
        Sources:  sources,
    }, nil
}
```

## Streaming Responses

Stream answers as they are generated for better UX:

```go
import (
    "context"
    "fmt"
    "iter"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/schema"
)

func (k *KnowledgeQASystem) StreamAnswer(ctx context.Context, question string) iter.Seq2[schema.StreamChunk, error] {
    return func(yield func(schema.StreamChunk, error) bool) {
        // Retrieve context (same as non-streaming)
        queryEmbedding, err := k.embedder.EmbedSingle(ctx, question)
        if err != nil {
            yield(schema.StreamChunk{}, err)
            return
        }

        results, err := k.vectorStore.Search(ctx, queryEmbedding, 5)
        if err != nil {
            yield(schema.StreamChunk{}, err)
            return
        }

        // Build context
        var contextText strings.Builder
        for _, result := range results {
            contextText.WriteString(result.Content)
            contextText.WriteString("\n\n")
        }

        msgs := []schema.Message{
            schema.NewSystemMessage("Answer based on the provided context."),
            schema.NewHumanMessage(fmt.Sprintf("Context:\n%s\n\nQuestion: %s", contextText.String(), question)),
        }

        // Stream from LLM; each chunk carries a text Delta
        for chunk, err := range k.model.Stream(ctx, msgs) {
            if !yield(chunk, err) {
                return
            }
        }
    }
}
```

## Hybrid Search

Combine vector similarity with keyword matching for better results:

```go
import (
    "context"
    "fmt"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/rag/retriever"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

type HybridKnowledgeQA struct {
    KnowledgeQASystem
    retriever retriever.Retriever
}

// bm25 is your keyword index (Elasticsearch, OpenSearch, Typesense, ...)
// adapted to the one-method retriever.BM25Searcher interface. Beluga AI
// does not bundle a BM25 engine.
func NewHybridKnowledgeQA(ctx context.Context, bm25 retriever.BM25Searcher) (*HybridKnowledgeQA, error) {
    base, err := NewKnowledgeQASystem(ctx)
    if err != nil {
        return nil, err
    }

    // Hybrid retriever: vector + BM25, fused with Reciprocal Rank Fusion
    ret := retriever.NewHybridRetriever(base.vectorStore, base.embedder, bm25)

    return &HybridKnowledgeQA{
        KnowledgeQASystem: *base,
        retriever:         ret,
    }, nil
}

func (h *HybridKnowledgeQA) AnswerQuestion(ctx context.Context, question string) (*Answer, error) {
    // Retrieve using hybrid search
    docs, err := h.retriever.Retrieve(ctx, question,
        retriever.WithTopK(5),
    )
    if err != nil {
        return nil, fmt.Errorf("retrieve: %w", err)
    }

    // Build context and generate answer (same as before)
    var contextText strings.Builder
    sources := make([]Source, len(docs))

    for i, doc := range docs {
        contextText.WriteString(doc.Content)
        contextText.WriteString("\n\n")

        title, _ := doc.Metadata["title"].(string)
        url, _ := doc.Metadata["url"].(string)
        sources[i] = Source{Title: title, Content: doc.Content, URL: url}
    }

    msgs := []schema.Message{
        schema.NewSystemMessage("Answer based on the provided context."),
        schema.NewHumanMessage(fmt.Sprintf("Context:\n%s\n\nQuestion: %s", contextText.String(), question)),
    }

    resp, err := h.model.Generate(ctx, msgs)
    if err != nil {
        return nil, fmt.Errorf("generate: %w", err)
    }

    return &Answer{
        Question: question,
        Answer:   resp.Text(),
        Sources:  sources,
    }, nil
}
```

## Production Considerations

### Observability

Track query latency and retrieval quality:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

func (k *KnowledgeQASystem) AnswerWithTracing(ctx context.Context, question string) (*Answer, error) {
    tracer := otel.Tracer("knowledge-qa")
    ctx, span := tracer.Start(ctx, "qa.answer")
    defer span.End()

    span.SetAttributes(
        attribute.String("gen_ai.prompt", question),
    )

    start := time.Now()
    answer, err := k.AnswerQuestion(ctx, question)
    duration := time.Since(start)

    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    span.SetAttributes(
        attribute.Int("qa.sources_count", len(answer.Sources)),
        attribute.Float64("qa.duration_ms", float64(duration.Milliseconds())),
    )

    return answer, nil
}
```

### Batch Ingestion

Process large document collections efficiently:

```go
func (k *KnowledgeQASystem) IndexBatch(ctx context.Context, docPaths []string) error {
    batchSize := 100

    for i := 0; i < len(docPaths); i += batchSize {
        end := min(i+batchSize, len(docPaths))
        batch := docPaths[i:end]

        // Process batch in parallel
        var wg sync.WaitGroup
        for _, path := range batch {
            wg.Add(1)
            go func(p string) {
                defer wg.Done()
                if err := k.indexDocument(ctx, p); err != nil {
                    log.Printf("index %s: %v", p, err) // continue with the rest
                }
            }(path)
        }
        wg.Wait()
    }

    return nil
}
```

### Resilience

Add retry logic for transient failures:

```go
import "github.com/lookatitude/beluga-ai/v2/resilience"

policy := resilience.RetryPolicy{
    MaxAttempts:    3,
    InitialBackoff: 500 * time.Millisecond,
    MaxBackoff:     5 * time.Second,
    BackoffFactor:  2.0,
    Jitter:         true,
}

answer, err := resilience.Retry(ctx, policy, func(ctx context.Context) (*Answer, error) {
    return k.AnswerQuestion(ctx, question)
})
```

### Caching

Cache frequent queries to reduce costs:

```go
import "github.com/lookatitude/beluga-ai/v2/cache"

type CachedKnowledgeQA struct {
    KnowledgeQASystem
    cache cache.Cache
}

func (c *CachedKnowledgeQA) AnswerQuestion(ctx context.Context, question string) (*Answer, error) {
    cacheKey := fmt.Sprintf("qa:%s", question)

    // Check cache first
    cached, ok, err := c.cache.Get(ctx, cacheKey)
    if err != nil {
        return nil, fmt.Errorf("cache get: %w", err)
    }
    if ok {
        if answer, isAnswer := cached.(*Answer); isAnswer {
            return answer, nil
        }
    }

    // Generate answer
    answer, err := c.KnowledgeQASystem.AnswerQuestion(ctx, question)
    if err != nil {
        return nil, err
    }

    // Cache for 10 minutes
    if err := c.cache.Set(ctx, cacheKey, answer, 10*time.Minute); err != nil {
        return nil, fmt.Errorf("cache set: %w", err)
    }

    return answer, nil
}
```

### Access Control

Filter results based on user permissions:

```go
func (k *KnowledgeQASystem) AnswerWithAccessControl(ctx context.Context, userID, question string) (*Answer, error) {
    queryEmbedding, err := k.embedder.EmbedSingle(ctx, question)
    if err != nil {
        return nil, err
    }

    // Retrieve more results than needed, then filter
    results, err := k.vectorStore.Search(ctx, queryEmbedding, 20)
    if err != nil {
        return nil, err
    }

    // Filter based on user permissions (canAccess is your ACL check)
    filtered := make([]schema.Document, 0, 5)
    for _, result := range results {
        if canAccess(userID, result.Metadata["acl"]) {
            filtered = append(filtered, result)
            if len(filtered) >= 5 {
                break
            }
        }
    }

    // Generate the answer from filtered (same as AnswerQuestion)
    return k.answerFromDocs(ctx, question, filtered)
}
```

## Related Resources

- [Enterprise RAG Guide](/docs/guides/capabilities/rag/enterprise-rag/) for complete RAG pipeline
- [Retriever Guide](/docs/guides/capabilities/rag/rag-strategies/) for advanced retrieval
- [Vector Store Guide](/docs/reference/providers/vectorstore/) for scaling strategies
- [Recommendation Engine](/docs/guides/capabilities/rag/recommendation-engine/) for similarity patterns
