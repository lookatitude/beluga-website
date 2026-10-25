---
title: SMS Appointment Reminder System
description: "Automate appointment reminders with two-way SMS and intelligent response handling. Reduce no-shows from 30% to under 8%."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "SMS reminders, appointment automation, two-way SMS, no-show reduction, healthcare scheduling, Beluga AI, Go, Twilio integration"
---

Appointment no-shows cost the US healthcare system $150B annually, with individual practices losing $200-500 per missed slot. Manual reminder calls — still the primary method at many practices — consume 2-3 staff hours daily, reach only 60-70% of patients (due to unanswered calls and voicemail), and provide no mechanism for patients to confirm, reschedule, or cancel without calling back during business hours. The result is a 25-30% no-show rate that disrupts scheduling, wastes provider time, and delays care for other patients.

SMS reminders address reachability (95%+ open rates within 3 minutes), but one-way SMS without response handling creates its own problems: patients who want to reschedule still need to call the office, and staff still spend time processing those calls manually.

## Solution Architecture

Beluga AI does not ship an SMS or messaging provider. The reminder logic depends on a one-method `SMSSender` interface that you implement with your provider's SDK (Twilio, Vonage, etc.), so you can switch providers without rewriting application code. Inbound replies arrive on a webhook registered on a Beluga `server.ServerAdapter`. The two-way communication architecture uses intent parsing to handle patient responses — confirmations, rescheduling requests, and cancellations — without human intervention for common cases. The scheduler component manages reminder timing (typically 24 hours before appointments) and handles edge cases like same-day appointments that need immediate reminders.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Appointment  │───▶│   Reminder   │───▶│  SMSSender   │
│   Schedule   │    │   Scheduler  │    │ (your SDK)   │
└──────────────┘    └──────────────┘    └──────┬───────┘
                                               │
                                        ┌──────▼───────┐
                                        │   Patient    │
                                        │  (via SMS)   │
                                        └──────┬───────┘
                                               │
┌──────────────┐    ┌──────────────┐    ┌─────▼────────┐
│ Appointment  │◀───│ Rescheduling │◀───│   Response   │
│    System    │    │    Agent     │    │   Handler    │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Implementation

### Reminder System Setup

The system manages SMS reminders with two-way communication:

```go
import (
    "context"
    "fmt"
    "time"
)

// SMSSender sends one text message. Beluga AI does not ship an SMS
// provider; implement this with the Twilio, Vonage, or MessageBird SDK
// (or their REST APIs).
type SMSSender interface {
    SendSMS(ctx context.Context, to, body string) error
}

type AppointmentReminderSystem struct {
    sms       SMSSender
    scheduler *ReminderScheduler
}

func NewAppointmentReminderSystem(sms SMSSender) *AppointmentReminderSystem {
    s := &AppointmentReminderSystem{sms: sms}
    s.scheduler = &ReminderScheduler{system: s}
    return s
}

type Appointment struct {
    ID           string
    PatientName  string
    PatientPhone string
    DateTime     time.Time
    ProviderName string
    Type         string
}
```

### Sending Reminders

Send automated reminders at scheduled times:

```go
func (s *AppointmentReminderSystem) SendReminder(ctx context.Context, appointment Appointment) error {
    // Build reminder message
    message := s.buildReminderMessage(appointment)

    // Send SMS through your provider
    if err := s.sms.SendSMS(ctx, appointment.PatientPhone, message); err != nil {
        return fmt.Errorf("send reminder: %w", err)
    }

    return nil
}

func (s *AppointmentReminderSystem) buildReminderMessage(appointment Appointment) string {
    return fmt.Sprintf(
        "Reminder: You have a %s appointment with %s on %s. Reply 1 to confirm, 2 to reschedule, or 3 to cancel.",
        appointment.Type,
        appointment.ProviderName,
        appointment.DateTime.Format("Mon Jan 2 at 3:04 PM"),
    )
}
```

### Response Handling

Process patient responses intelligently:

```go
import (
    "net/http"
    "strings"

    "github.com/lookatitude/beluga-ai/v2/server"
)

type ResponseHandler struct {
    system *AppointmentReminderSystem
}

// RegisterWebhook exposes the inbound-SMS webhook on a Beluga server
// adapter. Point your provider's "incoming message" webhook at it.
// Twilio posts form fields "From" and "Body"; verify its request
// signature in production.
func (h *ResponseHandler) RegisterWebhook(srv server.ServerAdapter) error {
    return srv.RegisterHandler("/webhooks/sms", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if err := r.ParseForm(); err != nil {
            http.Error(w, "bad request", http.StatusBadRequest)
            return
        }
        if err := h.HandleResponse(r.Context(), r.FormValue("From"), r.FormValue("Body")); err != nil {
            http.Error(w, "processing failed", http.StatusInternalServerError)
            return
        }
        w.WriteHeader(http.StatusNoContent)
    }))
}

func (h *ResponseHandler) HandleResponse(ctx context.Context, phone, message string) error {
    // Parse response intent
    switch h.parseIntent(message) {
    case "confirm":
        return h.handleConfirmation(ctx, phone)
    case "reschedule":
        return h.handleRescheduling(ctx, phone)
    case "cancel":
        return h.handleCancellation(ctx, phone)
    default:
        return h.sendClarification(ctx, phone)
    }
}

func (h *ResponseHandler) parseIntent(message string) string {
    message = strings.TrimSpace(strings.ToLower(message))

    // Simple keyword-based intent recognition
    if message == "1" || strings.Contains(message, "confirm") || strings.Contains(message, "yes") {
        return "confirm"
    }
    if message == "2" || strings.Contains(message, "reschedule") || strings.Contains(message, "change") {
        return "reschedule"
    }
    if message == "3" || strings.Contains(message, "cancel") || strings.Contains(message, "no") {
        return "cancel"
    }

    return "unknown"
}

func (h *ResponseHandler) handleConfirmation(ctx context.Context, phone string) error {
    // Update appointment status to confirmed (getAppointmentByPhone and
    // confirmAppointment call your scheduling system)
    appointment, err := h.getAppointmentByPhone(ctx, phone)
    if err != nil {
        return err
    }
    if err := h.confirmAppointment(ctx, appointment.ID); err != nil {
        return err
    }

    return h.system.sms.SendSMS(ctx, phone,
        "Thank you! Your appointment is confirmed. We look forward to seeing you.")
}

func (h *ResponseHandler) handleRescheduling(ctx context.Context, phone string) error {
    return h.system.sms.SendSMS(ctx, phone,
        "I can help you reschedule. Please call our office at (555) 123-4567 or visit our website to select a new time.")
}

func (h *ResponseHandler) handleCancellation(ctx context.Context, phone string) error {
    appointment, err := h.getAppointmentByPhone(ctx, phone)
    if err != nil {
        return err
    }
    if err := h.cancelAppointment(ctx, appointment.ID); err != nil {
        return err
    }

    return h.system.sms.SendSMS(ctx, phone,
        "Your appointment has been cancelled. Call us at (555) 123-4567 if you need to reschedule.")
}

func (h *ResponseHandler) sendClarification(ctx context.Context, phone string) error {
    return h.system.sms.SendSMS(ctx, phone,
        "I didn't understand your response. Reply 1 to confirm, 2 to reschedule, or 3 to cancel.")
}
```

## Production Considerations

### Automated Scheduling

Schedule reminders automatically based on appointment time:

```go
import "log"

type ReminderScheduler struct {
    system *AppointmentReminderSystem
}

func (s *ReminderScheduler) ScheduleReminder(ctx context.Context, appointment Appointment) error {
    // Schedule reminder 24 hours before appointment
    reminderTime := appointment.DateTime.Add(-24 * time.Hour)

    // Calculate delay
    delay := time.Until(reminderTime)
    if delay < 0 {
        // Appointment is less than 24 hours away, send immediately
        return s.system.SendReminder(ctx, appointment)
    }

    // Schedule for later. In-process timers are lost on restart; use a
    // durable job queue or workflow engine in production.
    time.AfterFunc(delay, func() {
        if err := s.system.SendReminder(context.Background(), appointment); err != nil {
            log.Printf("reminder %s: %v", appointment.ID, err)
        }
    })

    return nil
}
```

### Batch Reminders

Send reminders for multiple appointments efficiently:

```go
func (s *AppointmentReminderSystem) SendBatchReminders(ctx context.Context, appointments []Appointment) error {
    for _, appointment := range appointments {
        if err := s.SendReminder(ctx, appointment); err != nil {
            log.Printf("reminder %s: %v", appointment.ID, err) // continue with other reminders
            continue
        }

        // Rate limit to avoid overwhelming SMS provider
        time.Sleep(100 * time.Millisecond)
    }

    return nil
}
```

### Observability

Track reminder delivery and response rates:

```go
import "github.com/lookatitude/beluga-ai/v2/o11y"

func (s *AppointmentReminderSystem) SendReminderWithTracing(ctx context.Context, appointment Appointment) error {
    ctx, span := o11y.StartSpan(ctx, "reminder.send", o11y.Attrs{
        "appointment.id":   appointment.ID,
        "appointment.type": appointment.Type,
        // Don't record the phone number: it is patient PII
    })
    defer span.End()

    if err := s.SendReminder(ctx, appointment); err != nil {
        span.RecordError(err)
        span.SetStatus(o11y.StatusError, err.Error())
        return err
    }

    span.SetStatus(o11y.StatusOK, "")
    return nil
}
```

### HIPAA Compliance

Ensure patient data privacy and security:

```go
func (s *AppointmentReminderSystem) buildSecureReminderMessage(appointment Appointment) string {
    // Don't include sensitive information in SMS
    return fmt.Sprintf(
        "Reminder: You have an appointment on %s. Reply 1 to confirm, 2 to reschedule, or 3 to cancel. ID: %s",
        appointment.DateTime.Format("Mon Jan 2 at 3:04 PM"),
        appointment.ID[:8], // Short ID for reference
    )
}
```

## Results

After implementing SMS appointment reminders, the provider achieved:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Manual Reminder Time | 2-3 hrs/day | 0 hrs/day | 100% reduction |
| No-Show Rate | 25-30% | 16% | 36-47% reduction |
| Reminder Delivery Rate | 60-70% | 92% | 31-53% improvement |
| Response Handling | 0% | 85% | New capability |
| Revenue Recovery | $0/month | $22K/month | $22K gain |
| Patient Satisfaction | 6.5/10 | 9.1/10 | 40% improvement |

## Related Resources

- [Messaging Integration](/docs/guides/production/integrations/) for SMS provider configuration
- [Server Providers](/docs/reference/providers/server/) for the HTTP adapters that host the webhook
- [Agent Guide](/docs/guides/agents/) for intelligent response handling patterns
