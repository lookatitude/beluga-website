---
title: Document Loaders
description: "Load documents from filesystems, cloud storage, databases, and APIs into Beluga AI RAG pipelines for embedding and retrieval."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "document loaders, Beluga AI, file ingestion, cloud storage loader, RAG pipeline, data loading Go, document processing"
---

Before documents can be embedded and searched, they need to be loaded from wherever they live -- local filesystems, cloud storage buckets, databases, APIs, or SaaS platforms. Document loaders handle this ingestion step, converting source data into Beluga AI's `schema.Document` type with content and metadata preserved.

This guide covers the loaders that ship with Beluga AI and shows how to implement custom loaders for sources that are not covered.

Every loader implements one interface from `rag/loader`:

```go
type DocumentLoader interface {
    Load(ctx context.Context, source string) ([]schema.Document, error)
}
```

The `source` argument is loader-specific: a file path for the built-in loaders, an `s3://` / `gs://` / `az://` URL for cloud storage, a file ID for Google Drive, or a URL for web crawlers.

## Built-in Loaders

The `rag/loader` package registers four format loaders in `init()`: `text`, `markdown`, `csv`, and `json`. Create them through the registry with `loader.New`, or construct them directly.

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
)

func main() {
    ctx := context.Background()

    // Registry-based construction.
    textLoader, err := loader.New("text", config.ProviderConfig{})
    if err != nil {
        log.Fatal(err)
    }
    docs, err := textLoader.Load(ctx, "/path/to/notes.txt")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("loaded %d text documents\n", len(docs))

    // Direct construction with options.
    csvLoader := loader.NewCSVLoader(loader.WithContentColumns("title,body"))
    rows, err := csvLoader.Load(ctx, "/path/to/articles.csv")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("loaded %d CSV rows\n", len(rows))

    jsonLoader := loader.NewJSONLoader(
        loader.WithJQPath("data.items"), // dot path to the array of items
        loader.WithContentKey("content"), // key holding each item's text
    )
    items, err := jsonLoader.Load(ctx, "/path/to/export.json")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("loaded %d JSON items\n", len(items))
}
```

- **text**: the whole file becomes one document.
- **markdown**: `loader.NewMarkdownLoader()`; the whole file becomes one document.
- **csv**: one document per row; column headers become metadata keys. `WithContentColumns` (or `Options["content_columns"]`) picks the columns concatenated into `Content`.
- **json**: an array (top level or at `WithJQPath`) yields one document per element; `WithContentKey` selects the content field, otherwise the whole element is serialized.

### Pipelines and Transformers

`loader.NewPipeline` runs several loaders against the same source and applies transformers to every resulting document:

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

func main() {
    ctx := context.Background()

    p := loader.NewPipeline(
        loader.WithLoader(loader.NewMarkdownLoader()),
        loader.WithTransformer(loader.TransformerFunc(
            func(ctx context.Context, doc schema.Document) (schema.Document, error) {
                if doc.Metadata == nil {
                    doc.Metadata = map[string]any{}
                }
                doc.Metadata["ingested_at"] = time.Now().UTC().Format(time.RFC3339)
                return doc, nil
            },
        )),
    )

    docs, err := p.Load(ctx, "/path/to/README.md")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("loaded %d documents\n", len(docs))
}
```

There is no built-in directory walker. To ingest a directory, walk it with `filepath.WalkDir` and call the loader that matches each file's extension.

## External Loaders

Provider loaders live under `rag/loader/providers/` and register themselves when imported. All of them are created with `loader.New(name, config.ProviderConfig{...})`.

| Name | Import | Source argument | Configuration |
|------|--------|-----------------|---------------|
| `cloudstorage` | `rag/loader/providers/cloudstorage` | `s3://bucket/key`, `gs://bucket/key`, `az://container/key` | `APIKey` (access key), `Options["secret_key"]`, `Options["region"]` |
| `gdrive` | `rag/loader/providers/gdrive` | Drive file ID | `APIKey` (API key or OAuth token) |
| `firecrawl` | `rag/loader/providers/firecrawl` | URL to crawl | `APIKey` |
| `docling` | `rag/loader/providers/docling` | file path or URL (PDF, DOCX, images) | `BaseURL` of a Docling server |
| `unstructured` | `rag/loader/providers/unstructured` | file path | `APIKey`, optional `BaseURL` |
| `confluence` | `rag/loader/providers/confluence` | page ID | `APIKey`, `BaseURL` (wiki URL), `Options["user"]` |
| `github` | `rag/loader/providers/github` | `owner/repo/path/to/file` | `APIKey` (personal access token) |
| `notion` | `rag/loader/providers/notion` | page ID | `APIKey` (integration token) |

### Cloud Storage

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/cloudstorage"
)

func main() {
    ctx := context.Background()

    l, err := loader.New("cloudstorage", config.ProviderConfig{
        APIKey: os.Getenv("STORAGE_ACCESS_TOKEN"),
        Options: map[string]any{
            "region": "us-west-2",
        },
    })
    if err != nil {
        log.Fatal(err)
    }

    docs, err := l.Load(ctx, "gs://my-bucket/documents/handbook.md")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("loaded %d documents\n", len(docs))
}
```

The cloud storage loader fetches one object per `Load` call (it does not list prefixes) and sends `APIKey` as a bearer token. It does not perform AWS SigV4 request signing, so for private S3 objects either make the object readable to the request or download it with the AWS SDK and pass the content to a format loader.

### Google Drive and Web Crawling

```go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/firecrawl"
    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/gdrive"
)

func main() {
    ctx := context.Background()

    drive, err := loader.New("gdrive", config.ProviderConfig{
        APIKey: os.Getenv("GOOGLE_OAUTH_TOKEN"),
    })
    if err != nil {
        log.Fatal(err)
    }
    driveDocs, err := drive.Load(ctx, "your-file-id")
    if err != nil {
        log.Fatal(err)
    }

    crawler, err := loader.New("firecrawl", config.ProviderConfig{
        APIKey: os.Getenv("FIRECRAWL_API_KEY"),
    })
    if err != nil {
        log.Fatal(err)
    }
    webDocs, err := crawler.Load(ctx, "https://example.com/docs")
    if err != nil {
        log.Fatal(err)
    }

    fmt.Printf("drive: %d, web: %d\n", len(driveDocs), len(webDocs))
}
```

Google Docs files are exported as plain text; other files are downloaded as-is.

## Implementing Custom Loaders

For sources that are not covered (SQL databases, internal APIs, SaaS platforms), implement `loader.DocumentLoader` and optionally register it so it can be created by name.

```go
package custom

import (
    "context"
    "database/sql"
    "fmt"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

// SQLLoader turns rows of a query into documents. The source argument is
// the SQL query to run; it must return id, title and content columns.
type SQLLoader struct {
    db *sql.DB
}

var _ loader.DocumentLoader = (*SQLLoader)(nil)

func NewSQLLoader(db *sql.DB) *SQLLoader {
    return &SQLLoader{db: db}
}

func (l *SQLLoader) Load(ctx context.Context, query string) ([]schema.Document, error) {
    rows, err := l.db.QueryContext(ctx, query)
    if err != nil {
        return nil, fmt.Errorf("sql loader: query: %w", err)
    }
    defer rows.Close()

    var docs []schema.Document
    for rows.Next() {
        var id, title, content string
        if err := rows.Scan(&id, &title, &content); err != nil {
            return nil, fmt.Errorf("sql loader: scan: %w", err)
        }
        docs = append(docs, schema.Document{
            ID:      id,
            Content: content,
            Metadata: map[string]any{
                "source": "sql",
                "title":  title,
            },
        })
    }
    if err := rows.Err(); err != nil {
        return nil, fmt.Errorf("sql loader: rows: %w", err)
    }
    return docs, nil
}

// Register makes the loader available as loader.New("sql", cfg).
// The DSN comes from cfg.BaseURL and the driver from Options["driver"].
func init() {
    loader.Register("sql", func(cfg config.ProviderConfig) (loader.DocumentLoader, error) {
        driver, ok := config.GetOption[string](cfg, "driver")
        if !ok {
            return nil, fmt.Errorf("sql loader: Options[\"driver\"] is required")
        }
        db, err := sql.Open(driver, cfg.BaseURL)
        if err != nil {
            return nil, fmt.Errorf("sql loader: open: %w", err)
        }
        return NewSQLLoader(db), nil
    })
}
```

`DocumentLoader` returns a slice. For very large sources, page through the source in your own code and call `Load` once per page (for example, pass the page cursor in `source`), so each batch can be embedded and indexed before the next is fetched.

## Event-Driven Loading

Load documents reactively as they arrive. The excerpt below polls an SQS queue for S3 notifications and hands each object to a loader. `parseS3Event` and `processDocuments` are application code.

```go
type S3EventLoader struct {
    sqsClient *sqs.SQS
    queueURL  string
    loader    loader.DocumentLoader // e.g. loader.New("cloudstorage", ...)
}

func (sel *S3EventLoader) ProcessEvents(ctx context.Context) error {
    for {
        result, err := sel.sqsClient.ReceiveMessageWithContext(ctx, &sqs.ReceiveMessageInput{
            QueueUrl:            aws.String(sel.queueURL),
            MaxNumberOfMessages: aws.Int64(10),
            WaitTimeSeconds:     aws.Int64(20),
        })
        if err != nil {
            return err
        }

        for _, msg := range result.Messages {
            event, err := parseS3Event(msg.Body)
            if err != nil {
                log.Printf("parse event: %v", err)
                continue
            }

            docs, err := sel.loader.Load(ctx, "s3://"+event.Bucket+"/"+event.ObjectKey)
            if err != nil {
                log.Printf("load document: %v", err)
                continue
            }

            if err := processDocuments(ctx, docs); err != nil {
                log.Printf("process documents: %v", err)
                continue
            }

            if _, err := sel.sqsClient.DeleteMessageWithContext(ctx, &sqs.DeleteMessageInput{
                QueueUrl:      aws.String(sel.queueURL),
                ReceiptHandle: msg.ReceiptHandle,
            }); err != nil {
                log.Printf("delete message: %v", err)
            }
        }

        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
        }
    }
}
```

## Best Practices

When working with document loaders:

1. **Page through large sources** instead of loading everything at once
2. **Implement retry logic** for network failures
3. **Add rate limiting** to respect API limits
4. **Cache credentials** securely
5. **Validate document content** before processing
6. **Track loading metrics** (throughput, errors)
7. **Handle pagination** correctly
8. **Process in batches** for efficiency
9. **Add comprehensive metadata** for filtering
10. **Implement checkpointing** for resumability

## Next Steps

- Learn about [Text Splitter Integrations](/docs/reference/api/memory-rag/rag-splitter/) for chunking
- Explore [Document Processing](/docs/guides/capabilities/documents/document-processing/) for complete pipelines
- Read [RAG Pipeline](/docs/guides/capabilities/rag/rag-pipeline/) for integration patterns
