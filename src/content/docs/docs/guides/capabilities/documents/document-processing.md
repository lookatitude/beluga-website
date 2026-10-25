---
title: Document Loading & Processing
description: "Load, parse, and chunk documents from files, PDFs, HTML, and cloud storage for RAG pipelines — with lazy loading, semantic splitting, and metadata preservation in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, document loading, text splitting, PDF, chunking, RAG pipeline, semantic splitting"
---

Before documents can be embedded and searched in a RAG pipeline, they need to be loaded from their source format, cleaned, and split into chunks that embedding models can process. This ingestion stage is the foundation of any knowledge-powered AI system — the quality of your chunking strategy directly affects retrieval precision and, consequently, the quality of generated answers.

Beluga AI provides document loaders for text, Markdown, CSV, and JSON, provider loaders for PDFs and office documents (via Docling or Unstructured.io), web pages, and cloud storage, and text splitters that preserve document structure. The pipeline is designed for production scale: file-by-file processing for bounded memory, batch processing for throughput, and explicit error handling for reliability.

## What You'll Learn

This guide covers:
- Loading documents from multiple sources (filesystem, PDF, HTML, cloud storage)
- Processing large datasets file by file so memory stays bounded
- Text splitting strategies and when to use each (recursive, markdown-aware, token, and code-friendly separators)
- Preserving document structure and metadata through the pipeline
- Batch processing with error handling and progress tracking
- Optimizing chunk size and overlap for retrieval quality

## When Document Processing Matters

Document processing is the first step in building any knowledge-powered AI feature:
- **RAG systems** that need searchable knowledge bases built from internal documents
- **Document intelligence** extracting structured data from files (invoices, contracts, reports)
- **Content migration** moving legacy document stores to AI-powered semantic search
- **Compliance** indexing regulated documents with metadata for auditing and access control
- **Knowledge management** making organizational knowledge discoverable through natural language

## Prerequisites

Before starting this guide:
- Complete [RAG Pipeline](/docs/guides/capabilities/rag/rag-pipeline/) to understand where document processing fits in the pipeline
- Understand vector embeddings and why documents need to be chunked
- Familiarity with file I/O in Go

## Document Loaders

Document loaders abstract the details of reading and parsing different file formats into a uniform `[]schema.Document` output. Every loader implements the `loader.DocumentLoader` interface, a single method `Load(ctx, source string) ([]schema.Document, error)`, so downstream pipeline stages (splitting, embedding, storing) work with clean, structured documents regardless of the original format.

The `rag/loader` package registers `text`, `markdown`, `csv`, and `json` loaders. Format-specific and remote loaders live under `rag/loader/providers/` (`docling`, `unstructured`, `cloudstorage`, `firecrawl`, `confluence`, `notion`, `gdrive`, `github`) and register themselves when you blank-import them.

### Loading a Directory

There is no built-in directory loader. Walk the tree with the standard library and hand each file to the loader registered for its extension. This keeps extension filtering and path exclusions in your code, where they are easy to change.

```go
package main

import (
    "context"
    "fmt"
    "io/fs"
    "log"
    "path/filepath"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

// loaderFor maps a file extension to a registered loader name.
var loaderFor = map[string]string{
    ".txt": "text",
    ".md":  "markdown",
    ".csv": "csv",
}

func LoadDirectory(ctx context.Context, dirPath string) ([]schema.Document, error) {
    root := filepath.Clean(dirPath)

    loaders := make(map[string]loader.DocumentLoader)
    for _, name := range loaderFor {
        l, err := loader.New(name, config.ProviderConfig{})
        if err != nil {
            return nil, fmt.Errorf("create %s loader: %w", name, err)
        }
        loaders[name] = l
    }

    var docs []schema.Document
    err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
        if err != nil {
            return err
        }
        if d.IsDir() {
            return nil
        }
        name, ok := loaderFor[filepath.Ext(path)]
        if !ok {
            return nil // skip unsupported extensions
        }
        loaded, err := loaders[name].Load(ctx, path)
        if err != nil {
            return fmt.Errorf("load %s: %w", path, err)
        }
        docs = append(docs, loaded...)
        return nil
    })
    if err != nil {
        return nil, err
    }

    fmt.Printf("Loaded %d documents\n", len(docs))
    return docs, nil
}

func main() {
    docs, err := LoadDirectory(context.Background(), "./knowledge_base")
    if err != nil {
        log.Fatal(err)
    }

    for _, doc := range docs {
        fmt.Printf("Document: %s (%d bytes)\n",
            doc.Metadata["source"],
            len(doc.Content),
        )
    }
}
```

### PDF and Office Documents

PDF is one of the most common document formats in enterprise environments, but extracting clean text from PDFs is notoriously difficult due to complex layouts, embedded fonts, and mixed content. Beluga AI delegates this to a document-understanding service. The `docling` provider calls an IBM Docling server; the `unstructured` provider calls the Unstructured.io partition API. Both accept a local file path and return the extracted content as documents.

```go
import (
    "context"
    "fmt"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/docling"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func LoadPDF(ctx context.Context, filePath string) ([]schema.Document, error) {
    l, err := loader.New("docling", config.ProviderConfig{
        BaseURL: "http://localhost:5001", // your Docling server
    })
    if err != nil {
        return nil, fmt.Errorf("create docling loader: %w", err)
    }

    docs, err := l.Load(ctx, filePath)
    if err != nil {
        return nil, fmt.Errorf("load PDF: %w", err)
    }

    return docs, nil
}
```

### Web Pages

Web pages contain significant noise (scripts, stylesheets, navigation) that degrades embedding quality. The `firecrawl` provider uses the Firecrawl service to render the page and return clean markdown.

```go
import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/firecrawl"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func LoadWebPage(ctx context.Context, pageURL string) ([]schema.Document, error) {
    l, err := loader.New("firecrawl", config.ProviderConfig{
        APIKey: os.Getenv("FIRECRAWL_API_KEY"),
    })
    if err != nil {
        return nil, fmt.Errorf("create firecrawl loader: %w", err)
    }

    docs, err := l.Load(ctx, pageURL)
    if err != nil {
        return nil, fmt.Errorf("load page: %w", err)
    }

    return docs, nil
}
```

### Cloud Storage

For cloud-native applications, documents often reside in object storage rather than local filesystems. The `cloudstorage` provider loads objects from S3 (`s3://`), GCS (`gs://`), and Azure Blob (`az://`), picking the backend from the URL prefix.

```go
import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/cloudstorage"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func LoadFromS3(ctx context.Context, bucket, key string) ([]schema.Document, error) {
    l, err := loader.New("cloudstorage", config.ProviderConfig{
        APIKey: os.Getenv("AWS_ACCESS_KEY_ID"),
        Options: map[string]any{
            "secret_key": os.Getenv("AWS_SECRET_ACCESS_KEY"),
            "region":     "us-east-1",
        },
    })
    if err != nil {
        return nil, fmt.Errorf("create cloudstorage loader: %w", err)
    }

    docs, err := l.Load(ctx, "s3://"+bucket+"/"+key)
    if err != nil {
        return nil, fmt.Errorf("load from S3: %w", err)
    }

    return docs, nil
}
```

## Processing Large Datasets File by File

Loading millions of documents into memory at once is not feasible: it would exhaust available RAM and potentially crash the process. `DocumentLoader.Load` works on one source at a time, so the way to keep memory bounded is to load, process, and discard one file before moving to the next. Memory use then depends on the largest file, not on the size of the corpus.

```go
func ProcessLargeDataset(ctx context.Context, dirPath string, l loader.DocumentLoader) error {
    processed := 0
    err := filepath.WalkDir(filepath.Clean(dirPath), func(path string, d fs.DirEntry, err error) error {
        if err != nil || d.IsDir() {
            return err
        }

        docs, err := l.Load(ctx, path)
        if err != nil {
            log.Printf("Error loading %s: %v", path, err)
            return nil // skip this file, keep walking
        }

        for _, doc := range docs {
            // Process one document at a time: chunk, embed, and store.
            if err := processDocument(ctx, doc); err != nil {
                log.Printf("Error processing %s: %v", path, err)
                continue
            }
            processed++
            if processed%100 == 0 {
                fmt.Printf("Processed %d documents\n", processed)
            }
        }
        return nil
    })
    if err != nil {
        return err
    }

    fmt.Printf("Total processed: %d documents\n", processed)
    return nil
}
```

`processDocument` is your own function that splits, embeds, and stores a single document (see the batch pipeline below). For transforms that run on every document, `loader.NewPipeline(loader.WithLoader(...), loader.WithTransformer(...))` composes a loader with `loader.Transformer` steps; see [Lazy Loading](/docs/guides/capabilities/documents/lazy-loading/).

## Text Splitting Strategies

Choosing the right splitting strategy is one of the most impactful decisions in a RAG pipeline. Different content types have different structure (prose paragraphs, markdown headings, code functions) and a splitter that respects that structure produces chunks that are more semantically coherent and easier to retrieve accurately.

The `rag/splitter` package ships three splitters, each also registered by name: `recursive`, `markdown`, and `token`. All implement `splitter.TextSplitter` (`Split` for raw text, `SplitDocuments` for documents with metadata).

### Recursive Character Splitter

The recursive character splitter is the recommended default for general-purpose text. It tries a hierarchy of separators (paragraph breaks, line breaks, spaces, then characters) and recursively splits at the highest-level separator that produces chunks within the size limit. The overlap parameter ensures that sentences at chunk boundaries are not lost.

```go
import (
    "context"
    "fmt"

    "github.com/lookatitude/beluga-ai/v2/rag/splitter"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func SplitRecursive(ctx context.Context, doc schema.Document) ([]schema.Document, error) {
    s := splitter.NewRecursiveSplitter(
        splitter.WithChunkSize(1000),
        splitter.WithChunkOverlap(200),
    )

    chunks, err := s.SplitDocuments(ctx, []schema.Document{doc})
    if err != nil {
        return nil, fmt.Errorf("split document: %w", err)
    }

    return chunks, nil
}
```

### Markdown-Aware Splitter

Markdown documents have explicit structure through headings. The markdown splitter splits at heading boundaries, so each chunk corresponds to a coherent section. With `WithPreserveHeaders(true)`, each chunk includes its parent headings as context, so a chunk from a deeply nested section retains the full path of headings that scope its content.

```go
func SplitMarkdown(ctx context.Context, doc schema.Document) ([]schema.Document, error) {
    s := splitter.NewMarkdownSplitter(
        splitter.WithMarkdownChunkSize(1500),
        splitter.WithMarkdownChunkOverlap(100),
        splitter.WithPreserveHeaders(true),
    )

    chunks, err := s.SplitDocuments(ctx, []schema.Document{doc})
    if err != nil {
        return nil, fmt.Errorf("split markdown: %w", err)
    }

    return chunks, nil
}
```

### Splitting Source Code

Splitting code at arbitrary character boundaries breaks function definitions and control flow, producing chunks that are hard to retrieve. Beluga AI has no language-aware code splitter, but you can get most of the benefit by giving the recursive splitter language-specific separators, so it prefers to cut at declaration boundaries first.

```go
func SplitGoCode(ctx context.Context, doc schema.Document) ([]schema.Document, error) {
    s := splitter.NewRecursiveSplitter(
        splitter.WithChunkSize(1000),
        splitter.WithChunkOverlap(100),
        splitter.WithSeparators([]string{"\nfunc ", "\ntype ", "\n\n", "\n", " "}),
    )

    chunks, err := s.SplitDocuments(ctx, []schema.Document{doc})
    if err != nil {
        return nil, fmt.Errorf("split code: %w", err)
    }

    return chunks, nil
}
```

### Token Splitter and Semantic Splitting

When your limit is a model's token budget rather than a character count, use `splitter.NewTokenSplitter(splitter.WithTokenChunkSize(...), splitter.WithTokenChunkOverlap(...), splitter.WithTokenizer(...))`.

Semantic splitting (cutting where the embedding similarity between consecutive segments drops) is not a built-in splitter. You can implement it as your own `splitter.TextSplitter` on top of an `embedding.Embedder`; [Semantic Splitting](/docs/guides/capabilities/documents/semantic-splitting/) walks through one implementation.

## Metadata Enrichment

Metadata attached to documents flows through the entire pipeline, from loading through splitting to storage. Rich metadata enables filtered searches (e.g., "find documents from the engineering team written in 2024"), debugging (tracing a chunk back to its source file), and analytics (monitoring which document types are most frequently retrieved). Investing in metadata enrichment early in the pipeline pays dividends in retrieval quality and operational visibility.

```go
func EnrichMetadata(doc schema.Document) schema.Document {
    if doc.Metadata == nil {
        doc.Metadata = map[string]any{}
    }

    // Add file metadata
    if source, ok := doc.Metadata["source"].(string); ok {
        doc.Metadata["file_extension"] = filepath.Ext(source)
        doc.Metadata["file_name"] = filepath.Base(source)
        doc.Metadata["directory"] = filepath.Dir(source)
    }

    // Add content metadata
    doc.Metadata["word_count"] = len(strings.Fields(doc.Content))
    doc.Metadata["char_count"] = len(doc.Content)
    doc.Metadata["line_count"] = strings.Count(doc.Content, "\n")

    // Add processing metadata
    doc.Metadata["processed_at"] = time.Now().Format(time.RFC3339)
    doc.Metadata["processor_version"] = "1.0"

    // Extract language (simple heuristic)
    doc.Metadata["language"] = detectLanguage(doc.Content)

    return doc
}

func detectLanguage(text string) string {
    // Simple detection based on keywords
    text = strings.ToLower(text)

    if strings.Contains(text, "func ") && strings.Contains(text, "package ") {
        return "go"
    }
    if strings.Contains(text, "def ") && strings.Contains(text, "import ") {
        return "python"
    }
    if strings.Contains(text, "function ") && strings.Contains(text, "const ") {
        return "javascript"
    }

    return "unknown"
}
```

To run this as part of loading, wrap it in a `loader.TransformerFunc` and add it to a `loader.NewPipeline` with `loader.WithTransformer`.

## Batch Processing Pipeline

Production document ingestion requires batching for efficiency, error handling for resilience, and progress tracking for observability. Processing documents one at a time wastes API call overhead (embedding models accept batches), while loading everything at once risks memory exhaustion. The batch processing pattern below processes documents in configurable groups, accumulates statistics, and continues processing when individual documents fail.

```go
type DocumentProcessor struct {
    loader    loader.DocumentLoader
    splitter  splitter.TextSplitter
    embedder  embedding.Embedder
    vectorDB  vectorstore.VectorStore
    batchSize int
}

func NewDocumentProcessor(
    l loader.DocumentLoader,
    s splitter.TextSplitter,
    emb embedding.Embedder,
    vectorDB vectorstore.VectorStore,
) *DocumentProcessor {
    return &DocumentProcessor{
        loader:    l,
        splitter:  s,
        embedder:  emb,
        vectorDB:  vectorDB,
        batchSize: 10,
    }
}

type ProcessingStats struct {
    DocsLoaded    int
    DocsProcessed int
    ChunksCreated int
    Errors        []error
    StartTime     time.Time
    EndTime       time.Time
}

// Process loads each source in turn and processes its documents in batches.
func (dp *DocumentProcessor) Process(ctx context.Context, sources []string) (*ProcessingStats, error) {
    stats := &ProcessingStats{
        StartTime: time.Now(),
    }

    var batch []schema.Document
    for _, source := range sources {
        docs, err := dp.loader.Load(ctx, source)
        if err != nil {
            stats.Errors = append(stats.Errors, fmt.Errorf("load %s: %w", source, err))
            continue
        }

        for _, doc := range docs {
            stats.DocsLoaded++
            batch = append(batch, doc)

            // Process in batches
            if len(batch) >= dp.batchSize {
                if err := dp.processBatch(ctx, batch, stats); err != nil {
                    stats.Errors = append(stats.Errors, err)
                }
                batch = nil
            }
        }
    }

    // Process remaining documents
    if len(batch) > 0 {
        if err := dp.processBatch(ctx, batch, stats); err != nil {
            stats.Errors = append(stats.Errors, err)
        }
    }

    stats.EndTime = time.Now()
    return stats, nil
}

func (dp *DocumentProcessor) processBatch(
    ctx context.Context,
    docs []schema.Document,
    stats *ProcessingStats,
) error {
    // Split documents
    allChunks, err := dp.splitter.SplitDocuments(ctx, docs)
    if err != nil {
        return fmt.Errorf("split documents: %w", err)
    }

    stats.ChunksCreated += len(allChunks)

    // Embed chunks in a single batch call
    texts := make([]string, len(allChunks))
    for i, chunk := range allChunks {
        texts[i] = chunk.Content
    }
    vecs, err := dp.embedder.Embed(ctx, texts)
    if err != nil {
        return fmt.Errorf("embed chunks: %w", err)
    }

    // Store in vector database
    if err := dp.vectorDB.Add(ctx, allChunks, vecs); err != nil {
        return fmt.Errorf("store in vector DB: %w", err)
    }

    stats.DocsProcessed += len(docs)
    fmt.Printf("Processed batch: %d docs, %d chunks\n", len(docs), len(allChunks))

    return nil
}

func (stats *ProcessingStats) Report() string {
    duration := stats.EndTime.Sub(stats.StartTime)
    rate := float64(stats.DocsProcessed) / duration.Seconds()

    return fmt.Sprintf(`Processing Report:
- Documents Loaded: %d
- Documents Processed: %d
- Chunks Created: %d
- Errors: %d
- Duration: %s
- Rate: %.2f docs/sec`,
        stats.DocsLoaded,
        stats.DocsProcessed,
        stats.ChunksCreated,
        len(stats.Errors),
        duration,
        rate,
    )
}
```

## Custom Loaders

When built-in loaders do not cover your data source, implement `loader.DocumentLoader` yourself: a single `Load(ctx context.Context, source string) ([]schema.Document, error)` method. Custom loaders integrate with the rest of the pipeline; splitters, embedders, and vector stores do not care where the documents came from. To make one available by name, register it with `loader.Register` in an `init` function.

The following example loads a CSV file, using one column as document content and the remaining columns as metadata. (For simple cases the built-in `csv` loader, `loader.NewCSVLoader(loader.WithContentColumns(...))`, already does this.)

```go
type ColumnCSVLoader struct {
    columnName string // Column to use as document content
}

// Compile-time interface check.
var _ loader.DocumentLoader = (*ColumnCSVLoader)(nil)

func NewColumnCSVLoader(columnName string) *ColumnCSVLoader {
    return &ColumnCSVLoader{columnName: columnName}
}

func (l *ColumnCSVLoader) Load(ctx context.Context, source string) ([]schema.Document, error) {
    file, err := os.Open(filepath.Clean(source))
    if err != nil {
        return nil, fmt.Errorf("open file: %w", err)
    }
    defer file.Close()

    reader := csv.NewReader(file)
    records, err := reader.ReadAll()
    if err != nil {
        return nil, fmt.Errorf("read CSV: %w", err)
    }

    if len(records) < 1 {
        return nil, fmt.Errorf("empty CSV file")
    }

    // Find column index
    header := records[0]
    columnIdx := -1
    for i, col := range header {
        if col == l.columnName {
            columnIdx = i
            break
        }
    }

    if columnIdx == -1 {
        return nil, fmt.Errorf("column not found: %s", l.columnName)
    }

    // Create documents
    var docs []schema.Document
    for i, record := range records[1:] {
        if columnIdx >= len(record) {
            continue
        }

        // Create metadata from other columns
        metadata := map[string]any{
            "source":     source,
            "row_number": i + 1,
        }

        for j, col := range header {
            if j != columnIdx && j < len(record) {
                metadata[col] = record[j]
            }
        }

        docs = append(docs, schema.Document{
            ID:       fmt.Sprintf("%s#%d", source, i+1),
            Content:  record[columnIdx],
            Metadata: metadata,
        })
    }

    return docs, nil
}
```

## Optimizing for RAG Pipelines

The most impactful tuning parameters in a RAG pipeline are chunk size and overlap. Chunks that are too small lack context for the embedding model to capture meaning. Chunks that are too large dilute the embedding with multiple topics, reducing precision. The optimal size depends on your typical query length and content density.

### Chunk Size Optimization

A useful heuristic is to size chunks at 2-3x the average query length. This ensures that the chunk's embedding captures enough context to match the query's intent without introducing unrelated content.

```go
func OptimalChunkSize(avgQueryLength int) int {
    // Rule of thumb: chunks should be 2-3x query length
    baseSize := avgQueryLength * 2

    // Clamp to reasonable bounds
    if baseSize < 200 {
        return 200
    }
    if baseSize > 2000 {
        return 2000
    }

    return baseSize
}
```

### Overlap Strategy

Overlap ensures that sentences spanning chunk boundaries are not lost. A 10-20% overlap is typically sufficient to preserve context without significantly increasing storage requirements.

```go
func CalculateOverlap(chunkSize int) int {
    // 10-20% overlap preserves context
    overlap := chunkSize / 10

    if overlap < 50 {
        return 50 // Minimum overlap
    }
    if overlap > 200 {
        return 200 // Maximum overlap
    }

    return overlap
}
```

### Metadata Filtering

Adding hierarchical metadata derived from file paths enables scoped retrieval. For example, a knowledge base organized as `engineering/backend/auth.md` can be searched with metadata filters that restrict results to the `engineering` category or the `backend` subcategory, reducing noise from unrelated document categories.

```go
// Add hierarchical metadata for filtering
func AddHierarchicalMetadata(doc schema.Document) schema.Document {
    // Extract hierarchy from file path
    source := doc.Metadata["source"].(string)
    parts := strings.Split(source, string(filepath.Separator))

    if len(parts) > 0 {
        doc.Metadata["category"] = parts[0]
    }
    if len(parts) > 1 {
        doc.Metadata["subcategory"] = parts[1]
    }
    if len(parts) > 2 {
        doc.Metadata["topic"] = parts[2]
    }

    return doc
}
```

## Error Handling

Production document pipelines process thousands of files, and individual failures should not halt the entire pipeline. The error handling pattern below categorizes errors by pipeline phase (load, split, embed, store), distinguishes transient errors that can be retried from permanent failures, and logs enough context to diagnose problems after the fact.

```go
type DocumentError struct {
    Source string
    Err    error
    Phase  string // "load", "split", "embed", "store"
}

func (e *DocumentError) Error() string {
    return fmt.Sprintf("[%s] %s: %v", e.Phase, e.Source, e.Err)
}

func ProcessWithErrorHandling(ctx context.Context, doc schema.Document) error {
    // Try to process
    if err := processDocument(ctx, doc); err != nil {
        // Log error
        docErr := &DocumentError{
            Source: doc.Metadata["source"].(string),
            Err:    err,
            Phase:  identifyPhase(err),
        }

        log.Printf("Error processing document: %v", docErr)

        // Decide whether to retry or skip
        if isRetryable(err) {
            time.Sleep(time.Second)
            return processDocument(ctx, doc)
        }

        return docErr
    }

    return nil
}

func isRetryable(err error) bool {
    // Check for transient errors
    return strings.Contains(err.Error(), "timeout") ||
        strings.Contains(err.Error(), "rate limit") ||
        strings.Contains(err.Error(), "connection refused")
}
```

## Production Best Practices

The following checklist summarizes the key considerations for deploying document processing pipelines in production environments:

1. **Process file by file** for datasets larger than available memory
2. **Process in batches** to optimize API calls and database writes
3. **Add comprehensive metadata** for filtering and debugging
4. **Choose appropriate chunk sizes** based on query patterns
5. **Implement retry logic** for transient failures
6. **Monitor processing metrics** (throughput, error rate, latency)
7. **Version your processing pipeline** to track changes
8. **Test with edge cases** (empty files, malformed content, large files)
9. **Implement checkpointing** to resume after failures
10. **Use parallel processing** where possible

## Next Steps

Now that you understand document processing:
- Learn about [RAG Pipeline](/docs/guides/capabilities/rag/rag-pipeline/) for retrieval integration
- Explore [Multimodal AI](/docs/recipes/multimodal/) for image and audio processing
- Read [RAG Recipes](/docs/recipes/rag/) for advanced patterns
- Check out [Document Loader Integrations](/docs/guides/production/integrations/document-loaders) for more sources
