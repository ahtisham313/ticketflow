"""Ticket request and response contracts."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ticket import TicketCategory, TicketPriority, TicketStatus


class TicketCreateRequest(BaseModel):
    """Customer-controlled fields accepted when creating a ticket."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    category: TicketCategory
    priority: TicketPriority

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        """Trim text before length validation and reject whitespace-only values."""

        return value.strip() if isinstance(value, str) else value


class TicketUpdateRequest(BaseModel):
    """Allowed fields for a partial customer ticket update."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    category: TicketCategory | None = None
    priority: TicketPriority | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        """Trim supplied text before applying field constraints."""

        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_non_null_update(self) -> "TicketUpdateRequest":
        """Reject empty PATCH bodies and explicit null replacements."""

        if not self.model_fields_set:
            raise ValueError("At least one ticket field must be supplied")

        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class TicketStatusUpdateRequest(BaseModel):
    """Dedicated agent-controlled ticket status update."""

    model_config = ConfigDict(extra="forbid")

    status: TicketStatus


class TicketResponse(BaseModel):
    """Public ticket representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    """Paginated ticket collection and navigation metadata."""

    items: list[TicketResponse]
    page: int
    page_size: int
    total: int
    pages: int
