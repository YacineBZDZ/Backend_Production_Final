from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.
    Tracks active connections and handles user-specific notifications.
    """
    def __init__(self):
        # Maps user_id to a list of active connections (multi-device support)
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Role-based connection groups
        self.doctor_connections: Set[str] = set()
        self.patient_connections: Set[str] = set()
        self.admin_connections: Set[str] = set()

    async def connect(self, websocket: WebSocket, user_id: str, role: str):
        """Accepts a websocket connection and registers it with user details"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        # Add to role-based group
        if role == "doctor":
            self.doctor_connections.add(user_id)
        elif role == "patient":
            self.patient_connections.add(user_id)
        elif role == "admin":
            self.admin_connections.add(user_id)
        
        logger.info(f"New connection for user {user_id} with role {role}")
        
        # Send connection confirmation
        await self.send_personal_message(
            {
                "type": "connection_status", 
                "status": "connected",
                "message": f"Connected as {role}"
            }, 
            user_id
        )

    async def disconnect(self, websocket: WebSocket, user_id: str, role: str):
        """Removes a disconnected websocket"""
        # Remove this specific websocket
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            
            # If no more connections for this user, clean up
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                
                # Remove from role-based groups
                if role == "doctor" and user_id in self.doctor_connections:
                    self.doctor_connections.remove(user_id)
                elif role == "patient" and user_id in self.patient_connections:
                    self.patient_connections.remove(user_id)
                elif role == "admin" and user_id in self.admin_connections:
                    self.admin_connections.remove(user_id)
        
        logger.info(f"Disconnected user {user_id} with role {role}")

    async def send_personal_message(self, message: dict, user_id: str):
        """Sends a message to a specific user across all their devices"""
        if user_id in self.active_connections:
            message_json = json.dumps(message)
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message_json)
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {str(e)}")

    async def broadcast_to_doctors(self, message: dict):
        """Broadcasts a message to all connected doctors"""
        for doctor_id in self.doctor_connections:
            await self.send_personal_message(message, doctor_id)

    async def broadcast_to_patients(self, message: dict):
        """Broadcasts a message to all connected patients"""
        for patient_id in self.patient_connections:
            await self.send_personal_message(message, patient_id)
            
    async def broadcast_to_admins(self, message: dict):
        """Broadcasts a message to all connected admins"""
        for admin_id in self.admin_connections:
            await self.send_personal_message(message, admin_id)
            
    async def broadcast_to_all(self, message: dict):
        """Broadcasts a message to all connected users"""
        all_users = set(self.active_connections.keys())
        for user_id in all_users:
            await self.send_personal_message(message, user_id)
    
    async def send_appointment_notification(self, 
                                           appointment_data: dict, 
                                           notification_type: str,
                                           affected_user_ids: List[str]):
        """
        Sends appointment-related notifications to affected users
        
        Parameters:
        - appointment_data: Dictionary with appointment details
        - notification_type: Type of notification (new, update, status_change, auto_status_change)
        - affected_user_ids: List of user IDs who should receive this notification
        """
        try:
            notification = {
                "type": "appointment_notification",
                "notification_type": notification_type,
                "appointment": appointment_data
            }
            
            for user_id in affected_user_ids:
                try:
                    if user_id in self.active_connections:
                        await self.send_personal_message(notification, user_id)
                except Exception as e:
                    # Log but continue with other users
                    logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
                
            # Also try to send to admins for monitoring
            try:
                await self.broadcast_to_admins(notification)
            except Exception as e:
                logger.error(f"Failed to send admin notification: {str(e)}")
        except Exception as e:
            # Log the error but don't raise it - this ensures appointment operations complete
            logger.error(f"Error in send_appointment_notification: {str(e)}")

# Create a singleton instance
manager = ConnectionManager()

# Export the manager instance
__all__ = ["manager"]
