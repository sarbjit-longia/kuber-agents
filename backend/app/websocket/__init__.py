"""
WebSocket Package

Provides real-time updates for pipeline executions via WebSocket connections.
"""

from app.websocket.manager import ConnectionManager, get_connection_manager

__all__ = ["ConnectionManager", "get_connection_manager"]

