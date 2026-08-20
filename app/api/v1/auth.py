"""Authentication HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import rate_limit_exception
from app.core.deps import get_current_user, get_redis
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserRegisterRequest,
)
from app.services.auth_service import (
    issue_access_token_from_refresh,
    login_user,
    register_customer,
)
from app.services.rate_limit_service import (
    LOGIN_RATE_LIMIT,
    consume_rate_limit,
    login_rate_limit_key,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserResponse:
    """Register a public account as a CUSTOMER."""

    user = await register_customer(
        session,
        email=str(payload.email),
        password=payload.password.get_secret_value(),
    )

    return CurrentUserResponse.model_validate(user)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    redis: Annotated[Redis, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenPairResponse:
    """Authenticate credentials and return access and refresh tokens."""

    client_ip = request.client.host if request.client is not None else "unknown"
    rate_limit = await consume_rate_limit(
        redis,
        key=login_rate_limit_key(client_ip),
        limit=LOGIN_RATE_LIMIT,
    )
    if not rate_limit.allowed:
        raise rate_limit_exception(rate_limit.retry_after_seconds or 1)

    tokens = await login_user(
        session,
        email=str(payload.email),
        password=payload.password.get_secret_value(),
    )

    return TokenPairResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_expires_in=tokens.access_expires_in,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AccessTokenResponse:
    """Exchange a valid refresh token for a new access token."""

    token = await issue_access_token_from_refresh(
        session,
        payload.refresh_token.get_secret_value(),
    )

    return AccessTokenResponse(
        access_token=token.access_token,
        access_expires_in=token.access_expires_in,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    """Return safe fields for the currently authenticated database user."""

    return CurrentUserResponse.model_validate(current_user)
