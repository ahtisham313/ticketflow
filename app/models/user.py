"""User model and role definitions."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.ticket import Ticket
    from app.models.webhook import WebhookRegistration


class UserRole(str, enum.Enum):
    """Roles that control TicketFlow authorization."""

    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"


USER_ROLE_DB_ENUM = SAEnum(
    UserRole,
    name="user_role",
    native_enum=True,
    validate_strings=True,
)


class User(Base):
    """A customer or support agent account."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(USER_ROLE_DB_ENUM, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
    webhook_registrations: Mapped[list["WebhookRegistration"]] = relationship(
        back_populates="creator"
    )
