"""Sequential ticket workflow and post-transition mutability tests."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.models.ticket import Ticket, TicketStatus
from app.models.user import User

AuthHeadersFactory = Callable[[User], dict[str, str]]
TicketFactory = Callable[..., Awaitable[Ticket]]


async def test_agent_can_complete_all_valid_status_transitions(
    client: AsyncClient,
    customer_a: User,
    agent: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket = await ticket_factory(customer_a)
    path = f"/api/v1/tickets/{ticket.id}/status"

    for next_status in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        response = await client.patch(
            path,
            json={"status": next_status},
            headers=auth_headers(agent),
        )
        assert response.status_code == 200
        assert response.json()["status"] == next_status


@pytest.mark.parametrize(
    ("current_status", "requested_status"),
    [
        (TicketStatus.OPEN, TicketStatus.RESOLVED),
        (TicketStatus.OPEN, TicketStatus.CLOSED),
        (TicketStatus.IN_PROGRESS, TicketStatus.OPEN),
        (TicketStatus.IN_PROGRESS, TicketStatus.CLOSED),
        (TicketStatus.RESOLVED, TicketStatus.IN_PROGRESS),
        (TicketStatus.CLOSED, TicketStatus.OPEN),
        (TicketStatus.OPEN, TicketStatus.OPEN),
    ],
)
async def test_agent_cannot_make_invalid_status_transition(
    client: AsyncClient,
    customer_a: User,
    agent: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
    current_status: TicketStatus,
    requested_status: TicketStatus,
) -> None:
    ticket = await ticket_factory(customer_a, status=current_status)
    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}/status",
        json={"status": requested_status.value},
        headers=auth_headers(agent),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


async def test_customer_cannot_edit_or_delete_ticket_after_work_starts(
    client: AsyncClient,
    customer_a: User,
    agent: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket = await ticket_factory(customer_a)
    ticket_path = f"/api/v1/tickets/{ticket.id}"

    status_response = await client.patch(
        f"{ticket_path}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers(agent),
    )
    edit_response = await client.patch(
        ticket_path,
        json={"title": "Too late to edit"},
        headers=auth_headers(customer_a),
    )
    delete_response = await client.delete(
        ticket_path,
        headers=auth_headers(customer_a),
    )

    assert status_response.status_code == 200
    assert edit_response.status_code == 409
    assert edit_response.json()["error"]["code"] == "TICKET_NOT_EDITABLE"
    assert delete_response.status_code == 409
    assert delete_response.json()["error"]["code"] == "TICKET_NOT_DELETABLE"
