"""
Pytest Configuration and Fixtures

This module contains shared pytest fixtures and configuration.
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
async def client():
    """
    Fixture that provides an async HTTP client for testing.
    
    Usage:
        async def test_endpoint(client):
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


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

