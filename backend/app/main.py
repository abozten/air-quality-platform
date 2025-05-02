# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import random
import geohash
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Query, HTTPException, Body, status, WebSocket, WebSocketDisconnect
from .models import IngestRequest, AirQualityReading, Anomaly, PollutionDensity, AggregatedAirQualityPoint
from .db_client import (
    query_latest_location_data,
    query_recent_points,
    query_anomalies_from_db,
    query_density_in_bbox,
    close_influx_client,
    write_air_quality_data
)
from . import db_client # Keep for close_influx_client call
from . import queue_client
from . import websocket_manager # Import WebSocket manager
from .aggregation import aggregate_by_geohash # Import aggregation function
from .config import get_settings # Import get_settings

settings = get_settings() # Get settings instance

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Startup: Initializing resources...")
    # Initialize RabbitMQ connection pool
    await queue_client.initialize_rabbitmq_pool()
    # Initialize other resources if needed (e.g., check InfluxDB connection again)
    yield
    logger.info("API Shutdown: Cleaning up resources...")
    # Close RabbitMQ connection pool
    await queue_client.close_rabbitmq_pool()
    # Close InfluxDB connection (synchronous)
    db_client.close_influx_client()
    logger.info("Resource cleanup finished.")

# Update FastAPI app instance to use lifespan manager
app = FastAPI(
    title="Air Quality API",
    description="API for collecting, analyzing, and visualizing air quality data.",
    version="0.1.0",
    lifespan=lifespan # Add lifespan manager
)


# --- CORS Configuration ---
# Adjust origins based on your frontend setup
origins = [
    "http://localhost:3000", # Example React default
    "localhost:3000",
    "http://localhost:5173", # Example Vite default
    "localhost:5173",
    "http://127.0.0.1:5173",
    # Add WebSocket origins
    "ws://localhost:3000",
    "ws://localhost:5173", # Add this line for Vite WebSocket
    "ws://127.0.0.1:5173",
    # Add production frontend origin here if applicable
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# --- API Endpoints ---
API_PREFIX = "/api/v1"

# --- Endpoint for Aggregated Points (Map View) ---
@app.get(
    f"{API_PREFIX}/air_quality/points",
    response_model=List[AggregatedAirQualityPoint],
    summary="Get Aggregated Air Quality Points (DB Aggregation)", # Updated summary
    description="Retrieves air quality readings aggregated directly within InfluxDB into geohash grid cells based on the requested precision. Returns average values and counts for each cell." # Updated description
)
async def get_aggregated_air_quality_points(
    limit: int = Query(100, gt=0, le=1000, description="Maximum number of aggregated geohash grid cells to return."), # Increased max limit example
    window: str = Query("1h", description="Time window to query data from (e.g., '1h', '24h', '15m'). Format: InfluxDB duration literal."),
    geohash_precision: int = Query(6, ge=1, le=9, description="Geohash precision for spatial aggregation. Lower value = larger grid cells.")
):
    """
    Queries the database to get pre-aggregated data points based on the
    specified geohash precision and time window.
    """
    logger.info(f"Request for DB-aggregated points: limit={limit}, window={window}, geohash_precision={geohash_precision}")

    # Directly call the new database function that performs aggregation
    try:
        aggregated_points = db_client.query_aggregated_points(
            geohash_precision=geohash_precision,
            limit=limit,
            window=window
        )
    except Exception as e:
         # Catch potential errors during the DB call itself
         logger.error(f"Error calling query_aggregated_points: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Failed to retrieve aggregated points from database.")


    if not aggregated_points:
        logger.info(f"No aggregated points found for precision {geohash_precision}, window {window}.")
        return [] # Return empty list, not an error

    # No more Python aggregation needed here!
    # The sampling logic is also removed as aggregation happens first in DB.

    logger.info(f"Returning {len(aggregated_points)} aggregated points from DB query.")
    return aggregated_points

# --- Endpoint for Anomalies ---
@app.get(
    f"{API_PREFIX}/anomalies",
    response_model=List[Anomaly],
    summary="List Detected Anomalies",
    description="Lists anomalies detected and stored in the database within a specified time range. Defaults to the last 24 hours."
)
async def list_anomalies(
    start_time: Optional[datetime] = Query(None, description="Start time for filtering anomalies (ISO 8601 format, e.g., 2023-10-27T10:00:00Z)."),
    end_time: Optional[datetime] = Query(None, description="End time for filtering anomalies (ISO 8601 format). Defaults to now if start_time is provided.")
):
    """
    Retrieves stored anomaly records. Requires a separate process (like the worker)
    to detect and write anomalies to the `air_quality_anomalies` measurement.
    If no time range is provided, defaults to the last 24 hours.
    """
    logger.info(f"Request received for anomalies: start={start_time}, end={end_time}")

    now = datetime.now(timezone.utc)
    # If only start_time is provided, default end_time to now
    if start_time is not None and end_time is None:
        end_time = now
    # If only end_time is provided, default start_time to 24h before end_time
    elif start_time is None and end_time is not None:
        start_time = end_time - timedelta(hours=24)

    # Add timezone info if naive (assume UTC for query consistency)
    if start_time and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    anomalies = query_anomalies_from_db(start_time=start_time, end_time=end_time)
    logger.info(f"Returning {len(anomalies)} anomalies.")
    return anomalies

# --- Endpoint for Pollution Density ---
@app.get(
    f"{API_PREFIX}/pollution_density",
    response_model=Optional[PollutionDensity], # Can return null if no data
    summary="Get Pollution Density for Bounding Box",
    description="Calculates the average pollution levels for a specified geographic bounding box and time window using data stored in InfluxDB. Utilizes geohash filtering for efficiency if available."
    )
async def get_pollution_density_for_bbox(
    min_lat: float = Query(..., description="Minimum latitude of the bounding box.", ge=-90, le=90),
    max_lat: float = Query(..., description="Maximum latitude of the bounding box.", ge=-90, le=90),
    min_lon: float = Query(..., description="Minimum longitude of the bounding box.", ge=-180, le=180),
    max_lon: float = Query(..., description="Maximum longitude of the bounding box.", ge=-180, le=180),
    window: str = Query("24h", description="Time window for averaging (e.g., '1h', '24h', '7d'). Format: InfluxDB duration literal.")
):
    """
    Aggregates all data points within the bounding box and time window to provide
    average pollution metrics and a count of data points used.
    """
    logger.info(f"Request for density: bbox=[{min_lat},{min_lon} to {max_lat},{max_lon}], window={window}")
    # Basic validation for bounding box coordinates
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bounding box coordinates: min values must be less than max values."
        )

    density_data = query_density_in_bbox(
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, window=window
    )

    if not density_data:
        # Return None (which becomes JSON null) as per the response model Optional[]
        logger.info(f"No density data found for bbox [{min_lat},{min_lon} - {max_lat},{max_lon}], window {window}.")
        return None

    logger.info(f"Returning density data for bbox.")
    return density_data


# --- Endpoint for Specific Location ---
@app.get(
    f"{API_PREFIX}/air_quality/location",
    response_model=Optional[AirQualityReading], # Response can be None
    summary="Get Latest Data for a Geohash Cell",
    description="Retrieves the absolute latest air quality reading stored within a specific geohash cell, determined by the input latitude, longitude, and desired precision. Useful for getting data 'near' a point without needing exact coordinates."
)
async def get_air_quality_for_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude to determine the geohash cell."),
    lon: float = Query(..., ge=-180, le=180, description="Longitude to determine the geohash cell."),
    # Default precision to storage precision, allow range (e.g., 4 to 9)
    # Precision 5 as requested max, but allow flexibility. Defaulting to storage precision (e.g., 7)
    # often makes sense to find *any* data in the finest stored grid first.
    geohash_precision: int = Query(
        settings.geohash_precision_storage, # Default to storage precision
        ge=2, # Minimum reasonable precision for this use case
        le=6, # Maximum standard geohash precision
        description=f"Geohash precision level to search within (1=large cell, 9=small cell). Determines the size of the grid cell. Defaults to storage precision ({settings.geohash_precision_storage})."
    ),
    window: str = Query("24h", description="Time window to look back for the latest data (e.g., '1h', '15m'). Format: InfluxDB duration literal.")
):
    """
    Calculates the geohash for the given lat/lon at the specified `geohash_precision`.
    Looks for the most recent data point tagged with this exact geohash within the specified `window`.
    Returns null if no data is found.
    """
    logger.info(f"Request received for specific location: lat={lat}, lon={lon}, precision={geohash_precision}, window={window}")

    # Call the updated database query function
    data = query_latest_location_data(
        lat=lat,
        lon=lon,
        precision=geohash_precision, # Pass the requested precision
        window=window
    )

    if not data:
         logger.info(f"No data found for location {lat},{lon} at precision {geohash_precision} within window {window}. Returning null.")
         return None

    logger.info(f"Returning latest data found within geohash cell for location {lat},{lon} (precision {geohash_precision}).")
    # The query function returns the Pydantic model directly or None
    return data

# --- POST Endpoint for Ingesting Data ---
@app.post(
    f"{API_PREFIX}/air_quality/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Air Quality Data",
    description="Accepts a single air quality data point and publishes it to a queue for asynchronous processing and storage."
    )
async def ingest_air_quality_data(
    ingest_data: IngestRequest = Body(...)
):
    """
    Receives sensor data, performs basic validation, and puts it onto the
    RabbitMQ queue for the worker to process. Returns 202 Accepted on success.
    """
    # Log only essential info at INFO level, more detail at DEBUG
    logger.info(f"API: Received ingest request for lat={ingest_data.latitude}, lon={ingest_data.longitude}")
    logger.debug(f"API: Full ingest request data: {ingest_data.model_dump()}")

    # Publish message asynchronously using the queue client's pooled connection
    success = await queue_client.publish_message_async(ingest_data.model_dump())

    if success:
        logger.debug(f"API: Successfully published data for {ingest_data.latitude}, {ingest_data.longitude} to queue.")
        return {"message": "Data point accepted for processing"}
    else:
        # Log the failure and return an error response
        logger.error(f"API: FAILED to publish data for {ingest_data.latitude}, {ingest_data.longitude} after retries.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue data for processing. The queue service may be temporarily unavailable or overloaded."
        )

# --- WebSocket Endpoint for Live Anomaly Notifications ---
@app.websocket(f"{API_PREFIX}/ws/anomalies")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for clients to connect and receive live anomaly notifications.
    Sends recent anomalies upon connection.
    """
    connection_id = await websocket_manager.manager.connect(websocket)
    logger.info(f"WebSocket client {connection_id} connected. Current connections: {len(websocket_manager.manager.active_connections)}")

    # Send a welcome message
    try:
        await websocket.send_json({
            "type": "connection_status",
            "message": "Connected to anomaly notification service",
            "status": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Sent welcome message to client {connection_id}")

        # --- Send recent anomalies ---
        try:
            # Query recent anomalies (e.g., last 10)
            recent_anomalies = query_anomalies_from_db() 
            logger.info(f"Fetched {len(recent_anomalies)} recent anomalies for client {connection_id}")

            if recent_anomalies:
                # Send each recent anomaly individually
                for anomaly in recent_anomalies:
                    try:
                        await websocket.send_json({
                            "type": "recent_anomaly", # Distinguish from live broadcast
                            "payload": anomaly.model_dump(mode='json')
                        })
                    except Exception as send_err:
                        logger.error(f"Failed to send recent anomaly {anomaly.id} to client {connection_id}: {send_err}")

                logger.info(f"Finished sending {len(recent_anomalies)} recent anomalies to client {connection_id}")
            else:
                logger.info(f"No recent anomalies found to send to client {connection_id}")

        except Exception as db_err:
            logger.error(f"Failed to query recent anomalies for client {connection_id}: {db_err}")

    except Exception as e:
        logger.error(f"Error during initial connection or sending recent anomalies for client {connection_id}: {e}")
        await websocket_manager.manager.disconnect(connection_id)
        return

    try:
        while True:
            # Keep the connection alive and handle incoming messages
            data = await websocket.receive_text()
            logger.debug(f"Received message from client {connection_id}: {data}")

            # Handle ping messages
            if data == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "message": "Server received ping",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                logger.debug(f"Sent pong response to client {connection_id}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {connection_id} disconnected")
        await websocket_manager.manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error with client {connection_id}: {e}")
        await websocket_manager.manager.disconnect(connection_id)

# --- Test Endpoint for WebSocket Anomaly Broadcast ---
@app.post(
    f"{API_PREFIX}/test/broadcast-anomaly",
    summary="Test Anomaly Broadcast",
    description="Creates a test anomaly and broadcasts it via WebSockets for testing purposes."
)
async def test_anomaly_broadcast():
    """
    Creates a test anomaly and broadcasts it to all connected WebSocket clients.
    This is useful for debugging the WebSocket broadcast functionality.
    """
    logger.info("Creating and broadcasting test anomaly")
    
    # Create a test anomaly
    import uuid
    test_anomaly = Anomaly(
        id=f"test_anomaly_{uuid.uuid4()}",
        latitude=36.88,
        longitude=30.70,
        timestamp=datetime.now(timezone.utc),
        parameter="pm25",
        value=180.5,
        description="TEST ANOMALY - High PM2.5 level detected in Antalya"
    )
    
    # Broadcast the test anomaly
    try:
        await websocket_manager.broadcast_anomaly(test_anomaly)
        logger.info(f"Test anomaly broadcast successful")
        return {"message": "Test anomaly broadcast successful", "anomaly_id": test_anomaly.id}
    except Exception as e:
        logger.error(f"Failed to broadcast test anomaly: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to broadcast test anomaly: {str(e)}")

# --- Basic Root Endpoint ---
@app.get("/", summary="Root Endpoint", description="Basic API information.")
async def read_root():
    return {"message": "Welcome to the Air Quality API. See /docs for details."}