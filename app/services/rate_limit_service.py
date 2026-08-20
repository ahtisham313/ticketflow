"""Small Redis-backed fixed-window rate limiter."""

import logging
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

LOGIN_RATE_LIMIT = 5
TICKET_CREATE_RATE_LIMIT = 30
RATE_LIMIT_WINDOW_SECONDS = 60

_FIXED_WINDOW_SCRIPT = """
local count = redis.call("INCR", KEYS[1])
if count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

local ttl = redis.call("TTL", KEYS[1])
if ttl < 0 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end

return {count, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of consuming one request from a fixed-window quota."""

    allowed: bool
    retry_after_seconds: int | None = None


def login_rate_limit_key(client_ip: str) -> str:
    """Scope an unauthenticated login quota to the connecting client IP."""

    return f"rate_limit:login:{client_ip}"


def ticket_create_rate_limit_key(customer_id: object) -> str:
    """Scope ticket creation to the authenticated database user."""

    return f"rate_limit:ticket_create:{customer_id}"


async def consume_rate_limit(
    redis: Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
) -> RateLimitDecision:
    """Consume one quota unit atomically and fail open when Redis is unavailable."""

    try:
        result = await redis.eval(_FIXED_WINDOW_SCRIPT, 1, key, window_seconds)
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError("Unexpected Redis rate-limit response")

        count = int(result[0])
        ttl = int(result[1])
    except (RedisError, TypeError, ValueError):
        logger.warning(
            "Redis rate-limit check failed; allowing request",
            exc_info=True,
        )
        return RateLimitDecision(allowed=True)

    if count <= limit:
        return RateLimitDecision(allowed=True)

    return RateLimitDecision(
        allowed=False,
        retry_after_seconds=max(ttl, 1),
    )
