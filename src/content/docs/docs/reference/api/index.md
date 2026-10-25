---
title: "API Reference — Beluga AI v2"
description: "Complete API documentation for all Beluga AI v2 Go packages. Reference for core, LLM, agent, RAG, voice, and infrastructure APIs."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "API reference, documentation, Beluga AI, Go, godoc, packages, framework, agentic AI"
---

Complete API reference for all Beluga AI v2 packages. This documentation is generated from the Go source code doc comments.

## Foundation

| Package | Description |
|---------|-------------|
| [Core Package](/docs/reference/api/foundation/core/) | Foundation primitives: streams, Runnable, events, errors, lifecycle, multi-tenancy |
| [Schema Package](/docs/reference/api/foundation/schema/) | Shared types: messages, content parts, tool definitions, documents, events, sessions |
| [Config Package](/docs/reference/api/foundation/config/) | Configuration loading, validation, environment variables, and hot-reload |

## LLM & Agents

| Package | Description |
|---------|-------------|
| [LLM Package](/docs/reference/api/llm-agents/llm/) | ChatModel interface, provider registry, middleware, hooks, structured output, routing |
| [LLM Providers](/docs/reference/api/llm-agents/llm-providers/) | All LLM provider implementations: OpenAI, Anthropic, Google, Ollama, Bedrock, and more |
| [Agent Package](/docs/reference/api/llm-agents/agent/) | Agent runtime, BaseAgent, Executor, Planner strategies, handoffs, and event bus |
| [Agent Workflows](/docs/reference/api/llm-agents/agent-workflow/) | Sequential, Parallel, and Loop workflow agents for multi-agent orchestration |
| [Tool Package](/docs/reference/api/llm-agents/tool/) | Tool interface, FuncTool, registry, MCP client integration, and middleware |
| [Runtime Package](/docs/reference/api/infrastructure/runtime/) | Runner for agent lifecycle management, Team for multi-agent composition, Plugin system |

## Memory & RAG

| Package | Description |
|---------|-------------|
| [Memory Package](/docs/reference/api/memory-rag/memory/) | MemGPT-inspired 3-tier memory: Core, Recall, Archival, graph memory, composite |
| [Memory Store Providers](/docs/reference/api/memory-rag/memory-stores/) | Memory store implementations: in-memory, Redis, PostgreSQL, SQLite, MongoDB, Neo4j, Memgraph, Dragonfly |
| [RAG Embedding](/docs/reference/api/memory-rag/rag-embedding/) | Embedder interface for converting text to vector embeddings |
| [Embedding Providers](/docs/reference/api/memory-rag/rag-embedding-providers/) | Embedding provider implementations: OpenAI, Cohere, Google, Jina, Mistral, Ollama, Voyage, and more |
| [RAG Vector Store](/docs/reference/api/memory-rag/rag-vectorstore/) | VectorStore interface for similarity search over document embeddings |
| [Vector Store Providers](/docs/reference/api/memory-rag/rag-vectorstore-providers/) | Vector store implementations: pgvector, Pinecone, Qdrant, Weaviate, Milvus, Elasticsearch, and more |
| [RAG Retriever](/docs/reference/api/memory-rag/rag-retriever/) | Retriever strategies: Vector, Hybrid, HyDE, CRAG, Multi-Query, Ensemble, Rerank, Adaptive |
| [RAG Document Loaders](/docs/reference/api/memory-rag/rag-loader/) | Document loaders for files, cloud storage, APIs, and web content |
| [RAG Text Splitters](/docs/reference/api/memory-rag/rag-splitter/) | Text splitting strategies for chunking documents |

## Voice

| Package | Description |
|---------|-------------|
| [Voice Package](/docs/reference/api/voice/voice/) | Frame-based voice pipeline, VAD, hybrid cascade/S2S switching |
| [Voice STT](/docs/reference/api/voice/voice-stt/) | Speech-to-text interface and providers: Deepgram, AssemblyAI, Whisper, Groq, ElevenLabs, Gladia |
| [Voice TTS](/docs/reference/api/voice/voice-tts/) | Text-to-speech interface and providers: ElevenLabs, Cartesia, PlayHT, Fish, Groq, LMNT, Smallest |
| [Voice S2S](/docs/reference/api/voice/voice-s2s/) | Speech-to-speech interface and providers: OpenAI Realtime, Gemini Live, Nova S2S |
| [Voice Transport](/docs/reference/api/voice/voice-transport/) | Transport layer for voice sessions: WebSocket, LiveKit, Daily, Pipecat |
| [Voice VAD](/docs/reference/api/voice/voice-vad/) | Voice activity detection providers: Silero, WebRTC |

## Infrastructure

| Package | Description |
|---------|-------------|
| [Guard Package](/docs/reference/api/infrastructure/guard/) | Three-stage safety pipeline: input, output, tool guards with built-in and external providers |
| [Resilience Package](/docs/reference/api/infrastructure/resilience/) | Circuit breaker, hedge, retry, and rate limiting patterns |
| [Cache Package](/docs/reference/api/infrastructure/cache/) | Exact, semantic, and prompt caching with pluggable backends |
| [HITL Package](/docs/reference/api/infrastructure/hitl/) | Human-in-the-loop: confidence-based approval, escalation policies |
| [Auth Package](/docs/reference/api/infrastructure/auth/) | RBAC, ABAC, and capability-based security |
| [Eval Package](/docs/reference/api/infrastructure/eval/) | Evaluation framework: metrics, runners, and provider integrations |
| [State Package](/docs/reference/api/infrastructure/state/) | Shared agent state with watch and notify |
| [Prompt Package](/docs/reference/api/infrastructure/prompt/) | Prompt management, templating, and versioning |
| [Orchestration Package](/docs/reference/api/infrastructure/orchestration/) | Chain, Graph, Router, Parallel, and Supervisor orchestration patterns |
| [Workflow Package](/docs/reference/api/infrastructure/workflow/) | Durable execution engine with provider integrations |
| [Cost Package](/docs/reference/api/infrastructure/cost/) | Tracker interface for per-request/tenant/session spend, budget enforcement |
| [Audit Package](/docs/reference/api/infrastructure/audit/) | Structured audit entries for all agent actions; query by tenant and time |
| [Deploy Package](/docs/reference/api/infrastructure/deploy/) | Dockerfile/Compose generation, health endpoints, Kubernetes manifest helpers |
| [Kubernetes Package](/docs/reference/api/infrastructure/k8s/) | CRD-native operator (Agent, Team, ModelConfig resources) and Helm chart |

## Protocol & Server

| Package | Description |
|---------|-------------|
| [Protocol Package](/docs/reference/api/protocol/protocol/) | Protocol abstractions for MCP, A2A, REST, and OpenAI Agents compatibility |
| [MCP Protocol](/docs/reference/api/protocol/protocol-mcp/) | Model Context Protocol server/client, SDK, registry, and Composio integration |
| [A2A Protocol](/docs/reference/api/protocol/protocol-a2a/) | Agent-to-Agent protocol types and SDK implementation |
| [REST & OpenAI Agents](/docs/reference/api/protocol/protocol-rest/) | REST/SSE API server and OpenAI Agents protocol compatibility |
| [Server Adapters](/docs/reference/api/protocol/server/) | HTTP framework adapters: Gin, Fiber, Echo, Chi, gRPC, Connect, Huma |
| [Observability Package](/docs/reference/api/foundation/o11y/) | OpenTelemetry GenAI conventions, tracing, and provider integrations |

## Design Patterns

All extensible packages in Beluga AI v2 follow consistent patterns:

### Registry Pattern

Every extensible package provides:
- `Register(name, factory)` — register providers in `init()`
- `New(name, config)` — instantiate providers by name
- `List()` — discover available providers

### Middleware Pattern

Wrap interfaces to add cross-cutting behavior:
```go
model = llm.ApplyMiddleware(model,
    llm.WithLogging(logger),
    llm.WithProviderLimits(llm.ProviderLimits{RPM: 60}),
)
```

### Hooks Pattern

Inject lifecycle callbacks without middleware:
```go
hooks := llm.Hooks{
    BeforeGenerate: func(ctx, msgs) error { ... },
    AfterGenerate:  func(ctx, resp, err) { ... },
}
model = llm.WithHooks(model, hooks)
```

### Streaming Pattern

All streaming uses Go 1.23+ `iter.Seq2`:
```go
for chunk, err := range model.Stream(ctx, msgs) {
    if err != nil { break }
    fmt.Print(chunk.Delta)
}
```
