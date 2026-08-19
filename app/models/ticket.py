"""Support ticket model and ticket-related enums."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.user import User


class TicketCategory(str, enum.Enum):
    """Supported classifications for a ticket."""

    BILLING = "BILLING"
    TECHNICAL = "TECHNICAL"
    GENERAL = "GENERAL"


class TicketPriority(str, enum.Enum):
    """Supported urgency levels for a ticket."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TicketStatus(str, enum.Enum):
    """Ordered states in the ticket lifecycle."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


TICKET_CATEGORY_DB_ENUM = SAEnum(
    TicketCategory,
    name="ticket_category",
    native_enum=True,
    validate_strings=True,
)
TICKET_PRIORITY_DB_ENUM = SAEnum(
    TicketPriority,
    name="ticket_priority",
    native_enum=True,
    validate_strings=True,
)
TICKET_STATUS_DB_ENUM = SAEnum(
    TicketStatus,
    name="ticket_status",
    native_enum=True,
    validate_strings=True,
)


class Ticket(Base):
    """A support request owned by one customer."""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_customer_id", "customer_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_category", "category"),
        Index("ix_tickets_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[TicketCategory] = mapped_column(
        TICKET_CATEGORY_DB_ENUM,
        nullable=False,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        TICKET_PRIORITY_DB_ENUM,
        nullable=False,
    )
    status: Mapped[TicketStatus] = mapped_column(
        TICKET_STATUS_DB_ENUM,
        nullable=False,
        default=TicketStatus.OPEN,
        server_default=TicketStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped["User"] = relationship(back_populates="tickets")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
