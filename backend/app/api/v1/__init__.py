"""
API Version 1 Package

All v1 API endpoints are defined here.
"""
from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.pipelines import router as pipelines_router
from app.api.v1.agents import router as agents_router
from app.api.v1.executions import router as executions_router
from app.api.v1.websocket import router as websocket_router

router = APIRouter()

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(pipelines_router)
router.include_router(agents_router)
router.include_router(executions_router)
router.include_router(websocket_router)
