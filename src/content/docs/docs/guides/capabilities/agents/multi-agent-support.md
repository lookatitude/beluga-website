---
title: Multi-Agent Customer Support System
description: "Build intelligent support with specialized agents, seamless handoffs-as-tools, and human-in-the-loop escalation in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "multi-agent support, agent handoffs, customer support AI, HITL escalation, specialized agents, Beluga AI, Go, enterprise support"
---

Customer support teams face diverse inquiries requiring different expertise — billing disputes, technical troubleshooting, account management, and general questions. A single monolithic chatbot struggles with this breadth because it must carry tools, instructions, and context for every possible domain in a single prompt. This leads to tool confusion (the agent picks the wrong tool), context dilution (important domain instructions get lost in a sea of generic instructions), and poor specialization (jack of all trades, master of none).

Multi-agent systems solve this by routing each inquiry to a specialized agent that has the right tools and context for the job, with seamless handoffs between agents when issues cross domains. Each specialist agent has a focused persona, a curated tool set, and domain-specific instructions — keeping its context lean and its tool selection accurate.

## Solution Architecture

Beluga AI's agent system models handoffs as tools — this is a core architectural decision. When a triage agent determines that an inquiry requires billing expertise, it calls a `transfer_to_billing` tool, which transparently transfers the conversation to the billing agent. The handoffs-as-tools pattern is chosen over explicit routing logic because it lets the LLM reason about when to transfer using the same mechanism it uses for any other action. The triage agent does not need special routing code; it simply has `transfer_to_*` tools alongside its other capabilities, and the LLM decides when to use them based on conversation context.

Each specialized agent has its own persona, tools, and LLM configuration optimized for its domain.

```
                    ┌─────────────────┐
                    │  Triage Agent   │
                    │  (Classify &    │
                    │   Route)        │
                    └───────┬─────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │  Billing   │ │ Technical  │ │  General   │
     │  Agent     │ │  Agent     │ │  Agent     │
     │            │ │            │ │            │
     │ Tools:     │ │ Tools:     │ │ Tools:     │
     │ - Refund   │ │ - Logs     │ │ - FAQ      │
     │ - Invoice  │ │ - Restart  │ │ - Account  │
     │ - Payment  │ │ - Diagnose │ │ - Transfer │
     └────────────┘ └────────────┘ └────────────┘
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                    ┌─────────────────┐
                    │  HITL Manager   │
                    │  (Escalate to   │
                    │   Human Agent)  │
                    └─────────────────┘
```

## Building Specialized Agents

Each agent has a focused persona, a curated set of tools, and domain-specific instructions. The `agent.Persona` struct defines the agent's role, goal, and backstory — providing the LLM with clear behavioral guidance. Tools are registered using `tool.NewFuncTool` with typed inputs (via struct tags and JSON schema generation), ensuring the LLM generates correctly structured tool calls.

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/lookatitude/beluga-ai/v2/agent"
    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    "github.com/lookatitude/beluga-ai/v2/tool"

    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
)

// createBillingAgent builds an agent specialized in billing inquiries.
func createBillingAgent(ctx context.Context) (agent.Agent, error) {
    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return nil, fmt.Errorf("create model: %w", err)
    }

    // Domain-specific tools
    refundTool := tool.NewFuncTool("process_refund",
        "Process a refund for a customer order",
        func(ctx context.Context, input RefundInput) (*tool.Result, error) {
            // Call billing system API
            refundID, err := billingAPI.ProcessRefund(ctx, input.OrderID, input.Amount)
            if err != nil {
                return tool.ErrorResult(err), nil
            }
            return tool.TextResult(fmt.Sprintf("Refund %s of $%.2f processed for order %s", refundID, input.Amount, input.OrderID)), nil
        },
    )

    invoiceTool := tool.NewFuncTool("lookup_invoice",
        "Look up invoice details by invoice or customer ID",
        func(ctx context.Context, input InvoiceInput) (*tool.Result, error) {
            invoice, err := billingAPI.GetInvoice(ctx, input.InvoiceID)
            if err != nil {
                return tool.ErrorResult(err), nil
            }
            return tool.TextResult(fmt.Sprintf("Invoice %s: $%.2f, status: %s", invoice.ID, invoice.Amount, invoice.Status)), nil
        },
    )

    billingAgent := agent.New("billing-agent",
        agent.WithPersona(agent.Persona{
            Role:      "Billing Support Specialist",
            Goal:      "Resolve billing inquiries accurately and efficiently",
            Backstory: "You handle refunds, invoice questions, and payment issues. " +
                "Always verify the customer's identity before processing financial transactions.",
        }),
        agent.WithLLM(model),
        agent.WithTools([]tool.Tool{refundTool, invoiceTool}),
    )

    return billingAgent, nil
}

type RefundInput struct {
    OrderID string  `json:"order_id" description:"The order ID to refund"`
    Amount  float64 `json:"amount" description:"Refund amount in dollars"`
}

type InvoiceInput struct {
    InvoiceID string `json:"invoice_id" description:"The invoice ID to look up"`
}
```

## Handoffs as Tools

Beluga AI implements agent transfers as tools. When you register handoff targets via `agent.WithHandoffs()` (built with `agent.HandoffTo`), Beluga automatically generates a `transfer_to_{agent_id}` tool for each target that the parent agent can call to hand off the conversation. This automatic tool generation means adding a new specialist agent is a one-line change — add a handoff and the transfer tool appears automatically.

```go
func createTriageAgent(ctx context.Context) (agent.Agent, error) {
    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        return nil, fmt.Errorf("create model: %w", err)
    }

    billingAgent, err := createBillingAgent(ctx)
    if err != nil {
        return nil, err
    }

    techAgent, err := createTechAgent(ctx)
    if err != nil {
        return nil, err
    }

    generalAgent, err := createGeneralAgent(ctx)
    if err != nil {
        return nil, err
    }

    // Triage agent with handoff targets — transfer_to_* tools are auto-generated
    triageAgent := agent.New("triage-agent",
        agent.WithPersona(agent.Persona{
            Role: "Customer Support Triage",
            Goal: "Classify customer inquiries and route to the right specialist",
            Backstory: "You are the first point of contact. Quickly determine " +
                "whether the issue is billing, technical, or general, then " +
                "transfer to the appropriate specialist agent.",
        }),
        agent.WithLLM(model),
        agent.WithHandoffs([]agent.Handoff{
            agent.HandoffTo(billingAgent, "Billing: refunds, invoices, payment issues"),
            agent.HandoffTo(techAgent, "Technical: product errors and troubleshooting"),
            agent.HandoffTo(generalAgent, "General questions"),
        }),
    )

    return triageAgent, nil
}
```

When the triage agent calls `transfer_to_billing-agent`, the framework transparently transfers the conversation along with its full context to the billing agent.

## Streaming Agent Events

Monitor agent execution in real time using Beluga AI's streaming event system:

```go
func handleInquiry(ctx context.Context, triageAgent agent.Agent, inquiry string) error {
    for event, err := range triageAgent.Stream(ctx, inquiry) {
        if err != nil {
            return fmt.Errorf("agent error: %w", err)
        }

        switch event.Type {
        case agent.EventText:
            fmt.Print(event.Text) // Stream response text
        case agent.EventToolCall:
            fmt.Printf("[Tool: %s]\n", event.ToolCall.Name)
        case agent.EventHandoff:
            fmt.Printf("[Handoff to: %s]\n", event.AgentID)
        case agent.EventDone:
            fmt.Println("\n[Done]")
        }
    }
    return nil
}
```

## Human-in-the-Loop Escalation

Not every issue can be resolved by AI. Beluga AI's HITL (Human-in-the-Loop) system provides confidence-based escalation using a policy-based approval mechanism. Policies match tool names against patterns (e.g., `process_refund` requires explicit approval, `lookup_*` is auto-approved) and evaluate risk levels. This declarative approach means escalation rules are auditable and configurable without code changes — operations teams can adjust thresholds and policies based on observed outcomes.

```go
import "github.com/lookatitude/beluga-ai/v2/hitl"

func setupEscalation(ctx context.Context) (hitl.Manager, error) {
    // "default" is the built-in in-process manager registered by the hitl package.
    manager, err := hitl.New("default", hitl.Config{DefaultTimeout: 5 * time.Minute})
    if err != nil {
        return nil, fmt.Errorf("create hitl manager: %w", err)
    }

    // Auto-approve low-risk actions, require human approval for high-risk
    err = manager.AddPolicy(hitl.ApprovalPolicy{
        Name:          "refund-approval",
        ToolPattern:   "process_refund",
        MinConfidence: 0.9,
        MaxRiskLevel:  hitl.RiskDataModification,
        RequireExplicit: true,
    })
    if err != nil {
        return nil, fmt.Errorf("add policy: %w", err)
    }

    // Read-only lookups don't need approval
    err = manager.AddPolicy(hitl.ApprovalPolicy{
        Name:          "lookup-auto-approve",
        ToolPattern:   "lookup_*",
        MinConfidence: 0.5,
        MaxRiskLevel:  hitl.RiskReadOnly,
    })
    if err != nil {
        return nil, fmt.Errorf("add policy: %w", err)
    }

    return manager, nil
}
```

When a tool execution triggers HITL review, the system pauses the agent, notifies a human reviewer, and resumes once the decision is made:

```go
func escalateToHuman(ctx context.Context, manager hitl.Manager, toolName string, input map[string]any) error {
    resp, err := manager.RequestInteraction(ctx, hitl.InteractionRequest{
        Type:        hitl.TypeApproval,
        ToolName:    toolName,
        Description: "Customer is requesting a refund over $500",
        Input:       input,
        RiskLevel:   hitl.RiskDataModification,
        Confidence:  0.75,
        Timeout:     5 * time.Minute,
    })
    if err != nil {
        return fmt.Errorf("request interaction: %w", err)
    }

    if resp.Decision != hitl.DecisionApprove {
        return fmt.Errorf("refund rejected by reviewer: %s", resp.Feedback)
    }
    return nil
}
```

## Workflow Orchestration

For complex multi-step support cases, use workflow agents to coordinate a sequence of actions:

```go
import "github.com/lookatitude/beluga-ai/v2/agent/workflow"

// Sequential workflow: verify identity → diagnose → resolve → follow up.
// Each child agent receives the previous agent's output as its input.
supportWorkflow := workflow.NewSequentialAgent("support-workflow", []agent.Agent{
    identityVerifier,
    diagnosisAgent,
    resolutionAgent,
    followUpAgent,
})

result, err := supportWorkflow.Invoke(ctx, inquiry)
if err != nil {
    return fmt.Errorf("support workflow: %w", err)
}
fmt.Println(result)
```

## Production Considerations

### Observability

Each agent execution produces OpenTelemetry spans with `gen_ai.*` attributes, making it straightforward to trace a customer inquiry through triage, handoff, tool execution, and response generation:

```go
import "go.opentelemetry.io/otel/attribute"

// Spans are automatically created for each agent invocation.
// Add custom attributes for business metrics:
span.SetAttributes(
    attribute.String("support.inquiry_type", "billing"),
    attribute.String("support.customer_tier", "enterprise"),
    attribute.Bool("support.escalated", false),
)
```

### Safety Guards

Use Beluga AI's 3-stage guard pipeline to screen agent inputs, outputs, and tool calls. The guard pipeline is always input guards first, then output guards, then tool guards — this ordering ensures that malicious inputs are caught before they reach the LLM, PII is caught before it reaches the user, and tool calls are validated before they execute.

```go
import "github.com/lookatitude/beluga-ai/v2/guard"

// Input guard: prevent prompt injection attacks
// Output guard: prevent PII leakage in responses
// Tool guard: validate tool inputs before execution
pipeline := guard.NewPipeline(
    guard.Input(guard.NewPromptInjectionDetector(), toxicityGuard),
    guard.Output(guard.NewPIIRedactor(guard.DefaultPIIPatterns...)),
    guard.Tool(authorizationGuard),
)
```

### Authentication and Authorization

Restrict agent capabilities per customer tier using Beluga AI's auth system:

```go
import "github.com/lookatitude/beluga-ai/v2/auth"

policy := auth.NewRBACPolicy("support")
if err := policy.AddRole(auth.Role{
    Name:        "enterprise",
    Permissions: []auth.Permission{auth.PermToolExec},
}); err != nil {
    return err
}
if err := policy.AssignRole(customerID, "enterprise"); err != nil {
    return err
}

// Check if agent can execute a tool for this customer
allowed, err := policy.Authorize(ctx, customerID, auth.PermToolExec, "process_refund")
if err != nil {
    return fmt.Errorf("authorize: %w", err)
}
if !allowed {
    return fmt.Errorf("customer not authorized for refund processing")
}
```

### Scaling

- **Agent pooling**: Reuse agent instances across requests. Agents are stateless between invocations when memory is externalized.
- **Concurrent execution**: Multiple inquiries execute in parallel; each gets its own context and memory scope.
- **Rate limiting**: Use Beluga AI's resilience package to rate-limit expensive tool calls (billing API, external systems).
- **Load balancing**: Deploy multiple service instances behind a load balancer. Route by customer tier for SLA compliance.

## Related Resources

- [Building Your First Agent](/docs/guides/foundations/first-agent/) for planner strategies (ReAct, Reflexion, Self-Discover)
- [Tools & MCP](/docs/guides/capabilities/agents/tools-and-mcp/) for building custom tools
- [Safety & Guards](/docs/guides/production/safety-and-guards/) for human-in-the-loop patterns
