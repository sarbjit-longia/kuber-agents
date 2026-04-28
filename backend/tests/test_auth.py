"""
Unit tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.config import settings
from app.services.user_service import get_user_by_email


VALID_INVITATION_CODE = settings.BETA_INVITATION_CODE


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient, db_session: AsyncSession):
    """Test user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert "id" in data
    assert data["is_active"] is True
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db_session: AsyncSession):
    """Test that registering with duplicate email fails."""
    # Register first user
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "testpass123",
            "full_name": "First User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )

    # Try to register with same email
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "different123",
            "full_name": "Second User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_with_invalid_invitation_code(client: AsyncClient, db_session: AsyncSession):
    """Test that registering with the wrong invitation code is rejected."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongcode@example.com",
            "password": "testpass123",
            "full_name": "Wrong Code",
            "invitation_code": "NOT-A-REAL-CODE",
        }
    )
    assert response.status_code == 400
    assert "invalid invitation code" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_without_invitation_code(client: AsyncClient, db_session: AsyncSession):
    """Test that omitting the invitation code triggers Pydantic validation."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "missingcode@example.com",
            "password": "testpass123",
            "full_name": "Missing Code",
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invitation_code_does_not_short_circuit_email_check(
    client: AsyncClient, db_session: AsyncSession
):
    """An invalid code is rejected even if the email is already taken (code checked first)."""
    # Seed a user
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "seeded@example.com",
            "password": "testpass123",
            "full_name": "Seeded",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "seeded@example.com",
            "password": "testpass123",
            "full_name": "Seeded Dup",
            "invitation_code": "NOT-A-REAL-CODE",
        }
    )
    assert response.status_code == 400
    assert "invalid invitation code" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session: AsyncSession):
    """Test successful login."""
    # Register a user first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "testpass123",
            "full_name": "Login User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "testpass123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession):
    """Test login with wrong password."""
    # Register a user first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "correctpass",
            "full_name": "Test User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )

    # Try to login with wrong password
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "wrongpass"
        }
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with non-existent user."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "somepass"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, db_session: AsyncSession):
    """Test getting current user profile."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile@example.com",
            "password": "testpass123",
            "full_name": "Profile User",
            "invitation_code": VALID_INVITATION_CODE,
        }
    )

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "profile@example.com",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]

    # Get profile
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "profile@example.com"
    assert data["full_name"] == "Profile User"


@pytest.mark.asyncio
async def test_get_current_user_unauthorized(client: AsyncClient):
    """Test accessing protected route without token."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(client: AsyncClient):
    """Test accessing protected route with invalid token."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code == 401
