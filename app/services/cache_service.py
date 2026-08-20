"""Small Redis cache helpers for ticket lists and dashboard statistics."""

import hashlib
import json
import logging
from dataclasses import dataclass

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardStatsResponse
from app.schemas.ticket import TicketListResponse

logger = logging.getLogger(__name__)

TICKET_LIST_VERSION_KEY = "tickets:list:version"
DASHBOARD_STATS_KEY = "dashboard:stats"


@dataclass(frozen=True, slots=True)
class TicketListCacheParameters:
    """Every query dimension that changes a ticket-list response."""

    status: TicketStatus | None
    priority: TicketPriority | None
    category: TicketCategory | None
    query: str | None
    page: int
    page_size: int


async def resolve_ticket_list_cache_key(
    redis: Redis,
    current_user: User,
    parameters: TicketListCacheParameters,
) -> str | None:
    """Resolve the current versioned key or return None when Redis is unavailable."""

    try:
        await redis.set(TICKET_LIST_VERSION_KEY, "1", nx=True)
        raw_version = await redis.get(TICKET_LIST_VERSION_KEY)
        version = int(raw_version)
    except (RedisError, TypeError, ValueError):
        logger.warning("Ticket-list cache version lookup failed", exc_info=True)
        return None

    scope = (
        "agent"
        if current_user.role == UserRole.AGENT
        else f"customer:{current_user.id}"
    )
    normalized_query = parameters.query.strip() if parameters.query is not None else ""
    # Canonical JSON ensures equivalent filters always produce the same hash.
    canonical_parameters = {
        "category": (
            parameters.category.value if parameters.category is not None else None
        ),
        "page": parameters.page,
        "page_size": parameters.page_size,
        "priority": (
            parameters.priority.value if parameters.priority is not None else None
        ),
        "q": normalized_query or None,
        "status": parameters.status.value if parameters.status is not None else None,
    }
    canonical_json = json.dumps(
        canonical_parameters,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    filter_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"tickets:list:v{version}:{scope}:{filter_hash}"


async def get_cached_ticket_list(
    redis: Redis,
    cache_key: str | None,
) -> TicketListResponse | None:
    """Load and validate a cached ticket list, treating failures as cache misses."""

    if cache_key is None:
        return None

    try:
        cached_json = await redis.get(cache_key)
    except RedisError:
        logger.warning("Ticket-list cache read failed", exc_info=True)
        return None

    if cached_json is None:
        return None

    try:
        return TicketListResponse.model_validate_json(cached_json)
    except (ValidationError, ValueError):
        logger.warning("Ticket-list cache contained invalid JSON", exc_info=True)
        return None


async def set_cached_ticket_list(
    redis: Redis,
    cache_key: str | None,
    response: TicketListResponse,
) -> None:
    """Store a validated ticket-list response using the configured TTL."""

    if cache_key is None:
        return

    try:
        await redis.set(
            cache_key,
            response.model_dump_json(),
            ex=get_settings().ticket_list_cache_ttl_seconds,
        )
    except RedisError:
        logger.warning("Ticket-list cache write failed", exc_info=True)


async def get_cached_dashboard_stats(redis: Redis) -> DashboardStatsResponse | None:
    """Load and validate cached dashboard statistics."""

    try:
        cached_json = await redis.get(DASHBOARD_STATS_KEY)
    except RedisError:
        logger.warning("Dashboard cache read failed", exc_info=True)
        return None

    if cached_json is None:
        return None

    try:
        return DashboardStatsResponse.model_validate_json(cached_json)
    except (ValidationError, ValueError):
        logger.warning("Dashboard cache contained invalid JSON", exc_info=True)
        return None


async def set_cached_dashboard_stats(
    redis: Redis,
    response: DashboardStatsResponse,
) -> None:
    """Store dashboard statistics using the configured TTL."""

    try:
        await redis.set(
            DASHBOARD_STATS_KEY,
            response.model_dump_json(),
            ex=get_settings().dashboard_cache_ttl_seconds,
        )
    except RedisError:
        logger.warning("Dashboard cache write failed", exc_info=True)


async def invalidate_ticket_caches(redis: Redis) -> None:
    """Atomically advance list version and remove the fixed dashboard entry."""

    try:
        async with redis.pipeline(transaction=True) as pipeline:
            # A version bump invalidates every filtered list key without a key scan.
            pipeline.set(TICKET_LIST_VERSION_KEY, "1", nx=True)
            pipeline.incr(TICKET_LIST_VERSION_KEY)
            pipeline.delete(DASHBOARD_STATS_KEY)
            await pipeline.execute()
    except RedisError:
        # PostgreSQL has already committed; cache invalidation remains best effort.
        logger.warning("Post-commit ticket cache invalidation failed", exc_info=True)
