from uuid import uuid4

import pytest
from httpx import AsyncClient

API = "/api/v1/auth"


def new_user() -> dict:
    return {
        "email": f"test-{uuid4().hex}@example.com",
        "full_name": "Test User",
        "password": "StrongPassword123!",
    }


async def register_user(
    client: AsyncClient,
    user: dict,
) -> None:
    response = await client.post(
        f"{API}/register",
        json=user,
    )
    assert response.status_code == 201, response.text


async def login_user(
    client: AsyncClient,
    user: dict,
) -> dict:
    response = await client.post(
        f"{API}/login",
        json={
            "email": user["email"],
            "password": user["password"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(
    client: AsyncClient,
):
    user = new_user()

    await register_user(client, user)

    response = await client.post(
        f"{API}/register",
        json=user,
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_access_token_cannot_refresh(
    client: AsyncClient,
):
    user = new_user()

    await register_user(client, user)

    tokens = await login_user(client, user)

    response = await client.post(
        f"{API}/refresh",
        json={
            "refresh_token": tokens["access_token"],
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(
    client: AsyncClient,
):
    user = new_user()

    await register_user(client, user)

    tokens = await login_user(client, user)

    old_refresh_token = tokens["refresh_token"]

    # Dùng token lần đầu → thành công.
    first_response = await client.post(
        f"{API}/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert first_response.status_code == 200

    # Dùng lại token cũ → bị từ chối.
    second_response = await client.post(
        f"{API}/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert second_response.status_code == 401

    # Token mới vẫn có thể refresh.
    new_refresh_token = first_response.json()["refresh_token"]

    third_response = await client.post(
        f"{API}/refresh",
        json={"refresh_token": new_refresh_token},
    )

    assert third_response.status_code == 200
