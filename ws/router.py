from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status, HTTPException
from typing import Optional
import json
import logging
from sqlalchemy.orm import Session

from database.session import get_db
from models.user import User
from models.authentication import get_current_user_ws
from ws.connection_manager import manager
from ws.notifications import NotificationPayload

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Main WebSocket connection endpoint.
    Requires authentication token as a query parameter.
    """
    try:
        # Authenticate the WebSocket connection
        user = await get_current_user_ws(token, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        user_id = str(user.id)
        role = user.role.value
        
        # Accept the connection and register it
        await manager.connect(websocket, user_id, role)
        
        try:
            # Keep the connection alive and handle messages
            while True:
                # Wait for messages from the client
                data = await websocket.receive_text()
                
                try:
                    # Parse the message as JSON
                    message = json.loads(data)
                    message_type = message.get("type", "")
                    
                    # Handle different message types
                    if message_type == "ping":
                        # Simple ping/pong for connection health check
                        await manager.send_personal_message({"type": "pong"}, user_id)
                    else:
                        # Echo back any other messages for now
                        await manager.send_personal_message({
                            "type": "echo",
                            "content": message
                        }, user_id)
                        
                except json.JSONDecodeError:
                    # Handle invalid JSON
                    await manager.send_personal_message({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }, user_id)
                
        except WebSocketDisconnect:
            # Handle normal disconnection
            await manager.disconnect(websocket, user_id, role)
            
    except HTTPException:
        # Handle authentication failure
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass
