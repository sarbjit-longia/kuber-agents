"""
WebSocket API Endpoints

Provides real-time updates for pipeline executions.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from uuid import UUID
import structlog

from app.websocket.manager import get_connection_manager
from app.api.dependencies import get_current_user_ws

logger = structlog.get_logger()

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/executions")
async def websocket_executions(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token for authentication")
):
    """
    WebSocket endpoint for real-time execution updates.
    
    Connect to receive updates about pipeline executions.
    
    Message types sent to client:
    - execution_update: Status changes
    - execution_log: Log entries
    - execution_complete: Final results
    
    Message types received from client:
    - subscribe: {"action": "subscribe", "execution_id": "uuid"}
    - unsubscribe: {"action": "unsubscribe", "execution_id": "uuid"}
    - ping: {"action": "ping"}
    
    Args:
        websocket: WebSocket connection
        token: JWT authentication token (query param)
    """
    # Authenticate user
    try:
        user = await get_current_user_ws(token)
    except Exception as e:
        logger.error("websocket_auth_failed", error=str(e))
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    manager = get_connection_manager()
    await manager.connect(websocket, user.id)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to execution updates",
            "user_id": str(user.id)
        })
        
        # Listen for messages
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "ping":
                await websocket.send_json({"type": "pong"})
                
            elif action == "subscribe":
                execution_id = data.get("execution_id")
                if execution_id:
                    await manager.subscribe_to_execution(UUID(execution_id), user.id)
                    await websocket.send_json({
                        "type": "subscribed",
                        "execution_id": execution_id
                    })
                    
            elif action == "unsubscribe":
                execution_id = data.get("execution_id")
                if execution_id:
                    await manager.unsubscribe_from_execution(UUID(execution_id), user.id)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "execution_id": execution_id
                    })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}"
                })
                
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", user_id=str(user.id))
        manager.disconnect(websocket, user.id)
    except Exception as e:
        logger.exception("websocket_error", user_id=str(user.id))
        manager.disconnect(websocket, user.id)

