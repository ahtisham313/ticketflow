"""Authenticated, authorization-scoped WebSocket subscriptions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenType, TokenValidationError, decode_token
from app.db.session import get_db_session
from app.models.user import User, UserRole
from app.services.auth_service import get_user_by_id
from app.services.ticket_service import TicketNotFoundError, get_accessible_ticket
from app.services.ws_manager import (
    DASHBOARD_CHANNEL,
    connection_manager,
    ticket_channel,
)

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/tickets/{ticket_id}")
async def ticket_updates(
    websocket: WebSocket,
    ticket_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
) -> None:
    """Stream events only when the current user may access this ticket."""

    current_user = await _authenticate(websocket, token, session)
    if current_user is None:
        return

    try:
        await get_accessible_ticket(session, ticket_id, current_user)
    except TicketNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await session.close()
    await _serve_channel(websocket, ticket_channel(ticket_id))


@router.websocket("/ws/dashboard")
async def dashboard_updates(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
) -> None:
    """Stream dashboard-relevant events only to a current database agent."""

    current_user = await _authenticate(websocket, token, session)
    if current_user is None:
        return

    if current_user.role != UserRole.AGENT:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await session.close()
    await _serve_channel(websocket, DASHBOARD_CHANNEL)


async def _authenticate(
    websocket: WebSocket,
    token: str | None,
    session: AsyncSession,
) -> User | None:
    """Validate an access JWT and return its current database user."""

    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    try:
        user_id = decode_token(token, expected_type=TokenType.ACCESS)
    except TokenValidationError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    current_user = await get_user_by_id(session, user_id)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    return current_user


async def _serve_channel(websocket: WebSocket, channel: str) -> None:
    """Register a socket, keep it open for notifications, and always clean up."""

    await connection_manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(channel, websocket)
