"""Ticket comment HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.comment import CommentCreateRequest, CommentResponse
from app.services.comment_service import create_comment, list_comments
from app.services.ws_manager import (
    DASHBOARD_CHANNEL,
    connection_manager,
    ticket_channel,
)

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

    comments = await list_comments(session, ticket_id, current_user)

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

    comment = await create_comment(
        session,
        ticket_id,
        current_user,
        payload.body,
    )

    response = CommentResponse.model_validate(comment)
    event = {
        "event": "comment.created",
        "ticket_id": str(ticket_id),
        "data": response.model_dump(mode="json"),
    }
    await connection_manager.broadcast(ticket_channel(ticket_id), event)
    await connection_manager.broadcast(DASHBOARD_CHANNEL, event)
    return response
