"""Role and customer-ownership boundary tests."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.models.ticket import Ticket
from app.models.user import User

AuthHeadersFactory = Callable[[User], dict[str, str]]
TicketFactory = Callable[..., Awaitable[Ticket]]


async def test_customer_can_read_own_ticket_but_other_customer_gets_404(
    client: AsyncClient,
    customer_a: User,
    customer_b: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket = await ticket_factory(customer_a)

    own_response = await client.get(
        f"/api/v1/tickets/{ticket.id}", headers=auth_headers(customer_a)
    )
    other_response = await client.get(
        f"/api/v1/tickets/{ticket.id}", headers=auth_headers(customer_b)
    )

    assert own_response.status_code == 200
    assert other_response.status_code == 404
    assert other_response.json()["error"]["code"] == "TICKET_NOT_FOUND"


async def test_ticket_lists_are_customer_scoped_and_agent_sees_all(
    client: AsyncClient,
    customer_a: User,
    customer_b: User,
    agent: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket_a = await ticket_factory(customer_a, title="Customer A ticket")
    ticket_b = await ticket_factory(customer_b, title="Customer B ticket")

    customer_a_response = await client.get(
        "/api/v1/tickets", headers=auth_headers(customer_a)
    )
    customer_b_response = await client.get(
        "/api/v1/tickets", headers=auth_headers(customer_b)
    )
    agent_response = await client.get(
        "/api/v1/tickets", headers=auth_headers(agent)
    )

    assert {item["id"] for item in customer_a_response.json()["items"]} == {
        str(ticket_a.id)
    }
    assert {item["id"] for item in customer_b_response.json()["items"]} == {
        str(ticket_b.id)
    }
    assert {item["id"] for item in agent_response.json()["items"]} == {
        str(ticket_a.id),
        str(ticket_b.id),
    }


async def test_status_route_is_agent_only(
    client: AsyncClient,
    customer_a: User,
    agent: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket = await ticket_factory(customer_a)
    path = f"/api/v1/tickets/{ticket.id}/status"

    customer_response = await client.patch(
        path,
        json={"status": "IN_PROGRESS"},
        headers=auth_headers(customer_a),
    )
    agent_response = await client.patch(
        path,
        json={"status": "IN_PROGRESS"},
        headers=auth_headers(agent),
    )

    assert customer_response.status_code == 403
    assert customer_response.json()["error"]["code"] == "FORBIDDEN"
    assert agent_response.status_code == 200
    assert agent_response.json()["status"] == "IN_PROGRESS"


async def test_only_owner_can_edit_and_delete_open_ticket(
    client: AsyncClient,
    customer_a: User,
    customer_b: User,
    ticket_factory: TicketFactory,
    auth_headers: AuthHeadersFactory,
) -> None:
    ticket = await ticket_factory(customer_a)
    path = f"/api/v1/tickets/{ticket.id}"

    forbidden_edit = await client.patch(
        path,
        json={"title": "Not allowed"},
        headers=auth_headers(customer_b),
    )
    forbidden_delete = await client.delete(path, headers=auth_headers(customer_b))
    owner_edit = await client.patch(
        path,
        json={"title": "Updated by owner"},
        headers=auth_headers(customer_a),
    )
    owner_delete = await client.delete(path, headers=auth_headers(customer_a))

    assert forbidden_edit.status_code == 404
    assert forbidden_delete.status_code == 404
    assert owner_edit.status_code == 200
    assert owner_edit.json()["title"] == "Updated by owner"
    assert owner_delete.status_code == 204
