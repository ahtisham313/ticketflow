"""Create the initial TicketFlow schema.

Revision ID: 20260819_0001
Revises: None
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "CUSTOMER",
    "AGENT",
    name="user_role",
    create_type=False,
)
ticket_category = postgresql.ENUM(
    "BILLING",
    "TECHNICAL",
    "GENERAL",
    name="ticket_category",
    create_type=False,
)
ticket_priority = postgresql.ENUM(
    "LOW",
    "MEDIUM",
    "HIGH",
    name="ticket_priority",
    create_type=False,
)
ticket_status = postgresql.ENUM(
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
    "CLOSED",
    name="ticket_status",
    create_type=False,
)
webhook_event_type = postgresql.ENUM(
    "TICKET_CREATED",
    "TICKET_STATUS_CHANGED",
    name="webhook_event_type",
    create_type=False,
)


def upgrade() -> None:
    """Create enums, tables, constraints, foreign keys, and indexes."""

    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    ticket_category.create(bind, checkfirst=True)
    ticket_priority.create(bind, checkfirst=True)
    ticket_status.create(bind, checkfirst=True)
    webhook_event_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", ticket_category, nullable=False),
        sa.Column("priority", ticket_priority, nullable=False),
        sa.Column(
            "status",
            ticket_status,
            server_default=sa.text("'OPEN'::ticket_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_tickets_customer_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
    )
    op.create_index("ix_tickets_category", "tickets", ["category"], unique=False)
    op.create_index(
        "ix_tickets_created_at", "tickets", ["created_at"], unique=False
    )
    op.create_index(
        "ix_tickets_customer_id", "tickets", ["customer_id"], unique=False
    )
    op.create_index("ix_tickets_priority", "tickets", ["priority"], unique=False)
    op.create_index("ix_tickets_status", "tickets", ["status"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_role", user_role, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_comments_author_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name="fk_comments_ticket_id_tickets",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_comments"),
    )
    op.create_index("ix_comments_author_id", "comments", ["author_id"], unique=False)
    op.create_index(
        "ix_comments_created_at", "comments", ["created_at"], unique=False
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"], unique=False)

    op.create_table(
        "webhook_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column("event_type", webhook_event_type, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_webhook_registrations_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_registrations"),
    )
    op.create_index(
        "ix_webhook_registrations_created_by",
        "webhook_registrations",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_registrations_event_type",
        "webhook_registrations",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_registrations_is_active",
        "webhook_registrations",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "webhook_registration_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("event_type", webhook_event_type, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "response_code IS NULL OR response_code BETWEEN 100 AND 599",
            name="response_code_valid",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_registration_id"],
            ["webhook_registrations.id"],
            name="fk_delivery_logs_registration",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_delivery_logs"),
    )
    op.create_index(
        "ix_webhook_delivery_logs_attempted_at",
        "webhook_delivery_logs",
        ["attempted_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_delivery_logs_event_type",
        "webhook_delivery_logs",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_delivery_logs_webhook_registration_id",
        "webhook_delivery_logs",
        ["webhook_registration_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the complete initial TicketFlow schema."""

    op.drop_table("webhook_delivery_logs")
    op.drop_table("webhook_registrations")
    op.drop_table("comments")
    op.drop_table("tickets")
    op.drop_table("users")

    bind = op.get_bind()
    webhook_event_type.drop(bind, checkfirst=True)
    ticket_status.drop(bind, checkfirst=True)
    ticket_priority.drop(bind, checkfirst=True)
    ticket_category.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
