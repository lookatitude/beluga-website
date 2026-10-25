---
title: Scientific Paper Processing for RAG
description: "Process scientific papers with academic-aware splitting that preserves equations, citations, and section structure for accurate retrieval."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "scientific paper RAG, academic text splitting, equation preservation, citation indexing, research search, Beluga AI, Go"
---

Research institutions need to index thousands of scientific papers for literature search systems. Scientific papers have unique structural properties that standard text splitters destroy: mathematical equations contain special characters that get split mid-expression (turning `E = mc^2` into two meaningless fragments), citations like "[Smith et al., 2023]" get separated from the claims they support, and section hierarchy (Abstract, Methods, Results) provides critical retrieval context that flat chunking discards.

Academic-aware splitting respects paper structure, preserves equations and citations, and maintains semantic boundaries to enable accurate search across large paper collections. The key technique is placeholder protection: equations and citations are temporarily replaced with unique placeholders before splitting, then restored afterward. This ensures the splitter never sees or breaks these special constructs.

## Solution Architecture

Beluga AI's recursive splitter supports custom separators (`splitter.WithSeparators`); the academic-specific logic below is application code layered on top of it. The academic splitter uses section-aware separators, protects equations and citations with placeholder replacement, and enriches chunks with metadata including DOI, authors, and section names for precise source attribution.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Scientific  │───▶│    Format    │───▶│    Parser    │
│   Papers     │    │   Parser     │    │ (PDF/LaTeX/  │
│(PDF/LaTeX/MD)│    │              │    │  Markdown)   │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Embeddings  │◀───│   Academic   │◀───│   Section    │
│  + Vector    │    │   Splitter   │    │   Detector   │
│    Store     │    │ (Preserve Eq │    │              │
└──────────────┘    │  + Citations)│    └──────────────┘
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Metadata   │
                    │  Enrichment  │
                    │ (DOI/Authors)│
                    └──────────────┘
```

## Academic-Aware Splitter

Create a splitter that respects scientific paper structure:

```go
import (
    "regexp"

    "github.com/lookatitude/beluga-ai/v2/rag/splitter"
    "github.com/lookatitude/beluga-ai/v2/schema"
)

type AcademicSplitter struct {
    splitter      splitter.TextSplitter
    equationRegex *regexp.Regexp
    citationRegex *regexp.Regexp
}

func NewAcademicSplitter(chunkSize, chunkOverlap int) *AcademicSplitter {
    // Academic-specific separators that prioritize section boundaries
    separators := []string{
        "\n\n## ",          // Section headings (Markdown)
        "\n\n# ",           // Major headings
        "\n\nAbstract\n",   // Abstract section
        "\n\nIntroduction\n", // Introduction
        "\n\nMethods\n",    // Methods
        "\n\nResults\n",    // Results
        "\n\nDiscussion\n", // Discussion
        "\n\nReferences\n", // References
        "\n\n",             // Paragraphs
        "\n",               // Lines
        ". ",               // Sentences
        " ",                // Words
    }

    textSplitter := splitter.NewRecursiveSplitter(
        splitter.WithChunkSize(chunkSize),
        splitter.WithChunkOverlap(chunkOverlap),
        splitter.WithSeparators(separators),
    )

    // Regex for LaTeX and inline equations
    equationRegex := regexp.MustCompile(`\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\)`)

    // Regex for citations
    citationRegex := regexp.MustCompile(`\[[\d,\s]+\]|\([A-Z][a-z]+\s+et\s+al\.?,\s+\d{4}\)`)

    return &AcademicSplitter{
        splitter:      textSplitter,
        equationRegex: equationRegex,
        citationRegex: citationRegex,
    }
}
```

## Equation and Citation Protection

Prevent splitting of mathematical expressions and citations:

```go
import (
    "context"
    "fmt"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/schema"
)

type ProtectedContent struct {
    equations map[string]string
    citations map[string]string
}

func (a *AcademicSplitter) SplitPaper(ctx context.Context, paper Paper, content string) ([]schema.Document, error) {
    protected := &ProtectedContent{
        equations: make(map[string]string),
        citations: make(map[string]string),
    }

    // Replace equations with placeholders
    protectedContent := a.protectEquations(content, protected)

    // Replace citations with placeholders
    protectedContent = a.protectCitations(protectedContent, protected)

    // Detect sections
    sections := a.detectSections(protectedContent)

    // Split within each section
    chunks := []schema.Document{}
    for _, section := range sections {
        sectionChunks, err := a.splitter.Split(ctx, section.Content)
        if err != nil {
            return nil, fmt.Errorf("split section %s: %w", section.Name, err)
        }

        // Restore equations and citations
        for i, chunk := range sectionChunks {
            restoredContent := a.restoreProtectedContent(chunk, protected)

            doc := schema.Document{
                Content: restoredContent,
                Metadata: map[string]any{
                    "title":       paper.Title,
                    "authors":     paper.Authors,
                    "doi":         paper.DOI,
                    "section":     section.Name,
                    "chunk_index": i,
                    "chunk_total": len(sectionChunks),
                    "source":      paper.FilePath,
                },
            }
            chunks = append(chunks, doc)
        }
    }

    return chunks, nil
}

func (a *AcademicSplitter) protectEquations(text string, protected *ProtectedContent) string {
    counter := 0
    return a.equationRegex.ReplaceAllStringFunc(text, func(match string) string {
        placeholder := fmt.Sprintf("__EQUATION_%d__", counter)
        protected.equations[placeholder] = match
        counter++
        return placeholder
    })
}

func (a *AcademicSplitter) protectCitations(text string, protected *ProtectedContent) string {
    counter := 0
    return a.citationRegex.ReplaceAllStringFunc(text, func(match string) string {
        placeholder := fmt.Sprintf("__CITATION_%d__", counter)
        protected.citations[placeholder] = match
        counter++
        return placeholder
    })
}

func (a *AcademicSplitter) restoreProtectedContent(text string, protected *ProtectedContent) string {
    result := text
    for placeholder, original := range protected.equations {
        result = strings.ReplaceAll(result, placeholder, original)
    }
    for placeholder, original := range protected.citations {
        result = strings.ReplaceAll(result, placeholder, original)
    }
    return result
}
```

## Section Detection

Identify academic sections using pattern matching:

```go
import (
    "regexp"
    "strings"
)

type Section struct {
    Name    string
    Content string
    Start   int
    End     int
}

type Paper struct {
    Title    string
    Authors  []string
    DOI      string
    FilePath string
    Format   string
}

func (a *AcademicSplitter) detectSections(text string) []Section {
    sections := []Section{}

    // Common academic section patterns
    sectionPatterns := map[string]*regexp.Regexp{
        "Abstract":    regexp.MustCompile(`(?i)^\s*(abstract|summary)\s*$`),
        "Introduction": regexp.MustCompile(`(?i)^\s*(introduction|background)\s*$`),
        "Methods":     regexp.MustCompile(`(?i)^\s*(methods?|methodology)\s*$`),
        "Results":     regexp.MustCompile(`(?i)^\s*(results?|findings?)\s*$`),
        "Discussion":  regexp.MustCompile(`(?i)^\s*(discussion|analysis)\s*$`),
        "Conclusion":  regexp.MustCompile(`(?i)^\s*(conclusion|summary)\s*$`),
        "References":  regexp.MustCompile(`(?i)^\s*(references?|bibliography)\s*$`),
    }

    lines := strings.Split(text, "\n")
    currentSection := "Introduction"
    currentContent := []string{}

    for _, line := range lines {
        // Check if line matches a section header
        matchedSection := ""
        for sectionName, pattern := range sectionPatterns {
            if pattern.MatchString(strings.TrimSpace(line)) {
                // Finalize previous section
                if len(currentContent) > 0 {
                    sections = append(sections, Section{
                        Name:    currentSection,
                        Content: strings.Join(currentContent, "\n"),
                    })
                    currentContent = []string{}
                }
                matchedSection = sectionName
                break
            }
        }

        if matchedSection != "" {
            currentSection = matchedSection
        } else {
            currentContent = append(currentContent, line)
        }
    }

    // Add final section
    if len(currentContent) > 0 {
        sections = append(sections, Section{
            Name:    currentSection,
            Content: strings.Join(currentContent, "\n"),
        })
    }

    return sections
}
```

## Multi-Format Parsing

Support PDF, LaTeX, and Markdown papers:

```go
import (
    "context"
    "fmt"
    "os"
    "path/filepath"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/rag/loader"
    "github.com/lookatitude/beluga-ai/v2/schema"

    _ "github.com/lookatitude/beluga-ai/v2/rag/loader/providers/docling"
)

type FormatParser interface {
    Parse(ctx context.Context, filePath string) (Paper, string, error)
}

func ParsePaper(ctx context.Context, filePath string) (Paper, string, error) {
    ext := filepath.Ext(filePath)

    var parser FormatParser
    switch ext {
    case ".pdf":
        pdfParser, err := NewPDFParser()
        if err != nil {
            return Paper{}, "", err
        }
        parser = pdfParser
    case ".tex", ".latex":
        parser = NewLaTeXParser()
    case ".md", ".markdown":
        parser = NewMarkdownParser()
    default:
        return Paper{}, "", fmt.Errorf("unsupported format: %s", ext)
    }

    paper, content, err := parser.Parse(ctx, filePath)
    if err != nil {
        return Paper{}, "", fmt.Errorf("parse paper: %w", err)
    }

    paper.FilePath = filePath
    paper.Format = ext
    return paper, content, nil
}

type PDFParser struct {
    loader loader.DocumentLoader
}

// NewPDFParser converts PDFs to text through a Docling server.
// Beluga AI has no built-in PDF parser; "docling" and "unstructured"
// are the document-conversion loaders that handle PDFs.
func NewPDFParser() (*PDFParser, error) {
    pdfLoader, err := loader.New("docling", config.ProviderConfig{
        BaseURL: os.Getenv("DOCLING_URL"),
    })
    if err != nil {
        return nil, fmt.Errorf("create pdf loader: %w", err)
    }
    return &PDFParser{loader: pdfLoader}, nil
}

func (p *PDFParser) Parse(ctx context.Context, filePath string) (Paper, string, error) {
    docs, err := p.loader.Load(ctx, filePath)
    if err != nil {
        return Paper{}, "", err
    }

    // Extract metadata from first page or PDF properties
    paper := Paper{
        Title:   extractTitle(docs),
        Authors: extractAuthors(docs),
        DOI:     extractDOI(docs),
    }

    // Concatenate all pages
    var content strings.Builder
    for _, doc := range docs {
        content.WriteString(doc.Content)
        content.WriteString("\n")
    }

    return paper, content.String(), nil
}

func extractTitle(docs []schema.Document) string {
    // Extract title from first page or metadata
    if len(docs) > 0 {
        if title, ok := docs[0].Metadata["title"].(string); ok {
            return title
        }
    }
    return ""
}

func extractAuthors(docs []schema.Document) []string {
    // Extract authors from metadata
    if len(docs) > 0 {
        if authors, ok := docs[0].Metadata["authors"].([]string); ok {
            return authors
        }
    }
    return []string{}
}

func extractDOI(docs []schema.Document) string {
    // Extract DOI from metadata or text
    if len(docs) > 0 {
        if doi, ok := docs[0].Metadata["doi"].(string); ok {
            return doi
        }
    }
    return ""
}
```

## Production Considerations

### Observability

Track processing metrics and section detection accuracy:

```go
import (
    "time"

    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
)

var (
    tracer = otel.Tracer("paper-indexer")
    meter  = otel.Meter("paper-indexer")
)

func ProcessPaperWithObservability(ctx context.Context, filePath string) ([]schema.Document, error) {
    ctx, span := tracer.Start(ctx, "paper.process")
    defer span.End()

    span.SetAttributes(
        attribute.String("file.path", filePath),
        attribute.String("file.ext", filepath.Ext(filePath)),
    )

    start := time.Now()

    paper, content, err := ParsePaper(ctx, filePath)
    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    chunks, err := NewAcademicSplitter(1500, 200).SplitPaper(ctx, paper, content)
    if err != nil {
        span.RecordError(err)
        return nil, err
    }

    duration := time.Since(start)

    span.SetAttributes(
        attribute.String("paper.title", paper.Title),
        attribute.String("paper.doi", paper.DOI),
        attribute.Int("chunks.count", len(chunks)),
        attribute.Float64("duration.ms", float64(duration.Milliseconds())),
    )

    // Create instruments once at startup in real code
    hist, err := meter.Int64Histogram("paper.process.duration")
    if err != nil {
        return nil, err
    }
    hist.Record(ctx, duration.Milliseconds())

    return chunks, nil
}
```

### Batch Processing

Process large paper collections efficiently:

```go
func ProcessPaperBatch(ctx context.Context, filePaths []string) error {
    batchSize := 10
    for i := 0; i < len(filePaths); i += batchSize {
        end := min(i+batchSize, len(filePaths))
        batch := filePaths[i:end]

        var wg sync.WaitGroup
        for _, filePath := range batch {
            wg.Add(1)
            go func(path string) {
                defer wg.Done()
                chunks, err := ProcessPaperWithObservability(ctx, path)
                if err != nil {
                    log.Printf("process %s: %v", path, err) // continue with the batch
                    return
                }
                // Store chunks in vector database (embed + VectorStore.Add)
                if err := storeChunks(ctx, chunks); err != nil {
                    log.Printf("store %s: %v", path, err)
                }
            }(filePath)
        }
        wg.Wait()
    }
    return nil
}
```

### Chunk Quality Validation

Verify equation and citation preservation:

```go
func ValidateChunkQuality(chunks []schema.Document, originalContent string) error {
    // Count equations in original
    equationRegex := regexp.MustCompile(`\$\$.*?\$\$|\$.*?\$`)
    originalEquations := equationRegex.FindAllString(originalContent, -1)

    // Count equations in chunks
    var chunkEquations []string
    for _, chunk := range chunks {
        equations := equationRegex.FindAllString(chunk.Content, -1)
        chunkEquations = append(chunkEquations, equations...)
    }

    if len(originalEquations) != len(chunkEquations) {
        return fmt.Errorf("equation count mismatch: original=%d, chunks=%d",
            len(originalEquations), len(chunkEquations))
    }

    return nil
}
```

## Related Resources

- [Text Splitter Guide](/docs/guides/capabilities/documents/semantic-splitting/) for splitting strategies
- [Large Repository RAG](/docs/guides/capabilities/rag/rag-large-repos/) for code-aware splitting
- [RAG Pipeline Guide](/docs/guides/capabilities/rag/rag-pipeline/) for complete RAG setup
- [Document Loader Guide](/docs/guides/production/integrations/document-loaders/) for format parsing
