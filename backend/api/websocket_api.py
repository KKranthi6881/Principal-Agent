"""
WebSocket API for real-time notifications and progress updates
"""

import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import uuid

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create router
router = APIRouter(prefix="/ws", tags=["websocket"])

# Active WebSocket connections
active_connections: Dict[str, Dict[str, Any]] = {}

# Connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_subscriptions: Dict[str, List[str]] = {}  # User ID -> List of topics

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.user_subscriptions[client_id] = []
        logger.info(f"WebSocket connection established: {client_id}")
        
        # Send initial connection confirmation
        await self.send_message(client_id, {
            "type": "connection_established",
            "client_id": client_id,
            "message": "WebSocket connection established"
        })

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.user_subscriptions:
            del self.user_subscriptions[client_id]
        logger.info(f"WebSocket connection closed: {client_id}")

    async def send_message(self, client_id: str, message: Dict[str, Any]):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to client {client_id}: {str(e)}")
                return False
        return False

    async def broadcast(self, message: Dict[str, Any], topic: Optional[str] = None):
        """
        Broadcast a message to all connected clients or to clients subscribed to a specific topic
        """
        disconnected_clients = []
        
        for client_id, websocket in self.active_connections.items():
            # If topic is specified, only send to clients subscribed to that topic
            if topic and client_id in self.user_subscriptions and topic not in self.user_subscriptions[client_id]:
                continue
                
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    def subscribe(self, client_id: str, topic: str):
        """
        Subscribe a client to a topic
        """
        if client_id not in self.user_subscriptions:
            self.user_subscriptions[client_id] = []
        
        if topic not in self.user_subscriptions[client_id]:
            self.user_subscriptions[client_id].append(topic)
            logger.info(f"Client {client_id} subscribed to topic: {topic}")
            return True
        return False

    def unsubscribe(self, client_id: str, topic: str):
        """
        Unsubscribe a client from a topic
        """
        if client_id in self.user_subscriptions and topic in self.user_subscriptions[client_id]:
            self.user_subscriptions[client_id].remove(topic)
            logger.info(f"Client {client_id} unsubscribed from topic: {topic}")
            return True
        return False

# Create connection manager instance
manager = ConnectionManager()

# WebSocket endpoint for general notifications
@router.websocket("/notifications")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive and process messages from the client
            data = await websocket.receive_json()
            logger.debug(f"Received message from client {client_id}: {data}")
            
            # Handle client messages
            if "action" in data:
                if data["action"] == "subscribe" and "topic" in data:
                    manager.subscribe(client_id, data["topic"])
                    await manager.send_message(client_id, {
                        "type": "subscription_update",
                        "status": "subscribed",
                        "topic": data["topic"]
                    })
                
                elif data["action"] == "unsubscribe" and "topic" in data:
                    manager.unsubscribe(client_id, data["topic"])
                    await manager.send_message(client_id, {
                        "type": "subscription_update",
                        "status": "unsubscribed",
                        "topic": data["topic"]
                    })
                    
                elif data["action"] == "ping":
                    await manager.send_message(client_id, {
                        "type": "pong",
                        "timestamp": data.get("timestamp")
                    })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {str(e)}")
        manager.disconnect(client_id)

# WebSocket endpoint for task progress updates
@router.websocket("/tasks/{task_id}")
async def task_progress_endpoint(websocket: WebSocket, task_id: str):
    client_id = str(uuid.uuid4())
    await manager.connect(websocket, client_id)
    
    # Automatically subscribe to the task topic
    topic = f"task:{task_id}"
    manager.subscribe(client_id, topic)
    
    # Send initial task status if available
    from api.lineage_tasks import get_lineage_task
    task_status = get_lineage_task(task_id)
    if task_status:
        await manager.send_message(client_id, {
            "type": "task_status",
            "task_id": task_id,
            "data": task_status
        })
    
    try:
        while True:
            # Keep the connection alive and handle client messages
            data = await websocket.receive_json()
            
            if "action" in data and data["action"] == "ping":
                await manager.send_message(client_id, {
                    "type": "pong",
                    "timestamp": data.get("timestamp")
                })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {str(e)}")
        manager.disconnect(client_id)

# Functions to send notifications from other parts of the application
async def send_task_update(task_id: str, status: Dict[str, Any]):
    """
    Send a task update to all clients subscribed to the task topic
    """
    await manager.broadcast(
        message={
            "type": "task_status",
            "task_id": task_id,
            "data": status
        },
        topic=f"task:{task_id}"
    )

async def send_notification(message: str, notification_type: str = "info", data: Any = None):
    """
    Send a general notification to all connected clients
    """
    await manager.broadcast({
        "type": "notification",
        "notification_type": notification_type,
        "message": message,
        "data": data
    })
