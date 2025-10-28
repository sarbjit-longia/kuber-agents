"""
Unit tests for pipeline endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_pipeline(client: AsyncClient, auth_token: str):
    """Test creating a pipeline."""
    response = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Test Pipeline",
            "description": "A test pipeline",
            "config": {
                "nodes": [{"id": "node1", "type": "trigger"}],
                "edges": []
            }
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Pipeline"
    assert data["description"] == "A test pipeline"
    assert "id" in data
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_list_pipelines(client: AsyncClient, auth_token: str):
    """Test listing pipelines."""
    # Create a pipeline first
    await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Pipeline 1",
            "description": "First pipeline",
            "config": {"nodes": [], "edges": []}
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    # List pipelines
    response = await client.get(
        "/api/v1/pipelines",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "pipelines" in data
    assert "total" in data
    assert len(data["pipelines"]) >= 1


@pytest.mark.asyncio
async def test_get_pipeline(client: AsyncClient, auth_token: str):
    """Test getting a specific pipeline."""
    # Create a pipeline
    create_response = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Get Test Pipeline",
            "description": "Pipeline to get",
            "config": {"nodes": [], "edges": []}
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    pipeline_id = create_response.json()["id"]
    
    # Get the pipeline
    response = await client.get(
        f"/api/v1/pipelines/{pipeline_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == pipeline_id
    assert data["name"] == "Get Test Pipeline"


@pytest.mark.asyncio
async def test_update_pipeline(client: AsyncClient, auth_token: str):
    """Test updating a pipeline."""
    # Create a pipeline
    create_response = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "Original Name",
            "description": "Original description",
            "config": {"nodes": [], "edges": []}
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    pipeline_id = create_response.json()["id"]
    
    # Update the pipeline
    response = await client.patch(
        f"/api/v1/pipelines/{pipeline_id}",
        json={
            "name": "Updated Name",
            "description": "Updated description"
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_delete_pipeline(client: AsyncClient, auth_token: str):
    """Test deleting a pipeline."""
    # Create a pipeline
    create_response = await client.post(
        "/api/v1/pipelines",
        json={
            "name": "To Delete",
            "description": "Will be deleted",
            "config": {"nodes": [], "edges": []}
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    pipeline_id = create_response.json()["id"]
    
    # Delete the pipeline
    response = await client.delete(
        f"/api/v1/pipelines/{pipeline_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 204
    
    # Verify it's deleted
    get_response = await client.get(
        f"/api/v1/pipelines/{pipeline_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_pipeline_unauthorized(client: AsyncClient):
    """Test that pipeline endpoints require authentication."""
    response = await client.get("/api/v1/pipelines")
    assert response.status_code == 403

