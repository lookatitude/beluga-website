---
title: Enterprise RAG Knowledge Base
description: "Build a production RAG pipeline with hybrid search, multi-source ingestion, and semantic retrieval. Grounded answers with source citations."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "enterprise RAG, knowledge base AI, hybrid search pipeline, semantic retrieval, document ingestion, Beluga AI, Go, RAG use case"
---

Organizations accumulate vast amounts of knowledge across documents, wikis, codebases, and databases. When employees search for information, keyword-based systems return documents that contain the search terms but may not actually answer the question. A search for "how to handle customer refunds" returns every document mentioning "refund" — policy documents, meeting notes, email threads — without understanding which ones actually explain the refund process. This semantic gap between intent and keyword matching leads to lost productivity and inconsistent decision-making.

An enterprise RAG (Retrieval-Augmented Generation) system brings semantic understanding to internal knowledge, enabling employees to ask natural language questions and receive accurate, context-grounded answers. RAG is chosen over fine-tuning the LLM on internal documents because it keeps the knowledge current (new documents are indexed immediately), transparent (answers cite their sources), and controllable (access policies can be enforced at retrieval time).

## Solution Architecture

Beluga AI provides a complete RAG pipeline: document loaders ingest content from multiple sources, text splitters chunk it into semantically meaningful units, embedders convert text to vectors, vector stores index them for fast similarity search, and retriever strategies combine multiple signals for high-quality results. The LLM generates grounded answers from retrieved context.

Beluga AI defaults to hybrid search (Vector + BM25 + RRF fusion) because neither vector similarity nor keyword matching alone is sufficient. Vector search captures semantic meaning but can miss exact terms (product names, error codes, policy numbers). Keyword search catches exact terms but misses semantic relationships. Reciprocal Rank Fusion (RRF) combines both rankings without requiring score normalization, producing results that satisfy both intent-based and term-based queries.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Documents  │───▶│  Splitter    │───▶│  Embedder    │
│  (PDF, HTML, │    │  (Recursive, │    │  (OpenAI,    │
│   Markdown)  │    │   Markdown)  │    │   Ollama)    │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Response   │◀───│  LLM         │◀───│ VectorStore  │
│   (Grounded  │    │  (Generate   │    │ (pgvector,   │
│    Answer)   │    │   Answer)    │    │  Pinecone)   │
└──────────────┘    └──────────────┘    └──────────────┘
                          ▲
                          │
                    ┌─────┴────────┐
                    │  Retriever   │
                    │  (Hybrid,    │
                    │   CRAG, HyDE)│
                    └──────────────┘
```

## Document Ingestion Pipeline

The ingestion pipeline loads documents from various sources, splits them into chunks, generates embeddings, and stores them in a vector database. Built-in loaders cover text, Markdown, CSV and JSON; PDFs and office documents go through a document-conversion provider such as `docling` or `unstructured`.

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/rag/splitter"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"

    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/docling"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

func ingestDocuments(ctx context.Context, paths []string) error {
    // Load PDFs (and DOCX, HTML, ...) through a Docling server
    pdfLoader, err := loader.New("docling", config.ProviderConfig{
        BaseURL: os.Getenv("DOCLING_URL"), // e.g. http://localhost:5001
    })
    if err != nil {
        return fmt.Errorf("create loader: %w", err)
    }

    textSplitter := splitter.NewRecursiveSplitter(
        splitter.WithChunkSize(1000),
        splitter.WithChunkOverlap(150),
    )

    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-small",
    })
    if err != nil {
        return fmt.Errorf("create embedder: %w", err)
    }

    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: os.Getenv("DATABASE_URL"),
    })
    if err != nil {
        return fmt.Errorf("create vector store: %w", err)
    }

    for _, path := range paths {
        docs, err := pdfLoader.Load(ctx, path)
        if err != nil {
            return fmt.Errorf("load %s: %w", path, err)
        }

        // Split into chunks for embedding
        chunks, err := textSplitter.SplitDocuments(ctx, docs)
        if err != nil {
            return fmt.Errorf("split documents: %w", err)
        }

        texts := make([]string, len(chunks))
        for i, chunk := range chunks {
            texts[i] = chunk.Content
        }

        embeddings, err := embedder.Embed(ctx, texts)
        if err != nil {
            return fmt.Errorf("embed documents: %w", err)
        }

        if err := store.Add(ctx, chunks, embeddings); err != nil {
            return fmt.Errorf("store documents: %w", err)
        }

        log.Printf("Ingested %d chunks from %s", len(chunks), path)
    }
    return nil
}

func main() {
    if err := ingestDocuments(context.Background(), []string{"/data/knowledge-base/handbook.pdf"}); err != nil {
        log.Fatal(err)
    }
}
```

## Hybrid Retrieval with RRF Fusion

Beluga AI's default retrieval strategy combines vector similarity search with BM25 keyword matching, using Reciprocal Rank Fusion to merge results. This hybrid approach outperforms either method alone. `retriever.NewHybridRetriever` needs a keyword backend that implements `retriever.BM25Searcher`; Beluga AI does not ship a BM25 index, so you connect your own.

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/rag/embedding"
    "github.com/lookatitude/beluga-ai/v2/rag/retriever"
    "github.com/lookatitude/beluga-ai/v2/rag/vectorstore"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/embedding/providers/openai"
    _ "github.com/lookatitude/beluga-ai/v2/rag/vectorstore/providers/pgvector"
)

// RAGSystem combines retrieval and generation.
type RAGSystem struct {
    embedder  embedding.Embedder
    store     vectorstore.VectorStore
    retriever retriever.Retriever
    model     llm.ChatModel
}

// NewRAGSystem takes your BM25 keyword index (Elasticsearch, OpenSearch,
// Typesense, ...) wrapped in the retriever.BM25Searcher interface.
// Beluga AI does not bundle a BM25 engine.
func NewRAGSystem(ctx context.Context, bm25 retriever.BM25Searcher) (*RAGSystem, error) {
    embedder, err := embedding.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "text-embedding-3-small",
    })
    if err != nil {
        return nil, fmt.Errorf("create embedder: %w", err)
    }

    store, err := vectorstore.New("pgvector", config.ProviderConfig{
        BaseURL: os.Getenv("DATABASE_URL"),
    })
    if err != nil {
        return nil, fmt.Errorf("create vector store: %w", err)
    }

    // Hybrid retriever: vector + BM25 + RRF fusion
    ret := retriever.NewHybridRetriever(store, embedder, bm25)

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return nil, fmt.Errorf("create model: %w", err)
    }

    return &RAGSystem{
        embedder:  embedder,
        store:     store,
        retriever: ret,
        model:     model,
    }, nil
}

// buildMessages formats retrieved documents as grounded context.
func buildMessages(docs []schema.Document, question string) []schema.Message {
    var docContext strings.Builder
    for _, doc := range docs {
        docContext.WriteString(doc.Content)
        docContext.WriteString("\n\n")
    }
    return []schema.Message{
        schema.NewSystemMessage("Answer the question using only the provided context. " +
            "If the context doesn't contain the answer, say so."),
        schema.NewHumanMessage(fmt.Sprintf("Context:\n%s\n\nQuestion: %s", docContext.String(), question)),
    }
}

func (r *RAGSystem) Query(ctx context.Context, question string) (string, error) {
    // Retrieve relevant documents
    docs, err := r.retriever.Retrieve(ctx, question, retriever.WithTopK(5))
    if err != nil {
        return "", fmt.Errorf("retrieve: %w", err)
    }

    // Generate answer grounded in retrieved context
    resp, err := r.model.Generate(ctx, buildMessages(docs, question))
    if err != nil {
        return "", fmt.Errorf("generate: %w", err)
    }

    return resp.Text(), nil
}

func main() {
    ctx := context.Background()
    rag, err := NewRAGSystem(ctx, newKeywordIndex())
    if err != nil {
        log.Fatal(err)
    }
    answer, err := rag.Query(ctx, "How do we handle customer refunds?")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(answer)
}

// newKeywordIndex returns your BM25 backend. This stub returns no hits.
func newKeywordIndex() retriever.BM25Searcher { return noKeywordHits{} }

type noKeywordHits struct{}

func (noKeywordHits) Search(context.Context, string, int) ([]schema.Document, error) {
    return nil, nil
}
```

## Advanced Retrieval Strategies

Beyond hybrid search, Beluga AI supports advanced retrieval strategies for higher-quality results.

### CRAG (Corrective RAG)

CRAG evaluates the relevance of retrieved documents and falls back to alternative sources when relevance is low:

```go
// CRAG wraps a base retriever. When the model grades the retrieved
// documents as not relevant enough, it falls back to a web search.
// webSearcher is your implementation of retriever.WebSearcher.
cragRetriever := retriever.NewCRAGRetriever(r.retriever, r.model, webSearcher,
    retriever.WithCRAGThreshold(0.6),
)

docs, err := cragRetriever.Retrieve(ctx, "What is our refund policy?",
    retriever.WithTopK(10),
)
if err != nil {
    return fmt.Errorf("crag retrieve: %w", err)
}
```

### HyDE (Hypothetical Document Embeddings)

HyDE generates a hypothetical answer to the query first, then uses that hypothetical answer's embedding for retrieval. This bridges the gap between short queries and long documents:

```go
// HyDE asks the model for a hypothetical answer, embeds it,
// and searches the vector store with that embedding.
hydeRetriever := retriever.NewHyDERetriever(r.model, r.embedder, r.store)

docs, err := hydeRetriever.Retrieve(ctx, "quarterly revenue trends",
    retriever.WithTopK(5),
)
if err != nil {
    return fmt.Errorf("hyde retrieve: %w", err)
}
```

## Streaming Responses

For a better user experience, stream responses as they are generated:

```go
func (r *RAGSystem) StreamQuery(ctx context.Context, question string) iter.Seq2[schema.StreamChunk, error] {
    docs, err := r.retriever.Retrieve(ctx, question, retriever.WithTopK(5))
    if err != nil {
        return func(yield func(schema.StreamChunk, error) bool) {
            yield(schema.StreamChunk{}, err)
        }
    }

    // Each chunk carries a text Delta
    return r.model.Stream(ctx, buildMessages(docs, question))
}
```

## Production Considerations

### Observability

Instrument the RAG pipeline with OpenTelemetry to track latency, retrieval quality, and token usage:

```go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

func (r *RAGSystem) QueryWithTracing(ctx context.Context, question string) (string, error) {
    tracer := otel.Tracer("rag-system")
    ctx, span := tracer.Start(ctx, "rag.query")
    defer span.End()

    span.SetAttributes(attribute.String("gen_ai.prompt", question))

    docs, err := r.retriever.Retrieve(ctx, question, retriever.WithTopK(5))
    if err != nil {
        span.RecordError(err)
        return "", err
    }

    span.SetAttributes(attribute.Int("rag.documents_retrieved", len(docs)))

    resp, err := r.model.Generate(ctx, buildMessages(docs, question))
    if err != nil {
        span.RecordError(err)
        return "", err
    }
    return resp.Text(), nil
}
```

### Resilience

Wrap LLM calls with retry and circuit breaker for production reliability:

```go
import "github.com/lookatitude/beluga-ai/v2/resilience"

policy := resilience.RetryPolicy{
    MaxAttempts:    3,
    InitialBackoff: 500 * time.Millisecond,
    MaxBackoff:     5 * time.Second,
    BackoffFactor:  2.0,
    Jitter:         true,
}

answer, err := resilience.Retry(ctx, policy, func(ctx context.Context) (string, error) {
    return r.Query(ctx, question)
})
```

### Batch Ingestion

Process large document collections efficiently with batched embedding and storage:

```go
func (r *RAGSystem) IngestBatch(ctx context.Context, docs []schema.Document) error {
    batchSize := 100
    for i := 0; i < len(docs); i += batchSize {
        end := min(i+batchSize, len(docs))
        batch := docs[i:end]

        texts := make([]string, len(batch))
        for j, doc := range batch {
            texts[j] = doc.Content
        }

        embeddings, err := r.embedder.Embed(ctx, texts)
        if err != nil {
            return fmt.Errorf("embed batch %d: %w", i/batchSize, err)
        }

        if err := r.store.Add(ctx, batch, embeddings); err != nil {
            return fmt.Errorf("store batch %d: %w", i/batchSize, err)
        }
    }
    return nil
}
```

### Scaling

- **Horizontal scaling**: Deploy multiple RAG service instances behind a load balancer. Each instance is stateless.
- **Vector store scaling**: Use read replicas for pgvector or managed services like Pinecone for automatic scaling.
- **Embedding caching**: Cache embeddings for frequently queried terms to reduce API calls and latency.
- **Chunk size tuning**: Experiment with chunk sizes (256-1024 tokens) and overlap (10-20%) for your document types.

### Security

- Validate and sanitize user queries before passing to the retriever
- Implement document-level access control by filtering on metadata during retrieval
- Use Beluga AI's `guard/` pipeline to screen LLM inputs and outputs for PII leakage
- Store API keys in environment variables or a secrets manager, never in code

## Related Resources

- [RAG Pipeline Guide](/docs/guides/capabilities/rag/rag-pipeline/) for step-by-step setup
- [RAG Recipes](/docs/recipes/rag/) for advanced retrieval patterns
- [Vector Store Integration](/docs/reference/providers/vectorstore/) for provider-specific configuration
