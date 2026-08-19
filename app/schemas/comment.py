"""Comment request and response contracts."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class CommentCreateRequest(BaseModel):
    """The only client-controlled field for a new comment."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=5_000)

    @field_validator("body", mode="before")
    @classmethod
    def strip_body(cls, value: Any) -> Any:
        """Trim comment text before rejecting blank content."""

        return value.strip() if isinstance(value, str) else value


class CommentResponse(BaseModel):
    """Immutable public comment representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author_role: UserRole
    body: str
    created_at: datetime
