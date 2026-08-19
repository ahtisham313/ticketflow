"""Explicit authentication API contracts."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

from app.models.user import UserRole


class _EmailPasswordRequest(BaseModel):
    """Shared strict contract for email/password authentication requests."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def strip_email_whitespace(cls, value: Any) -> Any:
        """Allow harmless surrounding whitespace before EmailStr validation."""

        return value.strip() if isinstance(value, str) else value


class UserRegisterRequest(_EmailPasswordRequest):
    """Public customer-registration request; a role is intentionally absent."""


class LoginRequest(_EmailPasswordRequest):
    """JSON login credentials."""


class RefreshTokenRequest(BaseModel):
    """A stateless refresh-token exchange request."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: SecretStr = Field(min_length=1, max_length=4096)


class TokenPairResponse(BaseModel):
    """Access and refresh tokens returned after a successful login."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_in: int


class AccessTokenResponse(BaseModel):
    """A fresh access token returned from a valid refresh token."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_in: int


class CurrentUserResponse(BaseModel):
    """Safe public account fields used by registration and /auth/me."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime
