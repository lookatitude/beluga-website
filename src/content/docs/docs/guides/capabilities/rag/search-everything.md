---
title: Internal Search Everything Bot
description: "Build a unified search bot that queries across Confluence, GitHub, Slack, and databases. Single interface for all enterprise knowledge."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "unified enterprise search, search bot, cross-system search, MCP search, knowledge discovery, Beluga AI, Go, internal tools"
---

Large enterprises maintain knowledge across fragmented systems — documentation in Confluence, code in GitHub, discussions in Slack, data in databases, policies in SharePoint. Each system has its own search interface with different query syntax and different result formats. Employees waste significant time switching between search interfaces, and cross-system questions ("who implemented this feature and what was the design rationale?") require manual correlation across multiple tools.

A unified search bot aggregates results from all sources, applies intelligent ranking, and provides a single interface for knowledge discovery. The orchestrator queries systems in parallel (for speed) and uses score-based ranking to merge results into a single relevance-ordered list, regardless of source.

## Solution Architecture

Beluga AI's `server` package provides HTTP adapters (the built-in `stdlib` adapter plus Gin, Chi, Echo, Fiber and others under `server/adapters/`), and `protocol/mcp` provides an MCP (Model Context Protocol) server, so the same search can be exposed as a REST endpoint and as an MCP tool. The search orchestrator queries multiple systems in parallel, aggregates results using score-based ranking, and returns unified results with source attribution and relevance scores.

Parallel querying is essential because total latency must be bounded by the slowest source, not the sum of all sources. Score-based ranking (rather than simple interleaving) ensures that a highly relevant result from one source ranks above marginally relevant results from another, regardless of which system responded first.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│     User     │───▶│  Search API  │───▶│    Search    │
│    Query     │    │ (REST/MCP)   │    │ Orchestrator │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                           ┌───────────────────┼───────────────────┐
                           │                   │                   │
                           ▼                   ▼                   ▼
                    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
                    │     Docs     │    │     Code     │    │     Wiki     │
                    │   Searcher   │    │   Searcher   │    │   Searcher   │
                    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
                           │                   │                   │
                           └───────────────────┼───────────────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │    Result    │
                                        │  Aggregator  │
                                        │   + Ranker   │
                                        └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │   Unified    │
                                        │   Results    │
                                        └──────────────┘
```

## Search Server Setup

Create the HTTP server and the MCP server:

```go
import (
    "context"
    "fmt"
    "time"

    "github.com/lookatitude/beluga-ai/v2/protocol/mcp"
    "github.com/lookatitude/beluga-ai/v2/server"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/metric"
    "go.opentelemetry.io/otel/trace"
)

type SearchEverythingBot struct {
    httpServer   server.ServerAdapter
    mcpServer    *mcp.MCPServer
    orchestrator *SearchOrchestrator
    tracer       trace.Tracer
    meter        metric.Meter
}

func NewSearchEverythingBot(ctx context.Context) (*SearchEverythingBot, error) {
    // HTTP server: the built-in "stdlib" adapter (gin, chi, echo, fiber, ...
    // are available under server/adapters/)
    httpServer, err := server.New("stdlib", server.Config{
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 30 * time.Second,
    })
    if err != nil {
        return nil, fmt.Errorf("create HTTP server: %w", err)
    }

    // MCP server exposing the search as a tool over Streamable HTTP
    mcpServer := mcp.NewServer("search-everything", "1.0.0")

    return &SearchEverythingBot{
        httpServer:   httpServer,
        mcpServer:    mcpServer,
        orchestrator: NewSearchOrchestrator(),
        tracer:       otel.Tracer("search-everything"),
        meter:        otel.Meter("search-everything"),
    }, nil
}
```

## Multi-Source Search Orchestration

Query all systems in parallel and aggregate results:

```go
import (
    "context"
    "log"
    "sort"
    "sync"
)

type SearchOrchestrator struct {
    docSearcher  *DocumentationSearcher
    codeSearcher *CodeSearcher
    wikiSearcher *WikiSearcher
    dbSearcher   *DatabaseSearcher
}

type SearchResult struct {
    Title     string
    Content   string
    Source    string // "docs", "code", "wiki", "database"
    SourceURL string
    Score     float64
    Metadata  map[string]any
}

type SourceResults struct {
    Source  string
    Results []SearchResult
    Error   error
}

func (s *SearchOrchestrator) SearchEverything(ctx context.Context, query string, limit int) ([]SearchResult, error) {
    // Search all sources in parallel
    resultsChan := make(chan SourceResults, 4)
    var wg sync.WaitGroup

    wg.Add(4)
    go func() {
        defer wg.Done()
        results, err := s.docSearcher.Search(ctx, query)
        resultsChan <- SourceResults{Source: "docs", Results: results, Error: err}
    }()

    go func() {
        defer wg.Done()
        results, err := s.codeSearcher.Search(ctx, query)
        resultsChan <- SourceResults{Source: "code", Results: results, Error: err}
    }()

    go func() {
        defer wg.Done()
        results, err := s.wikiSearcher.Search(ctx, query)
        resultsChan <- SourceResults{Source: "wiki", Results: results, Error: err}
    }()

    go func() {
        defer wg.Done()
        results, err := s.dbSearcher.Search(ctx, query)
        resultsChan <- SourceResults{Source: "database", Results: results, Error: err}
    }()

    go func() {
        wg.Wait()
        close(resultsChan)
    }()

    // Collect all results
    allResults := make([]SearchResult, 0)
    for sourceResults := range resultsChan {
        if sourceResults.Error != nil {
            log.Printf("search %s: %v", sourceResults.Source, sourceResults.Error) // continue with other sources
            continue
        }
        allResults = append(allResults, sourceResults.Results...)
    }

    // Rank and limit results
    ranked := s.rankResults(allResults, query)
    if len(ranked) > limit {
        ranked = ranked[:limit]
    }

    return ranked, nil
}

func (s *SearchOrchestrator) rankResults(results []SearchResult, query string) []SearchResult {
    // Score-based ranking combining:
    // 1. Source relevance score
    // 2. Freshness (if available in metadata)
    // 3. Query term matching
    // 4. Source authority (docs > wiki > code > database)

    sourceWeights := map[string]float64{
        "docs":     1.0,
        "wiki":     0.9,
        "code":     0.8,
        "database": 0.7,
    }

    for i := range results {
        weight := sourceWeights[results[i].Source]
        results[i].Score *= weight
    }

    // Sort by score descending
    sort.Slice(results, func(i, j int) bool {
        return results[i].Score > results[j].Score
    })

    return results
}
```

## Search API Endpoints

Expose REST and MCP interfaces:

```go
import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"

    "github.com/lookatitude/beluga-ai/v2/tool"
)

type searchInput struct {
    Query string `json:"query" description:"Search query" required:"true"`
    Limit int    `json:"limit" description:"Maximum number of results" default:"10"`
}

func (s *SearchEverythingBot) SetupAPIs(ctx context.Context) error {
    // REST endpoint: POST /api/v1/search
    search := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodPost {
            http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
            return
        }
        var req searchInput
        if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
            http.Error(w, "invalid request", http.StatusBadRequest)
            return
        }
        if req.Limit == 0 {
            req.Limit = 10
        }

        results, err := s.orchestrator.SearchEverything(r.Context(), req.Query, req.Limit)
        if err != nil {
            http.Error(w, err.Error(), http.StatusInternalServerError)
            return
        }

        w.Header().Set("Content-Type", "application/json")
        if err := json.NewEncoder(w).Encode(map[string]any{
            "query":   req.Query,
            "results": results,
            "count":   len(results),
        }); err != nil {
            http.Error(w, err.Error(), http.StatusInternalServerError)
        }
    })
    if err := s.httpServer.RegisterHandler("/api/v1/search", search); err != nil {
        return fmt.Errorf("register search handler: %w", err)
    }

    // MCP tool: the input schema is generated from searchInput's struct tags
    searchTool := tool.NewFuncTool("search_everything",
        "Search across all internal systems (docs, code, wikis, databases)",
        s.handleMCPSearch,
    )
    s.mcpServer.AddTool(searchTool)

    // Serve MCP on the same HTTP server
    if err := s.httpServer.RegisterHandler("/mcp", s.mcpServer.Handler()); err != nil {
        return fmt.Errorf("register MCP handler: %w", err)
    }

    return nil
}

func (s *SearchEverythingBot) handleMCPSearch(ctx context.Context, in searchInput) (*tool.Result, error) {
    limit := in.Limit
    if limit == 0 {
        limit = 10
    }

    results, err := s.orchestrator.SearchEverything(ctx, in.Query, limit)
    if err != nil {
        return tool.ErrorResult(err), nil
    }

    body, err := json.Marshal(map[string]any{
        "query":   in.Query,
        "results": results,
        "count":   len(results),
    })
    if err != nil {
        return nil, err
    }
    return tool.TextResult(string(body)), nil
}

// Run starts serving REST and MCP on :8080 until ctx is canceled.
func (s *SearchEverythingBot) Run(ctx context.Context) error {
    if err := s.SetupAPIs(ctx); err != nil {
        return err
    }
    return s.httpServer.Serve(ctx, ":8080")
}
```

## System-Specific Searchers

Implement adapters for each source system:

```go
import (
    "context"

    "github.com/lookatitude/beluga-ai/v2/rag/retriever"
)

type DocumentationSearcher struct {
    retriever retriever.Retriever
}

func (d *DocumentationSearcher) Search(ctx context.Context, query string) ([]SearchResult, error) {
    docs, err := d.retriever.Retrieve(ctx, query, retriever.WithTopK(20))
    if err != nil {
        return nil, err
    }

    results := make([]SearchResult, len(docs))
    for i, doc := range docs {
        title, _ := doc.Metadata["title"].(string)
        url, _ := doc.Metadata["url"].(string)
        results[i] = SearchResult{
            Title:     title,
            Content:   doc.Content,
            Source:    "docs",
            SourceURL: url,
            Score:     doc.Score, // relevance set by the retriever
            Metadata:  doc.Metadata,
        }
    }

    return results, nil
}

type CodeSearcher struct {
    retriever retriever.Retriever
}

func (c *CodeSearcher) Search(ctx context.Context, query string) ([]SearchResult, error) {
    docs, err := c.retriever.Retrieve(ctx, query, retriever.WithTopK(20))
    if err != nil {
        return nil, err
    }

    results := make([]SearchResult, len(docs))
    for i, doc := range docs {
        path, _ := doc.Metadata["file_path"].(string)
        repo, _ := doc.Metadata["repo_url"].(string)
        results[i] = SearchResult{
            Title:     path,
            Content:   doc.Content,
            Source:    "code",
            SourceURL: repo,
            Score:     doc.Score,
            Metadata:  doc.Metadata,
        }
    }

    return results, nil
}
```

## Production Considerations

### Observability

Track search metrics and source performance:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

var (
    searchTracer = otel.Tracer("search-everything")
    searchMeter  = otel.Meter("search-everything")
)

func (s *SearchOrchestrator) SearchWithObservability(ctx context.Context, query string, limit int) ([]SearchResult, error) {
    ctx, span := searchTracer.Start(ctx, "search.everything")
    defer span.End()

    span.SetAttributes(
        attribute.String("query", query),
        attribute.Int("limit", limit),
    )

    start := time.Now()
    results, err := s.SearchEverything(ctx, query, limit)
    duration := time.Since(start)

    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    span.SetAttributes(
        attribute.Int("results.count", len(results)),
        attribute.Float64("duration.ms", float64(duration.Milliseconds())),
    )

    // Create instruments once at startup in real code
    hist, err := searchMeter.Int64Histogram("search.duration")
    if err != nil {
        return nil, err
    }
    hist.Record(ctx, duration.Milliseconds())

    return results, nil
}
```

### Caching

Cache frequent queries to reduce latency:

```go
import "github.com/lookatitude/beluga-ai/v2/cache"

type CachedSearchOrchestrator struct {
    SearchOrchestrator
    cache cache.Cache
}

func (c *CachedSearchOrchestrator) SearchEverything(ctx context.Context, query string, limit int) ([]SearchResult, error) {
    cacheKey := fmt.Sprintf("search:%s:%d", query, limit)

    // Check cache first
    cached, ok, err := c.cache.Get(ctx, cacheKey)
    if err != nil {
        return nil, err
    }
    if ok {
        if results, isResults := cached.([]SearchResult); isResults {
            return results, nil
        }
    }

    // Perform search
    results, err := c.SearchOrchestrator.SearchEverything(ctx, query, limit)
    if err != nil {
        return nil, err
    }

    // Cache results for 5 minutes
    if err := c.cache.Set(ctx, cacheKey, results, 5*time.Minute); err != nil {
        return nil, err
    }

    return results, nil
}
```

### Access Control

Filter results based on user permissions:

```go
func (s *SearchOrchestrator) SearchWithAccessControl(ctx context.Context, userID, query string, limit int) ([]SearchResult, error) {
    results, err := s.SearchEverything(ctx, query, limit*2)
    if err != nil {
        return nil, err
    }

    // Filter based on user permissions
    filtered := make([]SearchResult, 0)
    for _, result := range results {
        if s.canAccess(userID, result) {
            filtered = append(filtered, result)
            if len(filtered) >= limit {
                break
            }
        }
    }

    return filtered, nil
}

func (s *SearchOrchestrator) canAccess(userID string, result SearchResult) bool {
    // Check document-level permissions
    // Implementation depends on your access control system
    return true
}
```

## Related Resources

- [Server Package Guide](/docs/guides/production/rest-deployment/) for REST and MCP APIs
- [Retriever Guide](/docs/guides/capabilities/rag/rag-strategies/) for multi-source retrieval
- [Customer Support Gateway](/docs/guides/capabilities/messaging/support-gateway/) for API gateway patterns
- [Knowledge QA System](/docs/guides/capabilities/rag/knowledge-qa/) for semantic search patterns
