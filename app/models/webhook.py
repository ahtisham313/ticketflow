"""Webhook registration and delivery audit models."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class WebhookEventType(str, enum.Enum):
    """Events that can be delivered to registered webhook endpoints."""

    # Member names match the existing PostgreSQL enum labels. Values are the
    # stable public event names used by REST, WebSockets, and outgoing payloads.
    TICKET_CREATED = "ticket.created"
    TICKET_STATUS_CHANGED = "ticket.status_changed"


WEBHOOK_EVENT_DB_ENUM = SAEnum(
    WebhookEventType,
    name="webhook_event_type",
    native_enum=True,
    validate_strings=True,
)


class WebhookRegistration(Base):
    """An agent-managed outgoing webhook subscription."""

    __tablename__ = "webhook_registrations"
    __table_args__ = (
        Index("ix_webhook_registrations_created_by", "created_by"),
        Index("ix_webhook_registrations_event_type", "event_type"),
        Index("ix_webhook_registrations_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[WebhookEventType] = mapped_column(
        WEBHOOK_EVENT_DB_ENUM,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    creator: Mapped["User"] = relationship(back_populates="webhook_registrations")
    delivery_logs: Mapped[list["WebhookDeliveryLog"]] = relationship(
        back_populates="webhook_registration"
    )


class WebhookDeliveryLog(Base):
    """An immutable record of one outgoing webhook delivery attempt."""

    __tablename__ = "webhook_delivery_logs"
    __table_args__ = (
        CheckConstraint(
            "response_code IS NULL OR response_code BETWEEN 100 AND 599",
            name="response_code_valid",
        ),
        Index(
            "ix_webhook_delivery_logs_webhook_registration_id",
            "webhook_registration_id",
        ),
        Index("ix_webhook_delivery_logs_event_type", "event_type"),
        Index("ix_webhook_delivery_logs_attempted_at", "attempted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    webhook_registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "webhook_registrations.id",
            name="fk_delivery_logs_registration",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_type: Mapped[WebhookEventType] = mapped_column(
        WEBHOOK_EVENT_DB_ENUM,
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    webhook_registration: Mapped["WebhookRegistration"] = relationship(
        back_populates="delivery_logs"
    )
