"""Authentication and token-purpose API tests."""

import pytest
from httpx import AsyncClient

from app.models.user import User

TEST_PASSWORD = "TestPassword123!"


async def _login(client: AsyncClient, user: User, password: str = TEST_PASSWORD) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    return {"response": response, **response.json()}


async def test_public_registration_creates_customer(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new-customer@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "CUSTOMER"


async def test_public_registration_rejects_agent_role(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "attempted-agent@example.com",
            "password": TEST_PASSWORD,
            "role": "AGENT",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_login_returns_access_and_refresh_tokens(
    client: AsyncClient,
    customer_a: User,
) -> None:
    result = await _login(client, customer_a)

    assert result["response"].status_code == 200
    assert result["access_token"]
    assert result["refresh_token"]
    assert result["token_type"] == "bearer"


async def test_login_rejects_incorrect_credentials(
    client: AsyncClient,
    customer_a: User,
) -> None:
    result = await _login(client, customer_a, password="WrongPassword123!")

    assert result["response"].status_code == 401
    assert result["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_accepts_valid_access_token(
    client: AsyncClient,
    customer_a: User,
) -> None:
    result = await _login(client, customer_a)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {result['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == customer_a.email


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer invalid-token"},
    ],
    ids=["missing", "invalid"],
)
async def test_me_rejects_missing_or_invalid_token(
    client: AsyncClient,
    headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_refresh_token_cannot_access_protected_route(
    client: AsyncClient,
    customer_a: User,
) -> None:
    result = await _login(client, customer_a)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {result['refresh_token']}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_access_token_cannot_be_refreshed(
    client: AsyncClient,
    customer_a: User,
) -> None:
    result = await _login(client, customer_a)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": result["access_token"]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
