"""Authentication business flows and user persistence operations."""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    TokenType,
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole


class DuplicateEmailError(ValueError):
    """Raised when a normalized email is already registered."""


class AuthenticationError(ValueError):
    """Raised for deliberately generic authentication failures."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Tokens and access-token lifetime produced by a successful login."""

    access_token: str
    refresh_token: str
    access_expires_in: int


@dataclass(frozen=True, slots=True)
class FreshAccessToken:
    """Access token and lifetime produced by a refresh exchange."""

    access_token: str
    access_expires_in: int


def normalize_email(email: str) -> str:
    """Apply the same lookup and storage normalization to every email."""

    return email.strip().lower()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Load a user by normalized email."""

    normalized_email = normalize_email(email)
    return await session.scalar(select(User).where(User.email == normalized_email))


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Load the current database representation of a user."""

    return await session.get(User, user_id)


async def register_customer(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    """Register a CUSTOMER and handle duplicate-email races safely."""

    normalized_email = normalize_email(email)
    if await get_user_by_email(session, normalized_email) is not None:
        raise DuplicateEmailError

    hashed_password = await asyncio.to_thread(hash_password, password)
    user = User(
        email=normalized_email,
        password_hash=hashed_password,
        role=UserRole.CUSTOMER,
    )
    session.add(user)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEmailError from exc

    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    """Validate email/password credentials without revealing which part failed."""

    user = await get_user_by_email(session, email)
    if user is None:
        raise AuthenticationError

    password_is_valid = await asyncio.to_thread(
        verify_password,
        password,
        user.password_hash,
    )
    if not password_is_valid:
        raise AuthenticationError

    return user


async def login_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> TokenPair:
    """Authenticate a user and issue an access/refresh token pair."""

    user = await authenticate_user(session, email, password)
    settings = get_settings()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        access_expires_in=settings.access_token_expire_minutes * 60,
    )


async def issue_access_token_from_refresh(
    session: AsyncSession,
    refresh_token: str,
) -> FreshAccessToken:
    """Validate a refresh token and issue a new access token for an existing user."""

    try:
        user_id = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except TokenValidationError as exc:
        raise AuthenticationError from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AuthenticationError

    settings = get_settings()
    return FreshAccessToken(
        access_token=create_access_token(user.id),
        access_expires_in=settings.access_token_expire_minutes * 60,
    )
