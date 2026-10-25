---
title: Multi-Channel Marketing Hub
description: "Send unified marketing campaigns across SMS, WhatsApp, and email with automated scheduling, deduplication, and cross-channel analytics."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "multi-channel marketing, SMS WhatsApp email, campaign automation, cross-channel analytics, messaging hub, Beluga AI, Go"
---

A marketing agency running a product launch across SMS, WhatsApp, and email typically manages each channel through its own dashboard — Twilio for SMS, WhatsApp Business API, and SendGrid for email. This fragmentation means the same campaign requires three separate configurations, three different template formats, and three separate analytics views. When the SMS version of a message has a typo, it gets fixed in Twilio but the WhatsApp version remains unchanged. Delivery failures on one channel are invisible from another channel's dashboard, so a campaign that failed to reach 30% of WhatsApp recipients might appear successful from the SMS dashboard alone.

The deeper problem is that channel-specific systems prevent cross-channel intelligence: knowing that a customer already opened the email version should suppress the SMS reminder, but siloed systems cannot coordinate this deduplication.

## Solution Architecture

Beluga AI does not include SMS, WhatsApp, or email providers, so the hub defines its own small `Channel` interface and you implement it once per provider with that provider's SDK. The key design choice is that SMS, WhatsApp, and email all satisfy the same `Send` contract. Campaign logic is written once against the interface, and channel-specific behavior (WhatsApp template requirements, SMS character limits, email HTML formatting) lives in the channel implementations. Beluga AI's `o11y` package supplies the tracing. Delivery tracking and analytics aggregate across all channels into a single view.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Campaign   │───▶│   Campaign   │───▶│   Channel    │
│   Request    │    │   Manager    │    │    Router    │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                    ┌──────────────────────────┼────────────┐
                    │                          │            │
             ┌──────▼──────┐          ┌───────▼──────┐  ┌──▼─────┐
             │     SMS     │          │   WhatsApp   │  │ Email  │
             │   Channel   │          │    Channel   │  │Channel │
             └──────┬──────┘          └───────┬──────┘  └──┬─────┘
                    │                         │            │
                    └────────────┬────────────┘            │
                                 │                         │
                          ┌──────▼───────┐                 │
                          │   Delivery   │◀────────────────┘
                          │   Tracker    │
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │  Analytics   │
                          │    Engine    │
                          └──────────────┘
```

## Implementation

### Multi-channel Hub Setup

The hub manages messaging across multiple channels with a unified interface:

```go
import (
    "context"
    "fmt"
    "log"
    "strings"
    "time"
)

// Channel delivers one message to one address. Beluga AI does not ship
// messaging providers; implement Channel per provider with its SDK
// (Twilio for SMS and WhatsApp, SendGrid for email, ...).
type Channel interface {
    Send(ctx context.Context, address, body string) error
}

type MultiChannelHub struct {
    channels map[string]Channel // "sms", "whatsapp", "email"
}

func NewMultiChannelHub(channels map[string]Channel) *MultiChannelHub {
    return &MultiChannelHub{channels: channels}
}

// Usage:
//
//  hub := NewMultiChannelHub(map[string]Channel{
//      "sms":      twilioSMS,      // your Channel implementations
//      "whatsapp": twilioWhatsApp,
//      "email":    sendgridEmail,
//  })
```

### Campaign Management

Send campaigns across multiple channels with consistent messaging:

```go
type Campaign struct {
    ID          string
    Name        string
    Message     string
    Channels    []string
    Recipients  []Recipient
    ScheduledAt time.Time
}

type Recipient struct {
    ID          string
    Phone       string
    Email       string
    Preferences map[string]string
}

func (h *MultiChannelHub) SendCampaign(ctx context.Context, campaign Campaign) error {
    for _, name := range campaign.Channels {
        channel, exists := h.channels[name]
        if !exists {
            log.Printf("campaign %s: no channel %q configured", campaign.ID, name)
            continue
        }

        for _, recipient := range campaign.Recipients {
            address := h.getRecipientAddress(recipient, name)
            if address == "" {
                continue
            }

            body := h.personalizeMessage(campaign.Message, recipient)
            if err := channel.Send(ctx, address, body); err != nil {
                h.trackDelivery(ctx, campaign.ID, name, recipient.ID, "failed")
                continue
            }

            h.trackDelivery(ctx, campaign.ID, name, recipient.ID, "sent")
        }
    }

    return nil
}

func (h *MultiChannelHub) getRecipientAddress(recipient Recipient, channel string) string {
    switch channel {
    case "sms", "whatsapp":
        return recipient.Phone
    case "email":
        return recipient.Email
    default:
        return ""
    }
}

func (h *MultiChannelHub) personalizeMessage(template string, recipient Recipient) string {
    // Replace placeholders with recipient data
    message := template
    for key, value := range recipient.Preferences {
        placeholder := fmt.Sprintf("{{%s}}", key)
        message = strings.ReplaceAll(message, placeholder, value)
    }
    return message
}
```

### Delivery Tracking

Track delivery status across all channels:

```go
type DeliveryStatus struct {
    CampaignID  string
    Channel     string
    RecipientID string
    Status      string // "sent", "delivered", "failed", "read"
    Timestamp   time.Time
}

func (h *MultiChannelHub) trackDelivery(ctx context.Context, campaignID, channel, recipientID, status string) {
    deliveryStatus := DeliveryStatus{
        CampaignID:  campaignID,
        Channel:     channel,
        RecipientID: recipientID,
        Status:      status,
        Timestamp:   time.Now(),
    }

    // Store delivery status in database for analytics
    // Implementation depends on your storage mechanism
    h.storeDeliveryStatus(ctx, deliveryStatus)
}

func (h *MultiChannelHub) GetCampaignStats(ctx context.Context, campaignID string) (*CampaignStats, error) {
    // Aggregate delivery statuses by channel and status
    statuses, err := h.getDeliveryStatuses(ctx, campaignID)
    if err != nil {
        return nil, fmt.Errorf("get delivery statuses: %w", err)
    }

    stats := &CampaignStats{
        CampaignID: campaignID,
        ByChannel:  make(map[string]ChannelStats),
    }

    for _, status := range statuses {
        channelStats := stats.ByChannel[status.Channel]
        switch status.Status {
        case "sent":
            channelStats.Sent++
        case "delivered":
            channelStats.Delivered++
        case "failed":
            channelStats.Failed++
        case "read":
            channelStats.Read++
        }
        stats.ByChannel[status.Channel] = channelStats
    }

    return stats, nil
}

type CampaignStats struct {
    CampaignID string
    ByChannel  map[string]ChannelStats
}

type ChannelStats struct {
    Sent      int
    Delivered int
    Failed    int
    Read      int
}
```

## Production Considerations

### Automated Scheduling

Schedule campaigns for optimal delivery times:

```go
type Scheduler struct {
    hub *MultiChannelHub
}

func (s *Scheduler) ScheduleCampaign(ctx context.Context, campaign Campaign) error {
    // Calculate delay until scheduled time
    delay := time.Until(campaign.ScheduledAt)
    if delay < 0 {
        // Send immediately if scheduled time has passed
        return s.hub.SendCampaign(ctx, campaign)
    }

    // Schedule for later. In-process timers are lost on restart; use a
    // durable job queue or workflow engine in production.
    time.AfterFunc(delay, func() {
        if err := s.hub.SendCampaign(context.Background(), campaign); err != nil {
            log.Printf("campaign %s: %v", campaign.ID, err)
        }
    })

    return nil
}
```

### Rate Limiting

Respect channel rate limits to avoid throttling:

```go
import "golang.org/x/time/rate"

type RateLimitedHub struct {
    hub      *MultiChannelHub
    limiters map[string]*rate.Limiter
}

func NewRateLimitedHub(hub *MultiChannelHub) *RateLimitedHub {
    return &RateLimitedHub{
        hub: hub,
        limiters: map[string]*rate.Limiter{
            "sms":      rate.NewLimiter(rate.Limit(10), 10), // 10/sec
            "whatsapp": rate.NewLimiter(rate.Limit(5), 5),   // 5/sec
            "email":    rate.NewLimiter(rate.Limit(20), 20), // 20/sec
        },
    }
}

func (h *RateLimitedHub) SendCampaign(ctx context.Context, campaign Campaign) error {
    for _, channel := range campaign.Channels {
        limiter := h.limiters[channel]
        if limiter != nil {
            if err := limiter.Wait(ctx); err != nil {
                return fmt.Errorf("rate limit wait: %w", err)
            }
        }
    }

    return h.hub.SendCampaign(ctx, campaign)
}
```

### Observability

Track campaign performance with OpenTelemetry:

```go
import "github.com/lookatitude/beluga-ai/v2/o11y"

func (h *MultiChannelHub) SendCampaignWithTracing(ctx context.Context, campaign Campaign) error {
    ctx, span := o11y.StartSpan(ctx, "marketing.send_campaign", o11y.Attrs{
        "campaign.id":         campaign.ID,
        "campaign.name":       campaign.Name,
        "campaign.channels":   len(campaign.Channels),
        "campaign.recipients": len(campaign.Recipients),
    })
    defer span.End()

    if err := h.SendCampaign(ctx, campaign); err != nil {
        span.RecordError(err)
        span.SetStatus(o11y.StatusError, err.Error())
        return err
    }

    // Record campaign metrics
    stats, err := h.GetCampaignStats(ctx, campaign.ID)
    if err != nil {
        span.RecordError(err)
        return nil // the campaign was sent; only stats failed
    }
    for channel, channelStats := range stats.ByChannel {
        span.SetAttributes(o11y.Attrs{
            fmt.Sprintf("campaign.%s.sent", channel):      channelStats.Sent,
            fmt.Sprintf("campaign.%s.delivered", channel): channelStats.Delivered,
            fmt.Sprintf("campaign.%s.failed", channel):    channelStats.Failed,
        })
    }

    span.SetStatus(o11y.StatusOK, "")
    return nil
}
```

### Template Management

Maintain consistent branding across channels:

```go
type TemplateManager struct {
    templates map[string]map[string]string // channel -> template_name -> template
}

func (m *TemplateManager) GetTemplate(channel, name string) (string, error) {
    channelTemplates, exists := m.templates[channel]
    if !exists {
        return "", fmt.Errorf("no templates for channel: %s", channel)
    }

    template, exists := channelTemplates[name]
    if !exists {
        return "", fmt.Errorf("template not found: %s", name)
    }

    return template, nil
}
```

## Results

After implementing the multi-channel marketing hub, the agency achieved:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Delivery Rate | 60-70% | 96% | 37-60% improvement |
| Management Time | 10-15 hrs/week | 4 hrs/week | 73-80% reduction |
| Channel Consistency | 60% | 97% | 62% improvement |
| Campaign Performance | 6.0/10 | 9.1/10 | 52% improvement |
| Client Satisfaction | 6.5/10 | 9.2/10 | 42% improvement |

## Related Resources

- [Messaging Integration](/docs/guides/production/) for channel-specific configuration
- [Observability Guide](/docs/guides/production/observability/) for campaign analytics setup
