"""Agent dashboard statistics endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis, require_agent
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.dashboard import DashboardStatsResponse
from app.services.cache_service import (
    get_cached_dashboard_stats,
    set_cached_dashboard_stats,
)
from app.services.dashboard_service import calculate_dashboard_stats

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats(
    _agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> DashboardStatsResponse:
    """Return cached or freshly aggregated ticket statistics to an agent."""

    cached_response = await get_cached_dashboard_stats(redis)
    if cached_response is not None:
        return cached_response

    response = await calculate_dashboard_stats(session)
    await set_cached_dashboard_stats(redis, response)
    return response
