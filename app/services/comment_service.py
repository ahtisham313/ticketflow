"""Ticket comment authorization, creation, and chronological retrieval."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.user import User
from app.services.ticket_service import get_accessible_ticket


async def create_comment(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
    body: str,
) -> Comment:
    """Create a comment after enforcing ticket access for the current user."""

    ticket = await get_accessible_ticket(
        session,
        ticket_id,
        current_user,
        for_update=True,
    )
    comment = Comment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        author_role=current_user.role,
        body=body,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def list_comments(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
) -> list[Comment]:
    """Return an accessible ticket's comments from oldest to newest."""

    ticket = await get_accessible_ticket(session, ticket_id, current_user)
    statement = (
        select(Comment)
        .where(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    )
    return list((await session.scalars(statement)).all())
