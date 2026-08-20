"""Agent-only webhook registration and delivery-history endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_agent
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookDeliveryResponse,
    WebhookRegistrationResponse,
)
from app.services.webhook_service import (
    WebhookNotFoundError,
    create_webhook_registration,
    deactivate_webhook_registration,
    list_webhook_deliveries,
    list_webhook_registrations,
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post(
    "",
    response_model=WebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: WebhookCreateRequest,
    agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WebhookCreateResponse:
    """Register an event endpoint and reveal its generated secret once."""

    registration = await create_webhook_registration(
        session,
        agent,
        url=str(payload.url),
        event_type=payload.event_type,
    )
    return WebhookCreateResponse.model_validate(registration)


@router.get("", response_model=list[WebhookRegistrationResponse])
async def get_list(
    _agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WebhookRegistrationResponse]:
    """List safe registration metadata without signing secrets."""

    registrations = await list_webhook_registrations(session)
    return [
        WebhookRegistrationResponse.model_validate(registration)
        for registration in registrations
    ]


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def get_deliveries(
    _agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[WebhookDeliveryResponse]:
    """Return a bounded newest-first webhook delivery history."""

    deliveries = await list_webhook_deliveries(session, limit=limit)
    return [
        WebhookDeliveryResponse.model_validate(delivery)
        for delivery in deliveries
    ]


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete(
    webhook_id: uuid.UUID,
    _agent: Annotated[User, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """Deactivate a subscription while retaining its delivery history."""

    try:
        await deactivate_webhook_registration(session, webhook_id)
    except WebhookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook registration not found",
        ) from None

    return Response(status_code=status.HTTP_204_NO_CONTENT)
