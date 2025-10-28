"""
Pytest Configuration and Fixtures

This module contains shared pytest fixtures and configuration.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import Base, get_db
from app.config import settings


# Create test database engine
TEST_DATABASE_URL = settings.DATABASE_URL
if TEST_DATABASE_URL:
    # Replace the database name with a test database
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("/trading_platform", "/trading_platform_test")

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    Fixture that provides a clean database session for each test.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """
    Fixture that provides an async HTTP client for testing.
    
    Usage:
        async def test_endpoint(client):
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
    """
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    """
    Fixture that provides an authentication token for testing protected endpoints.
    
    Usage:
        async def test_protected_endpoint(client, auth_token):
            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
    """
    # Register a test user
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "password": "testpass123",
            "full_name": "Test User"
        }
    )
    
    # Login and get token
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "testpass123"
        }
    )
    
    return response.json()["access_token"]


@pytest.fixture
def mock_settings(monkeypatch):
    """
    Fixture to override settings for testing.
    
    Usage:
        def test_with_mock_settings(mock_settings):
            mock_settings(DEBUG=False, ENV="testing")
            # test code here
    """
    def _mock_settings(**kwargs):
        from app.config import settings
        for key, value in kwargs.items():
            monkeypatch.setattr(settings, key, value)
    
    return _mock_settings

