"""Ticket HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_agent, require_customer
from app.db.session import get_db_session
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketListResponse,
    TicketResponse,
    TicketStatusUpdateRequest,
    TicketUpdateRequest,
)
from app.services.ticket_service import (
    TicketNotFoundError,
    TicketStateError,
    change_ticket_status,
    create_ticket,
    delete_open_ticket,
    get_accessible_ticket,
    list_tickets,
    update_open_ticket,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: TicketCreateRequest,
    customer: Annotated[User, Depends(require_customer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    """Create an OPEN ticket for the authenticated customer."""

    ticket = await create_ticket(
        session,
        customer,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
    )
    return TicketResponse.model_validate(ticket)


@router.get("", response_model=TicketListResponse)
async def get_list(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TicketListResponse:
    """List tickets with SQL ownership scoping, filters, search, and pagination."""

    result = await list_tickets(
        session,
        current_user,
        status=status_filter,
        priority=priority,
        category=category,
        query=q,
        page=page,
        page_size=page_size,
    )
    return TicketListResponse(
        items=[TicketResponse.model_validate(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        pages=result.pages,
    )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_detail(
    ticket_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    """Return a ticket only when it is inside the user's access scope."""

    try:
        ticket = await get_accessible_ticket(session, ticket_id, current_user)
    except TicketNotFoundError:
        raise _ticket_not_found() from None

    return TicketResponse.model_validate(ticket)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    customer: Annotated[User, Depends(require_customer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    """Partially update a customer-owned OPEN ticket."""

    try:
        ticket = await update_open_ticket(
            session,
            ticket_id,
            customer,
            payload.model_dump(exclude_unset=True),
        )
    except TicketNotFoundError:
        raise _ticket_not_found() from None
    except TicketStateError as exc:
        raise _ticket_state_error(exc) from None

    return TicketResponse.model_validate(ticket)


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete(
    ticket_id: uuid.UUID,
    customer: Annotated[User, Depends(require_customer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Hard-delete a customer-owned OPEN ticket and its comments."""

    try:
        await delete_open_ticket(session, ticket_id, customer)
    except TicketNotFoundError:
        raise _ticket_not_found() from None
    except TicketStateError as exc:
        raise _ticket_state_error(exc) from None

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
async def update_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdateRequest,
    _agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    """Move a ticket through exactly one valid workflow transition."""

    try:
        ticket = await change_ticket_status(session, ticket_id, payload.status)
    except TicketNotFoundError:
        raise _ticket_not_found() from None
    except TicketStateError as exc:
        raise _ticket_state_error(exc) from None

    return TicketResponse.model_validate(ticket)


def _ticket_not_found() -> HTTPException:
    """Return the same 404 for missing and customer-inaccessible tickets."""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Ticket not found",
    )


def _ticket_state_error(exc: TicketStateError) -> HTTPException:
    """Translate a service business-rule error to HTTP 400."""

    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )
