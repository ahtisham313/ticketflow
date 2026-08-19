"""Password hashing and JWT primitives for authentication."""

import enum
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError as PyJWTInvalidTokenError
from pwdlib import PasswordHash

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
_password_hash = PasswordHash.recommended()


class TokenType(str, enum.Enum):
    """JWT purposes that must never be used interchangeably."""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenValidationError(ValueError):
    """Raised when a JWT cannot be trusted for its expected purpose."""


def hash_password(password: str) -> str:
    """Hash a plaintext password with pwdlib's recommended Argon2 settings."""

    return _password_hash.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Safely verify a plaintext password against a stored password hash."""

    try:
        return _password_hash.verify(plain_password, password_hash)
    except ValueError:
        # A malformed or unsupported stored hash is an authentication failure.
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    """Create a short-lived access JWT for one database user."""

    settings = get_settings()
    return _create_token(
        user_id=user_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a longer-lived stateless refresh JWT for one database user."""

    settings = get_settings()
    return _create_token(
        user_id=user_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    """Validate a JWT and return its UUID subject for the expected token type."""

    settings = get_settings()

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "type", "iat", "exp"]},
        )
    except PyJWTInvalidTokenError as exc:
        raise TokenValidationError("Token validation failed") from exc

    if payload.get("type") != expected_type.value:
        raise TokenValidationError("Incorrect token type")

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise TokenValidationError("Invalid token subject")

    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise TokenValidationError("Invalid token subject") from exc


def _create_token(
    user_id: uuid.UUID,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    """Create a signed JWT with the claims shared by both token types."""

    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type.value,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )
