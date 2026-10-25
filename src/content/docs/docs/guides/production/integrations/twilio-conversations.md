---
title: Twilio Conversations Integration
description: "Integrate Twilio Conversations API with Beluga AI for unified multi-channel messaging across SMS, WhatsApp, and web chat in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Twilio Conversations, multi-channel messaging, Beluga AI, SMS bot, WhatsApp AI, Twilio Go, omnichannel AI"
---

## Overview

Customers reach out through SMS, WhatsApp, and web chat -- often switching between channels mid-conversation. Twilio Conversations unifies these channels behind a single API, so one Beluga AI agent handles all of them without channel-specific logic. This reduces development effort and ensures consistent AI behavior regardless of how a customer contacts you. This guide covers connecting the Twilio Conversations API to a Beluga AI agent. Beluga does not ship a Twilio messaging provider; the integration uses the official `twilio-go` SDK for the Twilio side and a Beluga `agent` for the replies.

## Prerequisites

- Go 1.26 or later
- A Beluga AI application
- A Twilio account with Conversations API enabled
- Twilio Account SID, Auth Token, and Conversations Service SID

## Installation

Install the Twilio Go SDK:

```bash
go get github.com/twilio/twilio-go
```

Retrieve your credentials from the [Twilio Console](https://console.twilio.com) and set the required environment variables:

```bash
export TWILIO_ACCOUNT_SID="your-account-sid"
export TWILIO_AUTH_TOKEN="your-auth-token"
export TWILIO_CONVERSATIONS_SERVICE_SID="your-service-sid"
```

## Configuration

| Setting | Description | Required |
|--------|-------------|----------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (also used to verify webhook signatures) | Yes |
| `TWILIO_CONVERSATIONS_SERVICE_SID` | Conversations service SID | Yes |
| Webhook URL | Public URL of your `/webhook` endpoint, configured on the Conversations service for `onMessageAdded` | Yes, for inbound messages |

## Usage

### Create a Conversation and Send a Message

```go
package main

import (
	"fmt"
	"log"
	"os"

	"github.com/twilio/twilio-go"
	conversations "github.com/twilio/twilio-go/rest/conversations/v1"
)

func main() {
	client := twilio.NewRestClientWithParams(twilio.ClientParams{
		Username: os.Getenv("TWILIO_ACCOUNT_SID"),
		Password: os.Getenv("TWILIO_AUTH_TOKEN"),
	})
	serviceSID := os.Getenv("TWILIO_CONVERSATIONS_SERVICE_SID")

	createParams := &conversations.CreateServiceConversationParams{}
	createParams.SetFriendlyName("Customer Support")
	conv, err := client.ConversationsV1.CreateServiceConversation(serviceSID, createParams)
	if err != nil {
		log.Fatalf("failed to create conversation: %v", err)
	}

	msgParams := &conversations.CreateServiceConversationMessageParams{}
	msgParams.SetAuthor("agent")
	msgParams.SetBody("Hello from Beluga AI!")
	if _, err := client.ConversationsV1.CreateServiceConversationMessage(serviceSID, *conv.Sid, msgParams); err != nil {
		log.Fatalf("failed to send message: %v", err)
	}

	fmt.Printf("Created conversation: %s\n", *conv.Sid)
}
```

### Complete Example: Agent Replies via Webhook

Twilio posts a form-encoded `onMessageAdded` event to your webhook for each new message. The handler verifies the signature, runs the message through a Beluga agent, and posts the reply back to the same conversation:

```go
package main

import (
	"context"
	"log"
	"net/http"
	"os"

	"github.com/lookatitude/beluga-ai/v2/agent"
	"github.com/lookatitude/beluga-ai/v2/config"
	"github.com/lookatitude/beluga-ai/v2/llm"
	_ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
	"github.com/twilio/twilio-go"
	twclient "github.com/twilio/twilio-go/client"
	conversations "github.com/twilio/twilio-go/rest/conversations/v1"
)

func main() {
	authToken := os.Getenv("TWILIO_AUTH_TOKEN")
	serviceSID := os.Getenv("TWILIO_CONVERSATIONS_SERVICE_SID")
	publicURL := os.Getenv("WEBHOOK_PUBLIC_URL") // e.g. https://example.com/webhook

	client := twilio.NewRestClientWithParams(twilio.ClientParams{
		Username: os.Getenv("TWILIO_ACCOUNT_SID"),
		Password: authToken,
	})
	validator := twclient.NewRequestValidator(authToken)

	model, err := llm.New("openai", config.ProviderConfig{
		APIKey: os.Getenv("OPENAI_API_KEY"),
		Model:  "gpt-4o",
	})
	if err != nil {
		log.Fatalf("failed to create model: %v", err)
	}
	support := agent.New("support",
		agent.WithLLM(model),
		agent.WithPersona(agent.Persona{
			Role: "customer support agent",
			Goal: "answer customer questions briefly and politely",
		}),
	)

	http.HandleFunc("/webhook", func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			http.Error(w, "bad form", http.StatusBadRequest)
			return
		}
		params := make(map[string]string, len(r.PostForm))
		for k := range r.PostForm {
			params[k] = r.PostForm.Get(k)
		}
		if !validator.Validate(publicURL, params, r.Header.Get("X-Twilio-Signature")) {
			http.Error(w, "invalid signature", http.StatusForbidden)
			return
		}
		// Ignore our own messages and non-message events.
		if params["EventType"] != "onMessageAdded" || params["Author"] == "agent" {
			w.WriteHeader(http.StatusOK)
			return
		}

		reply, err := support.Invoke(context.WithoutCancel(r.Context()), params["Body"])
		if err != nil {
			log.Printf("agent error: %v", err)
			http.Error(w, "agent error", http.StatusInternalServerError)
			return
		}

		msg := &conversations.CreateServiceConversationMessageParams{}
		msg.SetAuthor("agent")
		msg.SetBody(reply)
		if _, err := client.ConversationsV1.CreateServiceConversationMessage(serviceSID, params["ConversationSid"], msg); err != nil {
			log.Printf("send error: %v", err)
		}
		w.WriteHeader(http.StatusOK)
	})

	log.Println("Webhook server listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}
```

## Advanced Topics

### Multi-Channel Support

Twilio Conversations unifies SMS, WhatsApp, and web chat behind a single API. Add participants from different channels to the same conversation:

- **SMS**: Add a phone number participant
- **WhatsApp**: Add a WhatsApp-enabled number participant
- **Web Chat**: Add a chat-based participant

The Beluga AI agent sees all messages through the same interface regardless of originating channel.

### Webhook Signature Verification

Always validate Twilio webhook signatures so requests are known to originate from Twilio. The example uses `client.NewRequestValidator` from `twilio-go` with the `X-Twilio-Signature` header; the URL passed to `Validate` must be exactly the public URL Twilio calls.

### Conversation Lifecycle

Manage conversation state transitions (active, inactive, closed) to control resource usage and agent availability. Use Twilio's conversation state API to archive completed support sessions.

### Cost Management

Monitor message volume and costs through the Twilio Console. To cap outbound message throughput, put a rate limiter in front of the send call (for example `golang.org/x/time/rate`).

## Troubleshooting

### "Invalid credentials"

Verify that `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are set correctly. Tokens can be regenerated from the Twilio Console.

### "Service not found"

Ensure the Conversations service is created in the Twilio Console and that `TWILIO_CONVERSATIONS_SERVICE_SID` matches the correct service.

## Related Resources

- [Slack Webhooks](/docs/guides/production/integrations/slack-webhooks) -- Slack messaging integration
- [Observability and Tracing](/docs/guides/production/otel-tracing/) -- OpenTelemetry setup for Beluga AI
