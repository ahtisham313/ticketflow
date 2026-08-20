"""Explicit webhook management and delivery-history API contracts."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.webhook import WebhookEventType


class WebhookCreateRequest(BaseModel):
    """Agent-controlled fields accepted for a webhook subscription."""

    model_config = ConfigDict(extra="forbid")

    url: Annotated[HttpUrl, Field(max_length=2048)]
    event_type: WebhookEventType

    @field_validator("url")
    @classmethod
    def reject_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        """Prevent embedded credentials from being stored or sent."""

        if value.username is not None or value.password is not None:
            raise ValueError("Webhook URL must not contain credentials")
        return value


class WebhookRegistrationResponse(BaseModel):
    """Safe registration representation that deliberately omits the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: HttpUrl
    event_type: WebhookEventType
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime


class WebhookCreateResponse(WebhookRegistrationResponse):
    """One-time creation representation containing the signing secret."""

    secret: str


class WebhookDeliveryResponse(BaseModel):
    """One immutable outgoing delivery-attempt audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    webhook_registration_id: uuid.UUID
    event_type: WebhookEventType
    payload: dict[str, Any]
    success: bool
    response_code: int | None
    error_message: str | None
    attempted_at: datetime


class WebhookEventEnvelope(BaseModel):
    """Stable payload shared by every registration receiving one event."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    event: WebhookEventType
    timestamp: datetime
    data: dict[str, Any]
