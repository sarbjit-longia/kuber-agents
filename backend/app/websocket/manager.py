"""
WebSocket Connection Manager

Manages WebSocket connections for real-time pipeline execution updates.
"""
import structlog
from typing import Dict, List, Set
from uuid import UUID
from fastapi import WebSocket
import json

logger = structlog.get_logger()


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Features:
    - User-specific connections
    - Pipeline-specific subscriptions
    - Broadcast to multiple clients
    - Connection lifecycle management
    """
    
    def __init__(self):
        # user_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
        # execution_id -> Set[user_id] (who's watching this execution)
        self.execution_watchers: Dict[str, Set[str]] = {}
        
        logger.info("connection_manager_initialized")
    
    async def connect(self, websocket: WebSocket, user_id: UUID):
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            user_id: User ID
        """
        await websocket.accept()
        
        user_id_str = str(user_id)
        if user_id_str not in self.active_connections:
            self.active_connections[user_id_str] = []
        
        self.active_connections[user_id_str].append(websocket)
        
        logger.info("websocket_connected", user_id=user_id_str, total_connections=len(self.active_connections[user_id_str]))
    
    def disconnect(self, websocket: WebSocket, user_id: UUID):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            user_id: User ID
        """
        user_id_str = str(user_id)
        
        if user_id_str in self.active_connections:
            self.active_connections[user_id_str].remove(websocket)
            
            if not self.active_connections[user_id_str]:
                del self.active_connections[user_id_str]
        
        # Remove from execution watchers
        for execution_id, watchers in list(self.execution_watchers.items()):
            if user_id_str in watchers:
                watchers.remove(user_id_str)
                if not watchers:
                    del self.execution_watchers[execution_id]
        
        logger.info("websocket_disconnected", user_id=user_id_str)
    
    async def send_personal_message(self, message: dict, user_id: UUID):
        """
        Send message to a specific user.
        
        Args:
            message: Message data
            user_id: User ID
        """
        user_id_str = str(user_id)
        
        if user_id_str not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[user_id_str]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("failed_to_send_message", user_id=user_id_str, error=str(e))
                disconnected.append(connection)
        
        # Clean up disconnected connections
        for connection in disconnected:
            self.disconnect(connection, user_id)
    
    async def broadcast_to_user(self, message: dict, user_id: UUID):
        """
        Broadcast message to all connections of a user.
        
        Args:
            message: Message data
            user_id: User ID
        """
        await self.send_personal_message(message, user_id)
    
    async def subscribe_to_execution(self, execution_id: UUID, user_id: UUID):
        """
        Subscribe a user to execution updates.
        
        Args:
            execution_id: Execution ID
            user_id: User ID
        """
        execution_id_str = str(execution_id)
        user_id_str = str(user_id)
        
        if execution_id_str not in self.execution_watchers:
            self.execution_watchers[execution_id_str] = set()
        
        self.execution_watchers[execution_id_str].add(user_id_str)
        
        logger.info("subscribed_to_execution", execution_id=execution_id_str, user_id=user_id_str)
    
    async def unsubscribe_from_execution(self, execution_id: UUID, user_id: UUID):
        """
        Unsubscribe a user from execution updates.
        
        Args:
            execution_id: Execution ID
            user_id: User ID
        """
        execution_id_str = str(execution_id)
        user_id_str = str(user_id)
        
        if execution_id_str in self.execution_watchers:
            self.execution_watchers[execution_id_str].discard(user_id_str)
            
            if not self.execution_watchers[execution_id_str]:
                del self.execution_watchers[execution_id_str]
        
        logger.info("unsubscribed_from_execution", execution_id=execution_id_str, user_id=user_id_str)
    
    async def broadcast_execution_update(self, execution_id: UUID, update: dict):
        """
        Broadcast execution update to all watching users.
        
        Args:
            execution_id: Execution ID
            update: Update data
        """
        execution_id_str = str(execution_id)
        
        if execution_id_str not in self.execution_watchers:
            return
        
        message = {
            "type": "execution_update",
            "execution_id": execution_id_str,
            "data": update
        }
        
        for user_id_str in self.execution_watchers[execution_id_str]:
            await self.send_personal_message(message, UUID(user_id_str))
    
    async def send_execution_log(self, execution_id: UUID, log_entry: dict):
        """
        Send execution log entry to watchers.
        
        Args:
            execution_id: Execution ID
            log_entry: Log entry data
        """
        execution_id_str = str(execution_id)
        
        if execution_id_str not in self.execution_watchers:
            return
        
        message = {
            "type": "execution_log",
            "execution_id": execution_id_str,
            "data": log_entry
        }
        
        for user_id_str in self.execution_watchers[execution_id_str]:
            await self.send_personal_message(message, UUID(user_id_str))
    
    async def send_execution_complete(self, execution_id: UUID, result: dict):
        """
        Notify watchers that execution is complete.
        
        Args:
            execution_id: Execution ID
            result: Final execution result
        """
        execution_id_str = str(execution_id)
        
        if execution_id_str not in self.execution_watchers:
            return
        
        message = {
            "type": "execution_complete",
            "execution_id": execution_id_str,
            "data": result
        }
        
        for user_id_str in self.execution_watchers[execution_id_str]:
            await self.send_personal_message(message, UUID(user_id_str))


# Singleton instance
_connection_manager: ConnectionManager = None


def get_connection_manager() -> ConnectionManager:
    """
    Get the global ConnectionManager instance.
    
    Returns:
        ConnectionManager instance
    """
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager

