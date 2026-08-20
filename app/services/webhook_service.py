"""Webhook registration, deterministic signing, delivery, and audit logging."""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.user import User
from app.models.webhook import (
    WebhookDeliveryLog,
    WebhookEventType,
    WebhookRegistration,
)
from app.schemas.webhook import WebhookEventEnvelope

logger = logging.getLogger(__name__)


class WebhookNotFoundError(LookupError):
    """Raised when an active registration cannot be found."""


@dataclass(frozen=True, slots=True)
class WebhookDeliveryTarget:
    """Immutable registration details captured when an event is scheduled."""

    registration_id: uuid.UUID
    url: str
    secret: str
    event_type: WebhookEventType


async def create_webhook_registration(
    session: AsyncSession,
    agent: User,
    *,
    url: str,
    event_type: WebhookEventType,
) -> WebhookRegistration:
    """Create an active subscription with a high-entropy server-side secret."""

    registration = WebhookRegistration(
        url=url,
        secret=secrets.token_hex(32),
        event_type=event_type,
        created_by=agent.id,
        is_active=True,
    )
    session.add(registration)
    await session.commit()
    await session.refresh(registration)
    return registration


async def list_webhook_registrations(
    session: AsyncSession,
) -> list[WebhookRegistration]:
    """Return all registrations, including deactivated audit-visible entries."""

    statement = select(WebhookRegistration).order_by(
        WebhookRegistration.created_at.desc(),
        WebhookRegistration.id.desc(),
    )
    return list((await session.scalars(statement)).all())


async def deactivate_webhook_registration(
    session: AsyncSession,
    webhook_id: uuid.UUID,
) -> None:
    """Soft-delete an active subscription while preserving delivery history."""

    statement = (
        select(WebhookRegistration)
        .where(
            WebhookRegistration.id == webhook_id,
            WebhookRegistration.is_active.is_(True),
        )
        .with_for_update()
    )
    registration = await session.scalar(statement)
    if registration is None:
        raise WebhookNotFoundError

    registration.is_active = False
    await session.commit()


async def list_webhook_deliveries(
    session: AsyncSession,
    *,
    limit: int,
) -> list[WebhookDeliveryLog]:
    """Return a bounded newest-first delivery history."""

    statement = (
        select(WebhookDeliveryLog)
        .order_by(
            WebhookDeliveryLog.attempted_at.desc(),
            WebhookDeliveryLog.id.desc(),
        )
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())


async def schedule_webhook_event(
    background_tasks: BackgroundTasks,
    session: AsyncSession,
    event_type: WebhookEventType,
    data: dict[str, Any],
) -> None:
    """Snapshot matching subscriptions and schedule one background dispatch."""

    statement = select(WebhookRegistration).where(
        WebhookRegistration.event_type == event_type,
        WebhookRegistration.is_active.is_(True),
    )
    registrations = list((await session.scalars(statement)).all())
    if not registrations:
        return

    targets = tuple(
        WebhookDeliveryTarget(
            registration_id=registration.id,
            url=registration.url,
            secret=registration.secret,
            event_type=registration.event_type,
        )
        for registration in registrations
    )
    envelope = WebhookEventEnvelope(
        id=uuid.uuid4(),
        event=event_type,
        timestamp=datetime.now(timezone.utc),
        data=data,
    ).model_dump(mode="json")
    body = serialize_webhook_payload(envelope)
    background_tasks.add_task(dispatch_webhook_event, targets, envelope, body)


def serialize_webhook_payload(payload: dict[str, Any]) -> bytes:
    """Produce the single deterministic JSON byte representation to be sent."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_webhook_payload(secret: str, body: bytes) -> str:
    """Return the HMAC-SHA256 signature header value for exact body bytes."""

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def dispatch_webhook_event(
    targets: tuple[WebhookDeliveryTarget, ...],
    payload: dict[str, Any],
    body: bytes,
) -> None:
    """Deliver independently to all captured targets without request resources."""

    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.webhook_delivery_timeout_seconds
    ) as client:
        results = await asyncio.gather(
            *(
                _deliver_to_target(client, target, payload, body)
                for target in targets
            ),
            return_exceptions=True,
        )

    for target, result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            logger.error(
                "Unexpected webhook delivery failure for registration %s",
                target.registration_id,
                exc_info=(type(result), result, result.__traceback__),
            )


async def _deliver_to_target(
    client: httpx.AsyncClient,
    target: WebhookDeliveryTarget,
    payload: dict[str, Any],
    body: bytes,
) -> None:
    """Perform and log exactly one delivery attempt with no retries."""

    delivery_id = uuid.uuid4()
    headers = {
        "Content-Type": "application/json",
        "X-TicketFlow-Signature": sign_webhook_payload(target.secret, body),
        "X-TicketFlow-Event": target.event_type.value,
        "X-TicketFlow-Delivery-ID": str(delivery_id),
    }

    response_code: int | None = None
    error_message: str | None = None
    success = False
    try:
        response = await client.post(target.url, content=body, headers=headers)
        response_code = response.status_code
        success = 200 <= response.status_code < 300
        if not success:
            error_message = f"Webhook endpoint returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        error_message = _sanitize_delivery_error(exc)

    await _record_delivery(
        delivery_id=delivery_id,
        target=target,
        payload=payload,
        success=success,
        response_code=response_code,
        error_message=error_message,
    )


async def _record_delivery(
    *,
    delivery_id: uuid.UUID,
    target: WebhookDeliveryTarget,
    payload: dict[str, Any],
    success: bool,
    response_code: int | None,
    error_message: str | None,
) -> None:
    """Persist an attempt using a background-owned database session."""

    async with async_session_factory() as session:
        session.add(
            WebhookDeliveryLog(
                id=delivery_id,
                webhook_registration_id=target.registration_id,
                event_type=target.event_type,
                payload=payload,
                success=success,
                response_code=response_code,
                error_message=error_message,
            )
        )
        await session.commit()


def _sanitize_delivery_error(exc: httpx.HTTPError) -> str:
    """Create a bounded single-line network error without response bodies."""

    message = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {message}"[:1000]
