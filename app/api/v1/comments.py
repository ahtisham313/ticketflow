"""Ticket comment HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.comment import CommentCreateRequest, CommentResponse
from app.services.comment_service import create_comment, list_comments
from app.services.ticket_service import TicketNotFoundError

router = APIRouter(
    prefix="/api/v1/tickets/{ticket_id}/comments",
    tags=["comments"],
)


@router.get("", response_model=list[CommentResponse])
async def get_list(
    ticket_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CommentResponse]:
    """Return an accessible ticket's immutable chronological comment thread."""

    try:
        comments = await list_comments(session, ticket_id, current_user)
    except TicketNotFoundError:
        raise _ticket_not_found() from None

    return [CommentResponse.model_validate(comment) for comment in comments]


@router.post(
    "",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    ticket_id: uuid.UUID,
    payload: CommentCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommentResponse:
    """Post a trusted-role comment to an accessible ticket."""

    try:
        comment = await create_comment(
            session,
            ticket_id,
            current_user,
            payload.body,
        )
    except TicketNotFoundError:
        raise _ticket_not_found() from None

    return CommentResponse.model_validate(comment)


def _ticket_not_found() -> HTTPException:
    """Hide whether a customer-inaccessible ticket exists."""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Ticket not found",
    )
