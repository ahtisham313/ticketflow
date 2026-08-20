"""Shared fixtures for isolated async API tests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise pytest.UsageError(
        "TEST_DATABASE_URL is required and must point to an isolated *_test database"
    )

try:
    test_database_name = make_url(TEST_DATABASE_URL).database
except Exception as exc:
    raise pytest.UsageError("TEST_DATABASE_URL is not a valid SQLAlchemy URL") from exc

if not test_database_name or not test_database_name.endswith("_test"):
    raise pytest.UsageError(
        "Refusing to run: TEST_DATABASE_URL database name must end with '_test'"
    )

# Application modules read settings at import time, so establish safe test values first.
os.environ["APP_ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-at-least-32-characters")
os.environ.setdefault("SEEDED_AGENT_EMAIL", "test-agent@example.com")
os.environ.setdefault("SEEDED_AGENT_PASSWORD", "TestOnlyAgent123!")

from app.core.config import get_settings

get_settings.cache_clear()

from app.core.deps import get_redis
from app.core.security import create_access_token, hash_password
from app.db.session import get_db_session
from app.main import app
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models.user import User, UserRole

TEST_PASSWORD = "TestPassword123!"

UserFactory = Callable[..., Awaitable[User]]
TicketFactory = Callable[..., Awaitable[Ticket]]
AuthHeadersFactory = Callable[[User], dict[str, str]]


class FakeRedis:
    """Minimal Redis behavior needed by ticket-list caching during API tests."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._values.get(key)

    async def set(
        self,
        key: str,
        value: object,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        del ex
        if nx and key in self._values:
            return False
        self._values[key] = str(value)
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        value = int(self._values.get(key, "0")) + amount
        self._values[key] = str(value)
        return value

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._values:
                removed += 1
                del self._values[key]
        return removed

    def pipeline(self, *, transaction: bool = True) -> FakeRedisPipeline:
        del transaction
        return FakeRedisPipeline(self)


class FakeRedisPipeline:
    """Queue Redis operations and apply them together when execute is awaited."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self) -> FakeRedisPipeline:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def set(self, key: str, value: object, *, nx: bool = False) -> FakeRedisPipeline:
        self._operations.append(("set", (key, value), {"nx": nx}))
        return self

    def incr(self, key: str) -> FakeRedisPipeline:
        self._operations.append(("incr", (key,), {}))
        return self

    def delete(self, key: str) -> FakeRedisPipeline:
        self._operations.append(("delete", (key,), {}))
        return self

    async def execute(self) -> list[object]:
        results = []
        for method_name, args, kwargs in self._operations:
            method = getattr(self._redis, method_name)
            results.append(await method(*args, **kwargs))
        return results


def _session(connection: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def db_connection() -> AsyncIterator[AsyncConnection]:
    """Wrap each test in a transaction that is always rolled back."""

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_connection: AsyncConnection) -> AsyncIterator[AsyncClient]:
    """Call FastAPI in-process with isolated database and Redis dependencies."""

    fake_redis = FakeRedis()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with _session(db_connection) as session:
            yield session

    def override_redis() -> FakeRedis:
        return fake_redis

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_redis] = override_redis

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_redis, None)


@pytest_asyncio.fixture
async def user_factory(db_connection: AsyncConnection) -> UserFactory:
    async def create_user(
        *,
        email: str,
        role: UserRole,
        password: str = TEST_PASSWORD,
    ) -> User:
        password_hash = await asyncio.to_thread(hash_password, password)
        async with _session(db_connection) as session:
            user = User(email=email, password_hash=password_hash, role=role)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return create_user


@pytest_asyncio.fixture
async def customer_a(user_factory: UserFactory) -> User:
    return await user_factory(email="customer-a@example.com", role=UserRole.CUSTOMER)


@pytest_asyncio.fixture
async def customer_b(user_factory: UserFactory) -> User:
    return await user_factory(email="customer-b@example.com", role=UserRole.CUSTOMER)


@pytest_asyncio.fixture
async def agent(user_factory: UserFactory) -> User:
    return await user_factory(email="agent@example.com", role=UserRole.AGENT)


@pytest.fixture
def auth_headers() -> AuthHeadersFactory:
    def build(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return build


@pytest_asyncio.fixture
async def ticket_factory(db_connection: AsyncConnection) -> TicketFactory:
    async def create_test_ticket(
        customer: User,
        *,
        title: str = "Test ticket",
        status: TicketStatus = TicketStatus.OPEN,
    ) -> Ticket:
        async with _session(db_connection) as session:
            ticket = Ticket(
                customer_id=customer.id,
                title=title,
                description="A test ticket description",
                category=TicketCategory.TECHNICAL,
                priority=TicketPriority.MEDIUM,
                status=status,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
            return ticket

    return create_test_ticket
