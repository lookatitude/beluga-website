---
title: Errors
description: "core.Error, ErrorCode, IsRetryable(), and the wrapping contract every Beluga AI layer follows. Typed errors over strings."
---

Beluga uses structured, typed errors throughout. Every public function that
can fail returns a `*core.Error` or wraps one in its chain. Raw
`errors.New` and `fmt.Errorf` strings exist in internal paths — not in any
function that crosses a package boundary.

The reason is operational: when an LLM provider returns a 429, the retry
middleware needs to know whether to retry, not just that something failed. A
string error cannot carry that signal reliably across package boundaries.
A typed `ErrorCode` can.

Two error paths coexist at runtime: application errors (tool failures, bad schemas) become `Observation`s that the planner can recover from; infrastructure errors (network blips, rate limits) are intercepted by middleware and retried transparently.

```mermaid
graph TD
  Tool[Tool.Execute fails] --> Err[core.Error + ErrorCode]
  Err --> Obs[Observation with error]
  Obs --> Replan[Planner.Replan]
  Replan --> Try2[Try a different tool or strategy]

  LLM[LLM transient error] --> MW[Middleware retry]
  MW --> Retry[Exponential backoff]
  Retry --> LLM
```

## `ErrorCode` — the classification

Source: [`core/errors.go:12-52`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L12-L52)

```go
type ErrorCode string

const (
    ErrRateLimit       ErrorCode = "rate_limit"
    ErrAuth            ErrorCode = "auth_error"
    ErrTimeout         ErrorCode = "timeout"
    ErrInvalidInput    ErrorCode = "invalid_input"
    ErrToolFailed      ErrorCode = "tool_failed"
    ErrProviderDown    ErrorCode = "provider_unavailable"
    ErrGuardBlocked    ErrorCode = "guard_blocked"
    ErrBudgetExhausted ErrorCode = "budget_exhausted"
    ErrNotFound        ErrorCode = "not_found"
    ErrCanceled        ErrorCode = "canceled"       // caller canceled; not retryable
    ErrInternal        ErrorCode = "internal_error" // no more specific classification; not retryable
)
```

These codes are the vocabulary for programmatic error handling. Every package
in the capability layer maps its provider-specific failures to one of these
codes. A networking timeout from the OpenAI SDK becomes `ErrTimeout`; a 429
becomes `ErrRateLimit`.

## `core.Error` — the structure

Source: [`core/errors.go:63-75`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L63-L75)

```go
type Error struct {
    Op      string    // operation that failed: "llm.generate", "tool.execute"
    Code    ErrorCode // classification
    Message string    // human-readable description
    Err     error     // wrapped cause (participates in errors.Is / errors.As)
}
```

`Op` is the dotted operation name: `llm.generate`, `tool.execute`,
`memory.load`. It survives stack unwinding and appears verbatim in
observability backends as the failing operation.

`Err` implements `Unwrap()` so `errors.Is` and `errors.As` traverse the
full chain (`core/errors.go:190-192`).

## Creating errors

Two constructors:

**`core.NewError`** — explicit fields:

Source: [`core/errors.go:79-86`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L79-L86)

```go
return core.NewError("tool.execute", core.ErrToolFailed, "fetch returned 404", err)
```

**`core.Errorf`** — formatted message, `%w` wrapping:

Source: [`core/errors.go:104-112`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L104-L112)

```go
return core.Errorf(core.ErrTimeout, "llm.generate: deadline exceeded after %d tokens: %w", n, err)
```

`core.Errorf` delegates to `fmt.Errorf` so `%w` works as expected. The wrapped
error is preserved in `Error.Err` and participates in `errors.Is` /
`errors.As` traversal. `Errorf` always uses the code you pass; to keep the
classification of a wrapped `*core.Error` (or map `context.Canceled` to
`ErrCanceled` and `context.DeadlineExceeded` to `ErrTimeout`), use
`core.Wrapf(fallback, format, args...)` instead.

## `IsRetryable` — the retry decision

Source: [`core/errors.go:207-213`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L207-L213)

```go
func IsRetryable(err error) bool {
    var e *Error
    if errors.As(err, &e) {
        return retryableCodes[e.Code]
    }
    return false
}
```

Three codes are retryable (`core/errors.go:55-59`): `ErrRateLimit`,
`ErrTimeout`, `ErrProviderDown`. All others are not. `IsRetryable` uses
`errors.As` so it traverses wrapped errors correctly — a `*core.Error`
nested inside a `fmt.Errorf("%w", ...)` still matches.

## Full example — wrapping a provider error

```go
import (
    "context"
    "errors"
    "fmt"
    "time"

    "github.com/lookatitude/beluga-ai/v2/core"
)

// callWithRetry calls fn up to maxAttempts times, retrying on retryable errors.
func callWithRetry(ctx context.Context, maxAttempts int, fn func(context.Context) error) error {
    var lastErr error
    for attempt := range maxAttempts {
        lastErr = fn(ctx)
        if lastErr == nil {
            return nil
        }
        if !core.IsRetryable(lastErr) {
            // auth failures, invalid input, guard blocks — don't retry
            return lastErr
        }
        // back off proportional to attempt number
        select {
        case <-ctx.Done():
            return fmt.Errorf("retry loop cancelled: %w", ctx.Err())
        case <-time.After(time.Duration(attempt+1) * 200 * time.Millisecond):
        }
    }
    return fmt.Errorf("all %d attempts failed: %w", maxAttempts, lastErr)
}

// wrapProviderError maps a raw SDK error to a core.Error.
func wrapProviderError(op string, sdkErr error) error {
    if sdkErr == nil {
        return nil
    }
    // In practice, inspect sdkErr for status codes, message text, etc.
    var code core.ErrorCode
    switch {
    case errors.Is(sdkErr, context.DeadlineExceeded):
        code = core.ErrTimeout
    default:
        code = core.ErrProviderDown
    }
    return core.NewError(op, code, sdkErr.Error(), sdkErr)
}
```

## Error string format

`Error.Error()` returns `"<op> [<code>]: <message>: <cause>"`. The `<op> `
segment is omitted when `Op` is empty (as it is for errors built by
`core.Errorf` and `core.Wrapf`), and `: <cause>` is omitted when the message
already contains the cause's text (as it always does for `Errorf` and `Wrapf`),
so a cause is never printed twice.

Source: [`core/errors.go:169-186`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go#L169-L186)

```
llm.generate [rate_limit]: provider returned 429: http: status 429
[timeout]: llm.generate: deadline exceeded after 512 tokens: context deadline exceeded
```

This format is readable in logs and `slog` structured output. The `op` field
scopes the error to its origin without requiring a stack trace.

## Error matching with `errors.Is`

`core.Error.Is` compares by `Code` only — two errors with the same code
match, regardless of message or cause (`core/errors.go:196-202`). This lets
you write:

```go
import (
    "errors"

    "github.com/lookatitude/beluga-ai/v2/core"
)

func handleErr(err error) {
    sentinel := &core.Error{Code: core.ErrGuardBlocked}
    if errors.Is(err, sentinel) {
        // guard rejected the request — do not retry, surface to user
    }
}
```

## Common mistakes

- **Returning raw `fmt.Errorf` from a public function.** `IsRetryable` returns `false` for all unclassified errors. Middleware cannot retry what it cannot classify. C-003 in `.guild/wiki/corrections.md` documents 190 occurrences of this pattern found across 50+ files during the v2 migration.
- **Using error message strings for branching.** String-matching errors breaks as soon as provider SDK messages change. Use `ErrorCode` or `errors.As`.
- **Swallowing errors silently.** Every error must either be returned, logged, or explicitly discarded with a comment explaining why. The rule is in `.claude/rules/go-packages.md`.
- **Panicking for recoverable errors.** `panic` is for programmer errors (nil pointer, out-of-bounds). Provider failures, tool timeouts, and guard blocks are recoverable — return a `*core.Error`.
- **Leaking internal details in errors returned to callers.** `Error.Message` is for operators; strip SQL query text, file paths, and internal IDs before the error crosses a trust boundary.

## Related reading

- [Resilience](/docs/reference/api/infrastructure/resilience/) — circuit breakers and retry middleware that consume `IsRetryable`.
- [Extensibility](/docs/concepts/extensibility) — where `core.Error` fits in the middleware chain.
- [`core/errors.go`](https://github.com/lookatitude/beluga-ai/blob/main/core/errors.go) — canonical source for all error types and codes.
- [`.guild/wiki/patterns/error-handling.md`](https://github.com/lookatitude/beluga-ai/blob/main/.guild/wiki/patterns/error-handling.md) — patterns and anti-patterns with file:line references.
