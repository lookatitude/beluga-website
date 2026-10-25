---
title: Auth0 JWT Authentication
description: "Integrate Auth0 JWT authentication with Beluga AI server endpoints for secure API access, token validation, and RBAC in Go."
head:
  - tag: meta
    attrs:
      name: keywords
      content: "Auth0, JWT authentication, Beluga AI, token validation, RBAC, secure API, Go authentication middleware"
---

## Overview

Exposing AI agents as API endpoints introduces the same authentication requirements as any public API -- plus the added risk that unauthenticated access can burn through expensive LLM token budgets. Auth0 provides a managed identity platform that handles user authentication, token issuance, and JWKS key rotation, so you can focus on agent logic instead of building auth infrastructure. This guide covers integrating [Auth0](https://auth0.com) with the Beluga AI `server` package to secure REST API endpoints using JWT authentication. You will implement middleware that validates tokens, extracts user identity, and propagates authentication context through your request pipeline.

## Prerequisites

- Go 1.26 or later
- Beluga AI framework installed
- An Auth0 account with an API application configured
- Auth0 tenant domain, client ID, and API audience identifier

## Installation

Install the JWT parsing library:

```bash
go get github.com/golang-jwt/jwt/v5
```

Gather your Auth0 credentials:

| Credential | Source | Example |
|---|---|---|
| Domain | Auth0 Dashboard > Applications > Settings | `your-tenant.auth0.com` |
| Client ID | Auth0 Dashboard > Applications > Settings | `abc123...` |
| Audience | Auth0 Dashboard > APIs > Identifier | `https://api.example.com` |

## Configuration

Set the required environment variables:

```bash
export AUTH0_DOMAIN="your-tenant.auth0.com"
export AUTH0_AUDIENCE="https://api.example.com"
```

| Variable | Description | Required |
|---|---|---|
| `AUTH0_DOMAIN` | Your Auth0 tenant domain | Yes |
| `AUTH0_AUDIENCE` | API audience identifier | Yes |
| `AUTH0_CLIENT_ID` | Application client ID | No |

## Usage

### Define JWT Claims

Define a claims struct that maps Auth0 token fields to Go types:

```go
package main

import (
    "github.com/golang-jwt/jwt/v5"
)

// Claims represents the Auth0 JWT token payload.
type Claims struct {
    Sub   string   `json:"sub"`
    Email string   `json:"email"`
    Roles []string `json:"https://beluga.ai/roles"`
    jwt.RegisteredClaims
}
```

### Create Authentication Middleware

Build an HTTP middleware that validates incoming Bearer tokens against Auth0:

```go
package main

import (
    "context"
    "fmt"
    "net/http"
    "strings"

    "github.com/golang-jwt/jwt/v5"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/attribute"
    "go.opentelemetry.io/otel/trace"
)

// contextKey is an unexported type for context keys to avoid collisions.
type contextKey string

const (
    userIDKey    contextKey = "user_id"
    userEmailKey contextKey = "user_email"
    userRolesKey contextKey = "user_roles"
)

// Auth0JWTMiddleware validates JWT tokens issued by Auth0.
type Auth0JWTMiddleware struct {
    domain   string
    audience string
    tracer   trace.Tracer
}

// NewAuth0JWTMiddleware creates a new Auth0 JWT middleware instance.
func NewAuth0JWTMiddleware(domain, audience string) *Auth0JWTMiddleware {
    return &Auth0JWTMiddleware{
        domain:   domain,
        audience: audience,
        tracer:   otel.Tracer("beluga.server.auth"),
    }
}

// Authenticate returns an HTTP middleware that validates JWT Bearer tokens.
func (m *Auth0JWTMiddleware) Authenticate(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        ctx, span := m.tracer.Start(r.Context(), "auth.authenticate")
        defer span.End()

        // Extract Bearer token from Authorization header
        authHeader := r.Header.Get("Authorization")
        if authHeader == "" {
            span.RecordError(fmt.Errorf("missing authorization header"))
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        parts := strings.SplitN(authHeader, " ", 2)
        if len(parts) != 2 || parts[0] != "Bearer" {
            span.RecordError(fmt.Errorf("invalid authorization header format"))
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        tokenString := parts[1]

        // Parse and validate the JWT
        token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
            if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
                return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
            }
            return m.getPublicKey(ctx, token)
        })
        if err != nil {
            span.RecordError(err)
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        claims, ok := token.Claims.(*Claims)
        if !ok || !token.Valid {
            span.RecordError(fmt.Errorf("invalid token claims"))
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        // Propagate user identity through context
        ctx = context.WithValue(ctx, userIDKey, claims.Sub)
        ctx = context.WithValue(ctx, userEmailKey, claims.Email)
        ctx = context.WithValue(ctx, userRolesKey, claims.Roles)

        span.SetAttributes(
            attribute.String("user.id", claims.Sub),
            attribute.String("user.email", claims.Email),
        )

        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// getPublicKey fetches the RSA public key from Auth0's JWKS endpoint.
func (m *Auth0JWTMiddleware) getPublicKey(ctx context.Context, token *jwt.Token) (interface{}, error) {
    // Fetch JWKS from https://{domain}/.well-known/jwks.json
    // Match the key by kid (Key ID) from the token header.
    // In production, cache the JWKS response to avoid per-request HTTP calls.
    _ = ctx
    _ = token
    return nil, fmt.Errorf("implement JWKS fetching for domain %s", m.domain)
}
```

### Extract User Information

Helper functions to read authenticated user data from the request context:

```go
// UserID extracts the authenticated user ID from context.
func UserID(ctx context.Context) string {
    if id, ok := ctx.Value(userIDKey).(string); ok {
        return id
    }
    return ""
}

// UserRoles extracts the authenticated user roles from context.
func UserRoles(ctx context.Context) []string {
    if roles, ok := ctx.Value(userRolesKey).([]string); ok {
        return roles
    }
    return nil
}
```

### Integrate with the Beluga AI Server

Wire the middleware into a Beluga AI HTTP server. `server.NewAgentHandler` exposes an agent at `POST {prefix}/invoke` and `POST {prefix}/stream`; wrapping it with `Authenticate` protects both routes:

```go
package main

import (
    "context"
    "log"
    "net/http"
    "os"
    "time"

    "github.com/lookatitude/beluga-ai/v2/agent"
    "github.com/lookatitude/beluga-ai/v2/config"
    "github.com/lookatitude/beluga-ai/v2/llm"
    _ "github.com/lookatitude/beluga-ai/v2/llm/providers/openai"
    "github.com/lookatitude/beluga-ai/v2/server"
)

func main() {
    ctx := context.Background()

    authMiddleware := NewAuth0JWTMiddleware(
        os.Getenv("AUTH0_DOMAIN"),
        os.Getenv("AUTH0_AUDIENCE"),
    )

    model, err := llm.New("openai", config.ProviderConfig{
        APIKey: os.Getenv("OPENAI_API_KEY"),
        Model:  "gpt-4o",
    })
    if err != nil {
        log.Fatalf("Failed to create model: %v", err)
    }
    assistant := agent.New("assistant", agent.WithLLM(model))

    srv := server.NewStdlibAdapter(server.Config{
        ReadTimeout:  30 * time.Second,
        WriteTimeout: 60 * time.Second,
    })

    protected := authMiddleware.Authenticate(server.NewAgentHandler(assistant))
    if err := srv.RegisterHandler("/api/agents/", http.StripPrefix("/api/agents", protected)); err != nil {
        log.Fatalf("Failed to register handler: %v", err)
    }

    if err := srv.Serve(ctx, "0.0.0.0:8080"); err != nil {
        log.Fatalf("Server failed: %v", err)
    }
}
```

The same pattern works with the framework adapters under `server/adapters/` (chi, echo, fiber, gin, huma, ...): every `server.ServerAdapter` accepts a raw `http.Handler` through `RegisterHandler`.

## Advanced Topics

### JWKS Caching

In production, avoid fetching the JWKS document on every request. Cache the key set with a TTL (e.g., 1 hour) and refresh it on cache miss or when a `kid` is not found:

```go
type JWKSCache struct {
    keys      map[string]interface{} // kid -> public key
    expiresAt time.Time
    mu        sync.RWMutex
    domain    string
}

func (c *JWKSCache) GetKey(ctx context.Context, kid string) (interface{}, error) {
    c.mu.RLock()
    if time.Now().Before(c.expiresAt) {
        if key, ok := c.keys[kid]; ok {
            c.mu.RUnlock()
            return key, nil
        }
    }
    c.mu.RUnlock()

    // Refresh cache
    return c.refresh(ctx, kid)
}
```

### Role-Based Access Control

Gate handlers on the roles carried in the Auth0 token. For policy-based decisions beyond a role check, evaluate the same identity with Beluga AI's `auth` package.

```go
func requireRole(role string, next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        for _, have := range UserRoles(r.Context()) {
            if have == role {
                next.ServeHTTP(w, r)
                return
            }
        }
        http.Error(w, "Forbidden", http.StatusForbidden)
    })
}
```

### Audit Logging

Use OpenTelemetry spans to record authentication events for compliance and debugging:

```go
span.SetAttributes(
    attribute.String("auth.provider", "auth0"),
    attribute.String("auth.method", "jwt"),
    attribute.String("user.id", claims.Sub),
)
```

## Troubleshooting

### Token validation failed

**Cause**: The token is expired, malformed, or signed for a different audience.

**Resolution**: Verify that `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` match the values configured in your Auth0 API application. Inspect the token payload at [jwt.io](https://jwt.io) to confirm the `aud` and `iss` claims.

### Public key not found

**Cause**: The JWKS endpoint at `https://{domain}/.well-known/jwks.json` is unreachable, or the token's `kid` does not match any key in the JWKS response.

**Resolution**: Confirm network connectivity to your Auth0 domain. If you cache JWKS keys, ensure the cache refreshes when an unknown `kid` is encountered.

## Related Resources

- [Beluga AI Auth Package](/docs/reference/api/infrastructure/auth/) -- RBAC and ABAC integration
- [Kubernetes Helm Deployment](/docs/guides/production/integrations/kubernetes-helm) -- Deploy authenticated services to Kubernetes
- [Server Package Guide](/docs/reference/api/protocol/server/) -- Full server configuration reference
