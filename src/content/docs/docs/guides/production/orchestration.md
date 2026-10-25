---
title: Orchestration & Workflows
description: "Coordinate agents with sequential pipelines, parallel fan-out, LLM-driven handoffs, supervisor delegation, and workflow execution with activity retries, signals, and pluggable durable backends."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Beluga AI, Go, orchestration, workflows, sequential agent, parallel, handoffs, durable execution"
---

Beluga provides multiple orchestration patterns for coordinating agents, each designed for a specific type of coordination problem. Deterministic patterns (sequential, parallel, loop) provide predictable execution when you know the steps in advance. LLM-driven patterns (handoffs, supervisor) enable dynamic routing when the execution path depends on the input. Workflows add activity retries, timeouts, and signals for long-running processes; run them on a durable provider such as Temporal when they must survive restarts.

Choosing the right pattern depends on two questions: Does the execution path change based on input? And does the workflow need to survive process restarts? The decision table at the end of this guide maps common scenarios to recommended patterns.

## Workflow Agents

The `agent/workflow` package provides deterministic orchestration patterns that compose child agents without LLM reasoning. These patterns execute in a predictable order, making them suitable for pipelines where the steps are known at build time and only the content changes between runs.

### Sequential Agent

Sequential agents run a series of agents in order, passing the output of each as the input to the next. This is the natural choice for pipelines where each step transforms or enriches the result: research feeds into writing, writing feeds into review. The key constraint is that each agent receives only the previous agent's output, not the full history.

```go
import (
	"github.com/lookatitude/beluga-ai/v2/agent"
	"github.com/lookatitude/beluga-ai/v2/agent/workflow"
)

researcher := agent.New("researcher",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "research analyst"}),
	agent.WithTools([]tool.Tool{searchTool}),
)

writer := agent.New("writer",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "technical writer"}),
)

reviewer := agent.New("reviewer",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "editor"}),
)

// Run: researcher → writer → reviewer
pipeline := workflow.NewSequentialAgent("content-pipeline",
	[]agent.Agent{researcher, writer, reviewer},
)

result, err := pipeline.Invoke(ctx, "Write a blog post about Go generics")
```

### Parallel Agent

When subtasks are independent of each other, running them concurrently reduces total latency. The parallel agent fans out the same input to all child agents simultaneously and aggregates their results. This pattern works well for tasks like multi-perspective analysis, where each agent examines the input from a different angle and the combined output is richer than any single agent's response.

```go
sentimentAgent := agent.New("sentiment",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "sentiment analyst"}),
)

topicAgent := agent.New("topics",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "topic classifier"}),
)

entityAgent := agent.New("entities",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "entity extractor"}),
)

// Run all three in parallel
parallel := workflow.NewParallelAgent("text-analysis",
	[]agent.Agent{sentimentAgent, topicAgent, entityAgent},
)

result, err := parallel.Invoke(ctx, "Analyze this customer feedback: ...")
// Result contains aggregated output from all three agents
```

### Loop Agent

The loop agent repeatedly invokes the same agent until a stop condition is met or a maximum iteration count is reached. This pattern is essential for iterative refinement tasks like code review, where the agent improves its output over multiple passes. The stop condition function inspects each iteration's output to decide whether the result is satisfactory.

```go
improver := agent.New("improver",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{
		Role: "code reviewer and improver",
		Goal: "iteratively improve code quality",
	}),
)

loop := workflow.NewLoopAgent("refinement-loop",
	improver,
	workflow.WithLoopMaxIterations(3),
	workflow.WithLoopCondition(func(iteration int, result string) bool {
		return strings.Contains(result, "APPROVED")
	}),
)

result, err := loop.Invoke(ctx, "Review and improve this code: ...")
```

## Handoffs (Agent Transfers)

Handoffs let the LLM dynamically decide when to route a conversation to a specialist agent. Unlike the deterministic patterns above, handoffs delegate the routing decision to the model, which makes them suitable for scenarios where the right specialist depends on conversational context rather than a predefined rule.

Handoffs are implemented as tools because the LLM already knows how to call tools. Each handoff automatically generates a `transfer_to_{name}` tool that the model can invoke when it determines a specialist would handle the conversation better. This design means no new routing concepts are needed: the model uses the same tool-calling mechanism it already understands.

```go
billingAgent := agent.New("billing",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "billing specialist"}),
)

techAgent := agent.New("tech-support",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{Role: "technical support engineer"}),
)

// Triage agent routes dynamically based on user input
triage := agent.New("triage",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{
		Role: "customer service triage",
		Goal: "route customers to the right specialist",
	}),
	agent.WithHandoffs([]agent.Handoff{
		agent.HandoffTo(billingAgent, "Transfer billing questions to the billing specialist"),
		agent.HandoffTo(techAgent, "Transfer technical issues to tech support"),
	}),
)

// The LLM sees these as tools:
//   transfer_to_billing: "Transfer billing questions..."
//   transfer_to_tech-support: "Transfer technical issues..."
result, err := triage.Invoke(ctx, "I was charged twice on my last invoice")
```

### Conditional Handoffs

Not all handoffs should be available at all times. Conditional handoffs control availability dynamically based on runtime context, such as user tier, feature flags, or system state. The `IsEnabled` function is evaluated before each tool call, so handoffs can appear and disappear based on the current request context.

```go
handoff := agent.Handoff{
	TargetAgent: premiumAgent,
	Description: "Transfer to premium support",
	IsEnabled: func(ctx context.Context) bool {
		// userFromContext is your application's helper that reads the
		// authenticated user your middleware stored in ctx.
		user := userFromContext(ctx)
		return user != nil && user.Tier == "premium"
	},
	OnHandoff: func(ctx context.Context) error {
		log.Println("Transferring to premium support")
		return nil
	},
	InputFilter: func(input agent.HandoffInput) agent.HandoffInput {
		// Add context for the target agent
		input.Context = map[string]any{"priority": "high"}
		return input
	},
}
```

## Supervisor Pattern

The supervisor pattern combines LLM-driven planning with structured delegation. A supervisor agent receives a high-level goal, uses LLM reasoning to decompose it into tasks, and delegates each task to a worker agent via handoffs. This pattern is suited for complex goals where the decomposition itself requires intelligence, not just rule-based routing.

Unlike simple handoffs where the model routes to one specialist, the supervisor orchestrates multiple specialists in sequence or parallel, synthesizing their outputs into a coherent result.

```go
// Worker agents
worker1 := agent.New("data-collector",
	agent.WithLLM(model),
	agent.WithTools([]tool.Tool{apiTool}),
)

worker2 := agent.New("analyzer",
	agent.WithLLM(model),
	agent.WithTools([]tool.Tool{calculatorTool}),
)

// Supervisor decides how to delegate
supervisor := agent.New("supervisor",
	agent.WithLLM(model),
	agent.WithPersona(agent.Persona{
		Role: "project supervisor",
		Goal: "coordinate workers to complete complex tasks",
	}),
	agent.WithChildren([]agent.Agent{worker1, worker2}),
	agent.WithHandoffs([]agent.Handoff{
		agent.HandoffTo(worker1, "Delegate data collection tasks"),
		agent.HandoffTo(worker2, "Delegate analysis tasks"),
	}),
)
```

## Event Bus

The agent `EventBus` interface (with the in-process `InMemoryBus` implementation) enables decoupled, asynchronous communication between agents. Instead of direct invocations, agents publish events to named topics and subscribe to the topics they care about. This pattern supports reactive architectures where adding a new agent requires only subscribing to existing topics, with no changes to publishers.

The tradeoff is reduced visibility into the overall workflow: since there is no central orchestrator, you must rely on event tracing and correlation IDs to reconstruct the execution path.

```go
bus := agent.NewInMemoryBus()

// Subscribe to events
sub, err := bus.Subscribe(ctx, "task.complete", func(event agent.AgentEvent) {
	log.Printf("Task completed by %s: %v", event.SourceID, event.Payload)
})
if err != nil {
	return err
}
defer sub.Unsubscribe()

// Publish events from agents
if err := bus.Publish(ctx, "task.complete", agent.AgentEvent{
	Type:      "task.complete",
	SourceID:  "researcher",
	Payload:   "Research phase finished",
	Timestamp: time.Now(),
}); err != nil {
	return err
}
```

## Durable Workflows

The `workflow` package provides a workflow engine for long-running, signal-driven work. A workflow is a plain Go function that receives a `workflow.WorkflowContext`; each unit of work runs as an activity through `ExecuteActivity`, with optional per-activity retry and timeout. The built-in `DefaultExecutor` runs workflows in-process, and external providers (Temporal, Dapr, Inngest, Kafka, NATS) plug in through the same `workflow.DurableExecutor` interface via the registry.

```go
import (
	"github.com/lookatitude/beluga-ai/v2/workflow"
	"github.com/lookatitude/beluga-ai/v2/workflow/providers/inmemory"
)

// Each step is an activity: func(ctx context.Context, input any) (any, error)
func ingest(ctx context.Context, input any) (any, error)  { return "documents loaded", nil }
func process(ctx context.Context, input any) (any, error) { return "documents processed", nil }
func publish(ctx context.Context, input any) (any, error) { return "published", nil }

func DocumentProcessing(ctx workflow.WorkflowContext, input any) (any, error) {
	retry := workflow.WithActivityRetry(workflow.DefaultRetryPolicy())
	out := input
	for _, step := range []workflow.ActivityFunc{ingest, process, publish} {
		var err error
		out, err = ctx.ExecuteActivity(step, out, retry, workflow.WithActivityTimeout(2*time.Minute))
		if err != nil {
			return nil, err
		}
	}
	return out, nil
}

executor := workflow.NewExecutor(workflow.WithStore(inmemory.New()))

handle, err := executor.Execute(ctx, DocumentProcessing, workflow.WorkflowOptions{
	ID:      "document-processing-42",
	Input:   "start processing",
	Timeout: 30 * time.Minute,
})
if err != nil {
	return err
}
result, err := handle.Result(ctx)
```

### Execution Features

| Feature | Description |
|---------|-------------|
| **Retries** | Per-activity retry with exponential backoff (`WithActivityRetry`) |
| **Timeouts** | Per-activity (`WithActivityTimeout`) and whole-workflow (`WorkflowOptions.Timeout`) |
| **Signals** | External events delivered with `executor.Signal` and consumed with `ctx.ReceiveSignal` |
| **Timers** | `ctx.Sleep` inside workflows |
| **State store** | Workflow state saved to the configured `WorkflowStore` |

The built-in executor saves workflow state when a run starts and when it finishes; it does not yet replay recorded activity results after a process crash. If a workflow must survive restarts mid-run without repeating expensive LLM calls, run it on a durable provider such as Temporal (`workflow.New("temporal", ...)`).

## Streaming Across Orchestration

All workflow agents support Beluga's `iter.Seq2` streaming pattern. Streaming is particularly valuable in orchestration because it provides real-time visibility into which agent is currently active and what it is producing. Without streaming, the user would see nothing until the entire multi-agent pipeline completes.

```go
for event, err := range pipeline.Stream(ctx, "Build a marketing report") {
	if err != nil {
		log.Fatal(err)
		break
	}

	switch event.Type {
	case agent.EventText:
		fmt.Print(event.Text)
	case agent.EventHandoff:
		fmt.Printf("\n[Handed off to: %s]\n", event.AgentID)
	case agent.EventToolCall:
		fmt.Printf("\n[Tool: %s]\n", event.ToolCall.Name)
	}
}
```

## Choosing an Orchestration Pattern

Use this table to match your coordination requirements to the appropriate pattern. The "Decision Maker" column indicates whether execution order is fixed at build time (deterministic) or determined by the LLM at runtime.

| Pattern | Decision Maker | Best For |
|---------|---------------|----------|
| **Sequential** | Deterministic | Linear pipelines where each step transforms the previous output |
| **Parallel** | Deterministic | Independent subtasks that can run concurrently for lower latency |
| **Loop** | Condition-based | Iterative refinement until a quality threshold is met |
| **Handoff** | LLM-driven | Dynamic routing to specialists based on conversational context |
| **Supervisor** | LLM-driven | Complex goals requiring decomposition, delegation, and synthesis |
| **Durable Workflow** | Deterministic | Long-running, signal-driven processes (use a durable provider such as Temporal to survive restarts) |

## Next Steps

- [Building Your First Agent](/docs/guides/foundations/first-agent/) — Single agent fundamentals
- [Tools & MCP](/docs/guides/capabilities/agents/tools-and-mcp/) — Tool system for agents
- [Safety & Guards](/docs/guides/production/safety-and-guards/) — Guard multi-agent systems
- [Deploying to Production](/docs/guides/production/deployment/) — Production orchestration
