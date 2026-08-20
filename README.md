# TicketFlow

TicketFlow is a FastAPI backend for a support-ticket system. Customers can create
and manage their own tickets, while support agents can review all tickets, add
comments, and move tickets through a controlled resolution workflow. The project
includes a REST API, PostgreSQL persistence, Redis caching, WebSocket notifications,
signed outgoing webhooks, and a Docker Compose development environment.

## Tech Stack

- Python 3.12
- FastAPI + Pydantic v2
- SQLAlchemy 2 async + asyncpg
- PostgreSQL 16
- Alembic
- Redis 7
- PyJWT + pwdlib/Argon2
- HTTPX
- Docker + Docker Compose

Exact dependency versions are defined in `requirements.txt`.

## Quick Start

PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Bash:

```bash
cp .env.example .env
docker compose up --build
```

Compose waits for PostgreSQL and Redis health checks. The API container then applies
Alembic migrations, runs the idempotent agent seed, and starts Uvicorn on port 8000.
The startup commands use fail-fast shell chaining, so a migration or seed failure
prevents the API server from starting.

## Seeded Agent

The development agent configured in `.env.example` is:

```text
Email: support@example.com
Password: TicketFlowDev123!
```

These credentials are for local development only. The seed command normalizes the
email and skips creation when the account already exists, so restarting the stack
does not create duplicate agents.

## API Documentation

- Health: <http://localhost:8000/health>
- Swagger UI: <http://localhost:8000/docs>

The health endpoint checks both PostgreSQL and Redis. It returns HTTP 503 with a
`degraded` status when either dependency check fails.

## Core Features

### Authentication

Login returns signed JWT access and refresh tokens. Public registration always creates
a `CUSTOMER`; the seeded `AGENT` uses the same login endpoint. Protected routes load
the current user from PostgreSQL and enforce roles server-side. Refresh tokens can be
exchanged for a new access token, but refresh-token rotation is not implemented.

### Tickets and comments

Customers can create, list, view, edit, and delete only their own tickets. Customer
edits and deletion are restricted to `OPEN` tickets. Agents can list and view all
tickets, add comments, and use the dedicated status endpoint. Both an authorized
customer and an agent can read or add comments on an accessible ticket.

### Filtering, search, and pagination

Ticket lists support filters for status, priority, and category; literal text search
across title and description; and database-level pagination. Search uses PostgreSQL
`ILIKE` with escaped wildcard characters.

### Redis caching and dashboard

Redis caches filtered ticket-list responses for 30 seconds and agent dashboard
statistics for 60 seconds by default. Ticket details and comments are read directly
from PostgreSQL. The dashboard reports total tickets and counts grouped by status,
priority, and category.

### Redis-backed rate limiting

- Login: 5 requests per minute for each client IP.
- Ticket creation: 30 requests per minute for each authenticated customer.

Rate limiting fails open if Redis is unavailable, so core PostgreSQL operations can
continue.

### WebSockets

Authenticated clients can subscribe to an accessible ticket, and agents can subscribe
to the dashboard. Ticket subscribers receive `comment.created` and
`ticket.status_changed`; dashboard subscribers receive both events across all tickets.
REST remains responsible for all mutations.

### Outgoing webhooks

Agents can register endpoints for `ticket.created` and `ticket.status_changed`.
TicketFlow signs the exact outgoing JSON bytes with a per-registration HMAC-SHA256
secret, sends the request through HTTPX in a FastAPI background task, and records each
delivery attempt in PostgreSQL. Webhook registration responses reveal the secret once;
normal registration lists and delivery history do not include it.

### Error responses

API failures use one JSON envelope containing a stable code, a client-readable message,
and optional validation details. Authentication failures retain the
`WWW-Authenticate: Bearer` response header. Ticket workflow and mutability conflicts
return HTTP 409, while malformed request data returns HTTP 422.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "body.email",
        "message": "value is not a valid email address"
      }
    ]
  }
}
```

## Ticket Workflow

```text
OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED
```

Only an `AGENT` can change ticket status. Each transition must move to the next state;
the API rejects skipped and backward transitions.

## API Summary

### Authentication

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me
```

### Tickets

```text
POST   /api/v1/tickets
GET    /api/v1/tickets
GET    /api/v1/tickets/{ticket_id}
PATCH  /api/v1/tickets/{ticket_id}
DELETE /api/v1/tickets/{ticket_id}
PATCH  /api/v1/tickets/{ticket_id}/status
```

### Comments and dashboard

```text
GET  /api/v1/tickets/{ticket_id}/comments
POST /api/v1/tickets/{ticket_id}/comments
GET  /api/v1/dashboard/stats
```

### Webhooks

```text
POST   /api/v1/webhooks
GET    /api/v1/webhooks
DELETE /api/v1/webhooks/{webhook_id}
GET    /api/v1/webhooks/deliveries?limit=100
```

### WebSockets

```text
/ws/tickets/{ticket_id}?token=<access_token>
/ws/dashboard?token=<access_token>
```

## Architecture

TicketFlow uses a modular-monolith design with PostgreSQL as the source of truth.
Redis is an optional caching layer: failures fall back to PostgreSQL, and versioned
ticket-list keys provide O(1) invalidation without scanning the keyspace. WebSocket
connections are held in memory, and outgoing webhooks run as background tasks because
the assessment uses one API instance without a separate worker.

The decisions, reasons, and trade-offs are documented in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Automated Tests

The focused pytest suite covers authentication, role and ownership permissions, and
the sequential ticket workflow. Tests require an isolated PostgreSQL database whose
name ends in `_test`; the safety check refuses any other database name.

Set both database variables to the isolated database, apply migrations, and run:

```powershell
$env:DATABASE_URL=$env:TEST_DATABASE_URL
alembic upgrade head
python -m pytest -q
```

GitHub Actions runs the same migration and test commands against a PostgreSQL service
on every push and pull request. Redis is replaced by an in-memory test double because
cache behavior is outside this focused suite.

## Manual Verification

Use Swagger UI or another HTTP client for a short manual flow:

1. Log in as the seeded agent and register webhooks for `ticket.created` and
   `ticket.status_changed`.
2. Register and log in as a customer, create a ticket, subscribe to its WebSocket,
   and add a comment.
3. Log in as the agent, subscribe to the dashboard WebSocket, and change the ticket
   status.
4. Confirm the WebSocket events, outgoing webhook requests, and delivery logs.

For webhook signature verification, calculate HMAC-SHA256 with the creation-time
secret over the exact raw request body and compare it with
`X-TicketFlow-Signature`.

## Shutting Down

```powershell
docker compose down
```

This stops the containers and retains the named PostgreSQL volume.
