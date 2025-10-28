"""
Health Endpoint Tests

Tests for the health check endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test the /health endpoint returns 200 and correct structure."""
    response = await client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert "timestamp" in data
    assert "environment" in data
    assert "version" in data
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_endpoint(client: AsyncClient):
    """Test the /readiness endpoint returns 200 and correct structure."""
    response = await client.get("/api/v1/readiness")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert "celery" in data


@pytest.mark.asyncio
async def test_ping_endpoint(client: AsyncClient):
    """Test the /ping endpoint returns pong."""
    response = await client.get("/api/v1/ping")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["message"] == "pong"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test the root endpoint returns API information."""
    response = await client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "message" in data
    assert "version" in data
    assert "status" in data
    assert data["status"] == "running"

