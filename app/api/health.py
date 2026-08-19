"""Application and dependency health checks."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public health status for the API and its required dependencies."""

    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    redis: Literal["ok", "error"]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health_check(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HealthResponse | JSONResponse:
    """Report whether the API can communicate with PostgreSQL and Redis."""

    database_status: Literal["ok", "error"] = "ok"
    redis_status: Literal["ok", "error"] = "ok"

    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "error"

    redis_client = cast(Redis, request.app.state.redis)
    try:
        await redis_client.ping()
    except RedisError:
        redis_status = "error"

    response = HealthResponse(
        status=(
            "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
        ),
        database=database_status,
        redis=redis_status,
    )

    if response.status == "degraded":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )

    return response
