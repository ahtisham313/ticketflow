"""Reusable authentication and role-authorization dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenType, TokenValidationError, decode_token
from app.api.errors import APIException
from app.db.session import get_db_session
from app.models.user import User, UserRole
from app.services.auth_service import get_user_by_id

bearer_scheme = HTTPBearer(auto_error=False)


def get_redis(request: Request) -> Redis:
    """Return the process-wide Redis client owned by the FastAPI lifespan."""

    return cast(Redis, request.app.state.redis)


def _authentication_exception() -> APIException:
    """Create the consistent 401 response used by protected endpoints."""

    return APIException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="AUTHENTICATION_REQUIRED",
        message="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Validate an access token and return the trusted current database user."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_exception()

    try:
        user_id = decode_token(
            credentials.credentials,
            expected_type=TokenType.ACCESS,
        )
    except TokenValidationError:
        raise _authentication_exception() from None

    # JWTs identify a user; the database remains authoritative for existence and role.
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise _authentication_exception()

    return user


async def require_agent(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Allow only a currently authenticated database AGENT."""

    if current_user.role != UserRole.AGENT:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Agent access required",
        )

    return current_user


async def require_customer(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Allow only a currently authenticated database CUSTOMER."""

    if current_user.role != UserRole.CUSTOMER:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Customer access required",
        )

    return current_user
