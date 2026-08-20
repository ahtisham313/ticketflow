"""Ticket access rules, querying, mutations, and status workflow."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.user import User, UserRole


class TicketNotFoundError(LookupError):
    """Raised when a ticket does not exist within the user's access scope."""


class TicketStateError(ValueError):
    """Raised when a ticket's current state forbids a requested mutation."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TicketPage:
    """Service result for one role-scoped page of tickets."""

    items: list[Ticket]
    page: int
    page_size: int
    total: int
    pages: int


@dataclass(frozen=True, slots=True)
class TicketStatusChange:
    """A committed status mutation and the state it replaced."""

    ticket: Ticket
    old_status: TicketStatus


ALLOWED_STATUS_TRANSITIONS: dict[TicketStatus, TicketStatus | None] = {
    TicketStatus.OPEN: TicketStatus.IN_PROGRESS,
    TicketStatus.IN_PROGRESS: TicketStatus.RESOLVED,
    TicketStatus.RESOLVED: TicketStatus.CLOSED,
    TicketStatus.CLOSED: None,
}


async def create_ticket(
    session: AsyncSession,
    customer: User,
    *,
    title: str,
    description: str,
    category: TicketCategory,
    priority: TicketPriority,
) -> Ticket:
    """Create an OPEN ticket owned by the authenticated customer."""

    ticket = Ticket(
        customer_id=customer.id,
        title=title,
        description=description,
        category=category,
        priority=priority,
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_accessible_ticket(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
    *,
    for_update: bool = False,
) -> Ticket:
    """Load one ticket using SQL-level ownership scoping for customers."""

    statement = select(Ticket).where(Ticket.id == ticket_id)
    if current_user.role == UserRole.CUSTOMER:
        # Scope in SQL so inaccessible and missing tickets have identical behavior.
        statement = statement.where(Ticket.customer_id == current_user.id)
    if for_update:
        # Serialize competing mutations before checking state-dependent rules.
        statement = statement.with_for_update()

    ticket = await session.scalar(statement)
    if ticket is None:
        raise TicketNotFoundError

    return ticket


async def list_tickets(
    session: AsyncSession,
    current_user: User,
    *,
    status: TicketStatus | None,
    priority: TicketPriority | None,
    category: TicketCategory | None,
    query: str | None,
    page: int,
    page_size: int,
) -> TicketPage:
    """Return one filtered and database-paginated role-aware ticket page."""

    conditions = []
    if current_user.role == UserRole.CUSTOMER:
        conditions.append(Ticket.customer_id == current_user.id)
    if status is not None:
        conditions.append(Ticket.status == status)
    if priority is not None:
        conditions.append(Ticket.priority == priority)
    if category is not None:
        conditions.append(Ticket.category == category)

    normalized_query = query.strip() if query is not None else ""
    if normalized_query:
        search_pattern = f"%{_escape_like(normalized_query)}%"
        conditions.append(
            or_(
                Ticket.title.ilike(search_pattern, escape="\\"),
                Ticket.description.ilike(search_pattern, escape="\\"),
            )
        )

    count_statement = select(func.count(Ticket.id)).where(*conditions)
    total = int(await session.scalar(count_statement) or 0)

    data_statement = (
        select(Ticket)
        .where(*conditions)
        # The UUID tie-breaker keeps pagination stable when timestamps match.
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await session.scalars(data_statement)).all())
    pages = (total + page_size - 1) // page_size if total else 0

    return TicketPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


async def update_open_ticket(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    customer: User,
    updates: dict[str, Any],
) -> Ticket:
    """Partially update a locked customer-owned ticket only while it is OPEN."""

    ticket = await get_accessible_ticket(
        session,
        ticket_id,
        customer,
        for_update=True,
    )
    _require_open(ticket, operation="updated")

    for field_name, value in updates.items():
        setattr(ticket, field_name, value)

    await session.commit()
    await session.refresh(ticket)
    return ticket


async def delete_open_ticket(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    customer: User,
) -> None:
    """Hard-delete a locked customer-owned ticket only while it is OPEN."""

    ticket = await get_accessible_ticket(
        session,
        ticket_id,
        customer,
        for_update=True,
    )
    _require_open(ticket, operation="deleted")

    await session.delete(ticket)
    await session.commit()


async def change_ticket_status(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    new_status: TicketStatus,
) -> TicketStatusChange:
    """Apply exactly the next allowed workflow state to a locked ticket."""

    statement = select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ticket = await session.scalar(statement)
    if ticket is None:
        raise TicketNotFoundError

    old_status = ticket.status
    expected_status = ALLOWED_STATUS_TRANSITIONS[old_status]
    if new_status != expected_status:
        raise TicketStateError(
            f"Invalid status transition from {ticket.status.value} "
            f"to {new_status.value}",
            code="INVALID_STATUS_TRANSITION",
        )

    ticket.status = new_status
    await session.commit()
    await session.refresh(ticket)
    return TicketStatusChange(ticket=ticket, old_status=old_status)


def _require_open(ticket: Ticket, *, operation: str) -> None:
    """Enforce the customer edit/delete rule."""

    if ticket.status != TicketStatus.OPEN:
        error_code = (
            "TICKET_NOT_EDITABLE" if operation == "updated" else "TICKET_NOT_DELETABLE"
        )
        raise TicketStateError(
            f"Only OPEN tickets can be {operation} by their customer",
            code=error_code,
        )


def _escape_like(value: str) -> str:
    """Treat user search text literally inside an ILIKE pattern."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
