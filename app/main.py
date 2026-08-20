"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.health import router as health_router
from app.api.errors import COMMON_ERROR_RESPONSES, register_exception_handlers
from app.api.v1.auth import router as auth_router
from app.api.v1.comments import router as comments_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.ws import router as ws_router
from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close process-wide external resource clients."""

    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    # One process-wide client lets redis-py reuse its connection pool per request.
    app.state.redis = redis_client

    try:
        yield
    finally:
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
    responses=COMMON_ERROR_RESPONSES,
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(comments_router)
app.include_router(dashboard_router)
app.include_router(webhooks_router)
app.include_router(ws_router)
