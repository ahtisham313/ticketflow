# Submission

## Core Implementation

The required TicketFlow backend functionality is implemented: JWT authentication and
role enforcement, customer-scoped ticket management, sequential agent workflow,
comments, filtering/search/pagination, Redis list and dashboard caching, authenticated
WebSocket notifications, and signed outgoing webhooks with delivery auditing.

The application runs through Docker Compose with PostgreSQL, Redis, Alembic migrations,
and an idempotent support-agent seed.

## Stretch Goals

- Automated tests with GitHub Actions CI.
- Redis-backed rate limiting for login and ticket creation.

## AI Tools Used

I used ChatGPT, Claude, and Gemini while comparing implementation approaches and
reviewing architectural decisions. OpenAI Codex was used to assist with implementation.
