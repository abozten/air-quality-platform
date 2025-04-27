# backend/app/websocket_manager.py
import logging
import asyncio
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect
from .models import Anomaly
import json  # Import json for potential serialization errors

# Configure logging
logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    WebSocket connection manager for handling multiple clients
    and broadcasting anomaly notifications.
    """

    def __init__(self):
        # Active client connections: connection_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # Counter for connection IDs
        self.connection_counter = 0
        # Lock for modifying active_connections to prevent race conditions
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> int:
        """
        Accept a new WebSocket connection and return its unique ID.
        """
        await websocket.accept()
        async with self._lock:
            connection_id = self.connection_counter
            self.active_connections[connection_id] = websocket
            self.connection_counter += 1
            logger.info(f"WebSocket client {connection_id} connected. Total connections: {len(self.active_connections)}")
        return connection_id

    async def disconnect(self, connection_id: int, websocket: WebSocket = None) -> None:
        """
        Remove a disconnected WebSocket from active connections.
        Optionally pass the websocket object for logging purposes if available.
        """
        async with self._lock:
            if connection_id in self.active_connections:
                client_info = f"client {connection_id}"
                # Example: Add client address if needed and available
                # ws_to_log = websocket or self.active_connections.get(connection_id)
                # if ws_to_log and ws_to_log.client:
                #     client_info += f" ({ws_to_log.client.host}:{ws_to_log.client.port})"

                del self.active_connections[connection_id]
                logger.info(f"WebSocket {client_info} disconnected. Remaining connections: {len(self.active_connections)}")
            # else: # Avoid logging noise if disconnect is called multiple times for the same ID
                 # logger.warning(f"Attempted to disconnect non-existent connection ID: {connection_id}")


    async def broadcast_anomaly(self, anomaly: Anomaly) -> None:
        """
        Broadcast an anomaly to all connected clients concurrently.
        Handles disconnections gracefully during broadcast.
        """
        # Check if there are any connections without locking first for performance
        if not self.active_connections:
            # logger.debug("No active WebSocket connections to broadcast anomaly to.") # Can be noisy
            return

        try:
            # Create a serializable version of the anomaly
            # Use mode='json' for pydantic v2 if Anomaly is a Pydantic model
            anomaly_data = anomaly.model_dump(mode='json')
            message = json.dumps(anomaly_data)  # Serialize to JSON string once
        except Exception as e:
            logger.error(f"Failed to serialize anomaly {anomaly.id}: {e}")
            return  # Cannot broadcast if serialization fails

        # Get a snapshot of connections under lock to prevent race conditions
        async with self._lock:
            # Create a list of tuples to avoid issues if dict changes during iteration
            connections_to_send = list(self.active_connections.items())

        if not connections_to_send:
             # logger.debug("No active connections found after acquiring lock.") # Can be noisy
             return

        logger.info(f"Attempting to broadcast anomaly {anomaly.id} to {len(connections_to_send)} clients.")

        tasks = []
        connection_ids_in_batch = []  # Keep track of IDs for this specific broadcast attempt

        for connection_id, websocket in connections_to_send:
             # Ensure the websocket object is valid before creating a task
             if websocket:
                 tasks.append(self._send_message(websocket, message, connection_id))
                 connection_ids_in_batch.append(connection_id)
             else:
                 # This case should ideally not happen if connect/disconnect are managed correctly
                 logger.warning(f"Found invalid websocket object for connection ID {connection_id} during broadcast preparation.")


        # Send concurrently and gather results (True for success, False for failure)
        results = await asyncio.gather(*tasks, return_exceptions=False)  # Handle errors in _send_message

        disconnected_during_send = []
        for i, success in enumerate(results):
            # Ensure index is valid before accessing connection_ids_in_batch
            if i < len(connection_ids_in_batch):
                connection_id = connection_ids_in_batch[i]
                if not success:
                    # The _send_message helper already logged the error
                    disconnected_during_send.append(connection_id)
            else:
                # This indicates a mismatch, log an error
                logger.error("Mismatch between gather results and connection IDs during broadcast.")


        # Clean up clients that failed during this broadcast attempt
        if disconnected_during_send:
            logger.warning(f"Found {len(disconnected_during_send)} clients potentially disconnected during broadcast of anomaly {anomaly.id}.")
            # Use the disconnect method which handles locking and logging
            # Run disconnect tasks concurrently for cleanup
            disconnect_tasks = [self.disconnect(conn_id) for conn_id in disconnected_during_send]
            await asyncio.gather(*disconnect_tasks)


        # Log final state after potential cleanup (optional, can be noisy)
        # async with self._lock:
        #     final_connection_count = len(self.active_connections)
        # logger.info(f"Finished broadcasting anomaly {anomaly.id}. Active connections now: {final_connection_count}")


    async def _send_message(self, websocket: WebSocket, message: str, connection_id: int) -> bool:
        """Helper to send a message to a single websocket and handle errors."""
        try:
            await websocket.send_text(message)  # Send raw JSON string
            # logger.debug(f"Successfully sent anomaly to connection {connection_id}") # Can be noisy
            return True
        except WebSocketDisconnect:
             logger.warning(f"Client {connection_id} disconnected during send.")
             # No need to call self.disconnect here, the main broadcast loop will handle it
             return False
        except Exception as e:
            # Catch other potential errors (network issues, etc.)
            logger.error(f"Error sending message to connection {connection_id}: {e}")
            # Assume connection is broken
            return False


# Create a global instance of the connection manager
manager = ConnectionManager()

async def broadcast_anomaly(anomaly: Anomaly) -> None:
    """
    Public function to broadcast anomaly to all connected clients using the global manager.
    """
    await manager.broadcast_anomaly(anomaly)