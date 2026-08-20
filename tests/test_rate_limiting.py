"""Focused endpoint and fail-open tests for Redis rate limiting."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from pytest import MonkeyPatch
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.v1 import tickets as ticket_routes
from app.models.ticket import Ticket
from app.models.user import User
from app.services.rate_limit_service import consume_rate_limit

AuthHeadersFactory = Callable[[User], dict[str, str]]
TicketFactory = Callable[..., Awaitable[Ticket]]


async def test_login_sixth_request_is_rate_limited(client: AsyncClient) -> None:
    payload = {"email": "missing@example.com", "password": "WrongPassword123!"}

    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    response = await client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please try again later.",
            "details": None,
        }
    }
    assert 1 <= int(response.headers["Retry-After"]) <= 60


async def test_ticket_creation_is_rate_limited_per_customer(
    client: AsyncClient,
    customer_a: User,
    auth_headers: AuthHeadersFactory,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(ticket_routes, "TICKET_CREATE_RATE_LIMIT", 2)
    payload = {
        "title": "Rate-limited ticket",
        "description": "Ticket creation limit test",
        "category": "TECHNICAL",
        "priority": "MEDIUM",
    }
    headers = auth_headers(customer_a)

    for _ in range(2):
        response = await client.post("/api/v1/tickets", json=payload, headers=headers)
        assert response.status_code == 201

    response = await client.post("/api/v1/tickets", json=payload, headers=headers)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


async def test_redis_failure_allows_request_to_continue() -> None:
    class UnavailableRedis:
        async def eval(self, *_args: object) -> object:
            raise RedisConnectionError("test Redis outage")

    decision = await consume_rate_limit(
        UnavailableRedis(),  # type: ignore[arg-type]
        key="rate_limit:test",
        limit=1,
    )

    assert decision.allowed is True
    assert decision.retry_after_seconds is None
