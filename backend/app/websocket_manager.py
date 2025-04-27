# backend/app/websocket_manager.py
import logging
import asyncio  # Import asyncio
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect
from .models import Anomaly

# Configure logging
logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    WebSocket connection manager for handling multiple clients
    and broadcasting anomaly notifications.
    """
    
    def __init__(self):
        # Active client connections
        self.active_connections: Dict[int, WebSocket] = {}
        # Counter for connection IDs
        self.connection_counter = 0
    
    async def connect(self, websocket: WebSocket) -> int:
        """
        Accept a new WebSocket connection and return its unique ID.
        """
        await websocket.accept()
        connection_id = self.connection_counter
        self.active_connections[connection_id] = websocket
        self.connection_counter += 1
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")
        return connection_id
    
    def disconnect(self, connection_id: int) -> None:
        """
        Remove a disconnected WebSocket from active connections.
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            logger.info(f"WebSocket client disconnected. Remaining connections: {len(self.active_connections)}")
    
    async def broadcast_anomaly(self, anomaly: Anomaly) -> None:
        """
        Broadcast an anomaly to all connected clients concurrently.
        """
        if not self.active_connections:
            logger.debug("No active WebSocket connections to broadcast anomaly to.")
            return
        
        # Create a serializable version of the anomaly
        anomaly_data = anomaly.model_dump()
        
        # Create tasks for sending to each client
        tasks = []
        connection_ids = list(self.active_connections.keys()) # Get IDs first
        for connection_id in connection_ids:
            websocket = self.active_connections.get(connection_id)
            if websocket: # Check if connection still exists
                 tasks.append(websocket.send_json(anomaly_data))
            else:
                 # Handle cases where connection might have been removed between getting keys and creating task
                 logger.warning(f"Connection {connection_id} disappeared before sending.")
                 tasks.append(asyncio.create_task(asyncio.sleep(0))) # Add a placeholder completed task

        # Send concurrently and gather results (including exceptions)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Keep track of disconnected clients to clean up
        disconnected_clients = []
        
        # Process results to find failed sends
        for i, result in enumerate(results):
            connection_id = connection_ids[i] # Match result to connection ID
            if isinstance(result, Exception):
                logger.error(f"Error sending to connection {connection_id}: {result}")
                # Only mark for disconnect if the connection still exists in the dictionary
                # It might have been disconnected by another concurrent operation or the connect/disconnect methods
                if connection_id in self.active_connections:
                    disconnected_clients.append(connection_id)
            else:
                 logger.debug(f"Sent anomaly to connection {connection_id}")

        # Clean up any disconnected clients
        for connection_id in disconnected_clients:
            # Check again before disconnecting, as it might have been handled elsewhere
            if connection_id in self.active_connections:
                self.disconnect(connection_id)
        
        logger.info(f"Broadcasted anomaly {anomaly.id} attempt finished. Active connections: {len(self.active_connections)}")

# Create a global instance of the connection manager
manager = ConnectionManager()

async def broadcast_anomaly(anomaly: Anomaly) -> None:
    """
    Public function to broadcast anomaly to all connected clients.
    """
    await manager.broadcast_anomaly(anomaly)