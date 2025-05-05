# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import random
import geohash
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import logging
import asyncio
import aio_pika
import json
from fastapi import FastAPI, Query, HTTPException, Body, status, WebSocket, WebSocketDisconnect, Path
from .models import IngestRequest, AirQualityReading, Anomaly, PollutionDensity, AggregatedAirQualityPoint, TimeSeriesDataPoint
from .db_client import (
    query_latest_location_data,
    query_raw_points_in_bbox,
    query_anomalies_from_db,
    query_density_in_bbox,
    query_location_history,
    close_influx_client,
    write_air_quality_data
)
from . import db_client # Keep for close_influx_client call
from . import queue_client # Import queue_client for publishing and consuming
from . import websocket_manager # Import WebSocket manager (used locally now)
from .aggregation import aggregate_by_geohash # Import aggregation function
from .config import get_settings # Import get_settings

settings = get_settings() # Get settings instance

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- RabbitMQ Consumer Task for WebSocket Broadcasts ---
rabbitmq_consumer_task = None
rabbitmq_connection = None
rabbitmq_channel = None

async def consume_broadcasts():
    """Connects to RabbitMQ, declares exclusive queue, binds to fanout, and consumes."""
    global rabbitmq_connection, rabbitmq_channel
    loop = asyncio.get_running_loop()
    settings = get_settings() # Get settings inside the async function
    RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
    BROADCAST_EXCHANGE = settings.rabbitmq_exchange_broadcast

    while True: # Keep trying to connect/reconnect
        try:
            logger.info("BROADCAST_CONSUMER: Attempting connection to RabbitMQ...")
            rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop, timeout=15)
            logger.info("BROADCAST_CONSUMER: Connection established.")

            rabbitmq_channel = await rabbitmq_connection.channel()
            logger.info("BROADCAST_CONSUMER: Channel created.")

            # Declare the fanout exchange (idempotent)
            exchange = await rabbitmq_channel.declare_exchange(
                BROADCAST_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
            )
            logger.info(f"BROADCAST_CONSUMER: Declared fanout exchange '{BROADCAST_EXCHANGE}'.")

            # Declare an exclusive, auto-delete queue for this instance
            # Empty name means RabbitMQ generates a unique one
            queue = await rabbitmq_channel.declare_queue(name='', exclusive=True, auto_delete=True)
            logger.info(f"BROADCAST_CONSUMER: Declared exclusive queue '{queue.name}'.")

            # Bind the exclusive queue to the fanout exchange
            await queue.bind(exchange)
            logger.info(f"BROADCAST_CONSUMER: Bound queue '{queue.name}' to exchange '{BROADCAST_EXCHANGE}'.")

            logger.info(f"BROADCAST_CONSUMER: Waiting for broadcast messages on queue '{queue.name}'...")

            async def on_message(message: aio_pika.IncomingMessage):
                async with message.process(ignore_processed=True): # Auto-ack on success
                    try:
                        logger.debug(f"BROADCAST_CONSUMER: Received message on '{queue.name}'.")
                        body = message.body.decode()
                        anomaly_data = json.loads(body)
                        # Validate if it looks like an anomaly (basic check)
                        if isinstance(anomaly_data, dict) and 'id' in anomaly_data and 'parameter' in anomaly_data:
                            # Re-create Anomaly object (optional, could just pass dict)
                            anomaly = Anomaly(**anomaly_data)
                            logger.info(f"BROADCAST_CONSUMER: Broadcasting anomaly {anomaly.id} received from queue.")
                            # Use the LOCAL websocket manager instance to broadcast
                            await websocket_manager.manager.broadcast_anomaly(anomaly)
                        else:
                            logger.warning(f"BROADCAST_CONSUMER: Received non-anomaly message: {body[:100]}...")
                    except json.JSONDecodeError:
                        logger.error("BROADCAST_CONSUMER: Failed to decode JSON message.", exc_info=True)
                    except Exception as e:
                        logger.error(f"BROADCAST_CONSUMER: Error processing message: {e}", exc_info=True)

            # Start consuming
            await queue.consume(on_message)

            # Keep consumer running until connection breaks or shutdown
            await asyncio.Future() # Wait indefinitely

        except (aio_pika.exceptions.AMQPConnectionError, ConnectionError, OSError) as e:
            logger.error(f"BROADCAST_CONSUMER: Connection/AMQP error: {e}. Retrying in 5 seconds...", exc_info=False)
            if rabbitmq_connection and not rabbitmq_connection.is_closed:
                try: await rabbitmq_connection.close()
                except Exception: pass
            rabbitmq_connection = None
            rabbitmq_channel = None
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("BROADCAST_CONSUMER: Task cancelled.")
            break # Exit the loop on cancellation
        except Exception as e:
            logger.error(f"BROADCAST_CONSUMER: An unexpected error occurred: {e}", exc_info=True)
            if rabbitmq_connection and not rabbitmq_connection.is_closed:
                try: await rabbitmq_connection.close()
                except Exception: pass
            rabbitmq_connection = None
            rabbitmq_channel = None
            logger.info("BROADCAST_CONSUMER: Restarting consumer loop after 10 seconds...")
            await asyncio.sleep(10)
        finally:
            logger.info("BROADCAST_CONSUMER: Cleaning up connection/channel...")
            if rabbitmq_channel and not rabbitmq_channel.is_closed:
                try: await rabbitmq_channel.close()
                except Exception: pass
            if rabbitmq_connection and not rabbitmq_connection.is_closed:
                try: await rabbitmq_connection.close()
                except Exception: pass
            rabbitmq_connection = None
            rabbitmq_channel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rabbitmq_consumer_task
    logger.info("API Startup: Initializing resources...")
    # Initialize RabbitMQ connection pool (for publishing)
    await queue_client.initialize_rabbitmq_pool()

    # Start the RabbitMQ broadcast consumer in the background
    logger.info("API Startup: Starting RabbitMQ broadcast consumer task...")
    loop = asyncio.get_running_loop()
    rabbitmq_consumer_task = loop.create_task(consume_broadcasts())

    yield # API is running

    logger.info("API Shutdown: Cleaning up resources...")
    # Stop the RabbitMQ broadcast consumer task
    if rabbitmq_consumer_task and not rabbitmq_consumer_task.done():
        logger.info("API Shutdown: Cancelling RabbitMQ broadcast consumer task...")
        rabbitmq_consumer_task.cancel()
        try:
            await rabbitmq_consumer_task # Wait for cancellation
        except asyncio.CancelledError:
            logger.info("API Shutdown: RabbitMQ broadcast consumer task cancelled successfully.")
        except Exception as e:
            logger.error(f"API Shutdown: Error during broadcast consumer task cancellation: {e}", exc_info=True)

    # Close RabbitMQ connection pool (for publishing)
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

def zoom_to_geohash_precision_backend(zoom: Optional[int]) -> int:
    """ Maps map zoom level to backend geohash aggregation precision. """
    if zoom is None: return 4 # Default if zoom not provided
    if zoom <= 3: return 2    # Very coarse for world view
    if zoom <= 5: return 3    # Coarse for continent/country
    if zoom <= 7: return 4    # Medium for region
    if zoom <= 10: return 5   # Finer for city/area
    if zoom <= 13: return 6   # Fine for neighborhood
    return 7                  # Very fine for street level (max reasonable default)


# --- NEW Endpoint for Heatmap Data ---
@app.get(
    f"{API_PREFIX}/air_quality/heatmap_data",
    response_model=List[AggregatedAirQualityPoint],
    summary="Get Aggregated Data for Heatmap",
    description="Retrieves raw air quality readings within the specified bounding box and time window, aggregates them into geohash cells based on the zoom level, and returns the average values suitable for heatmap rendering."
)
async def get_heatmap_data(
    min_lat: float = Query(..., description="Minimum latitude of the bounding box.", ge=-90, le=90),
    max_lat: float = Query(..., description="Maximum latitude of the bounding box.", ge=-90, le=90),
    min_lon: float = Query(..., description="Minimum longitude of the bounding box.", ge=-180, le=180),
    max_lon: float = Query(..., description="Maximum longitude of the bounding box.", ge=-180, le=180),
    zoom: Optional[int] = Query(None, description="Current map zoom level, used to determine aggregation precision."),
    window: str = Query("1h", description="Time window to fetch data from (e.g., '1h', '24h', '15m'). Format: InfluxDB duration literal."),
    # Consider adding a limit parameter for raw points fetched?
    # raw_point_limit: int = Query(5000, gt=0, le=20000, description="Maximum raw points to fetch before aggregation.")
):
    logger.info(f"Request for heatmap data: bbox=[{min_lat},{min_lon} to {max_lat},{max_lon}], zoom={zoom}, window={window}")

    # Basic validation
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bounding box coordinates: min values must be less than max values."
        )

    # 1. Fetch raw points within the bounding box
    # Using a default limit defined in the db_client function for now
    raw_readings = query_raw_points_in_bbox(
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon,
        window=window
        # limit=raw_point_limit # Pass limit if added as query param
    )

    if not raw_readings:
        logger.info("No raw points found in the specified bbox and window.")
        return []

    # 2. Determine geohash precision for aggregation based on zoom
    aggregation_precision = zoom_to_geohash_precision_backend(zoom)
    logger.info(f"Using aggregation precision: {aggregation_precision} for zoom {zoom}")

    # 3. Aggregate the fetched raw points using the calculated precision
    aggregated_data = aggregate_by_geohash(
        points=raw_readings,
        precision=aggregation_precision
        # No max_cells limit needed here usually, heatmap handles density visually
    )

    logger.info(f"Returning {len(aggregated_data)} aggregated points for heatmap.")
    return aggregated_data


# --- Endpoint for Aggregated Points (Map View) ---
@app.get(
    f"{API_PREFIX}/air_quality/pointsretired",
    response_model=List[AggregatedAirQualityPoint],
    summary="Get Aggregated Air Quality Points",
    description="Retrieves recent air quality readings, aggregates them into geohash grid cells, and returns the average values for each cell. Useful for map visualization."
)

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


# --- NEW Endpoint for Location History ---
@app.get(
    f"{API_PREFIX}/air_quality/history/coordinates/{{parameter}}",
    response_model=List[TimeSeriesDataPoint],
    summary="Get Time Series History for a Location and Parameter",
    description="Retrieves aggregated historical air quality data (e.g., 10-minute averages) for a specific parameter at a geographic location over a specified time window."
)
async def get_location_history(
    parameter: str = Path(..., description="The pollutant parameter to retrieve history for (e.g., 'pm25', 'no2')."),
    lat: float = Query(..., ge=-90, le=90, description="Latitude of the location."),
    lon: float = Query(..., ge=-180, le=180, description="Longitude of the location."),
    geohash_precision: int = Query(
        5, # Default precision for history lookup
        ge=2, # Minimum reasonable precision for this use case
        le=7, # Maximum standard geohash precision for history
        description="Geohash precision level to search within (1=large cell, 9=small cell). Determines the size of the grid cell for history retrieval."
    ),
    window: str = Query("24h", description="Time window to fetch history from (e.g., '1h', '24h', '7d'). Format: InfluxDB duration literal."),
    aggregate: str = Query("10m", description="Aggregation window for the time series (e.g., '1m', '10m', '1h'). Format: InfluxDB duration literal.")
):
    """
    Fetches time series data for a pollutant near the specified coordinates.
    Uses geohash internally to determine the cell area.
    """
    logger.info(f"Request for history: coordinates=({lat},{lon}), parameter={parameter}, precision={geohash_precision}, window={window}, aggregate={aggregate}")

    # Basic validation for parameters
    valid_parameters = {'pm25', 'pm10', 'no2', 'so2', 'o3', 'co'}
    if parameter not in valid_parameters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameter '{parameter}'. Valid parameters are: {', '.join(valid_parameters)}"
        )
    
    # Convert coordinates to geohash
    try:
        geohash_str = geohash.encode(lat, lon, precision=geohash_precision)
        logger.debug(f"Converted coordinates ({lat},{lon}) to geohash: {geohash_str} with precision {geohash_precision}")
    except Exception as e:
        logger.error(f"Error encoding coordinates to geohash: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error encoding coordinates to geohash: {str(e)}"
        )

    # Call existing query function with the calculated geohash
    history_data = query_location_history(
        geohash_str=geohash_str,
        parameter=parameter,
        window=window,
        aggregate_window=aggregate
    )

    if not history_data:
        logger.info(f"No history data found near coordinates ({lat},{lon}), geohash {geohash_str}, param {parameter}, window {window}.")
        # Return empty list as per response_model=List[...]
        return []

    logger.info(f"Returning {len(history_data)} history points for coordinates ({lat},{lon}), geohash {geohash_str}, param {parameter}.")
    return history_data


# Keep the original geohash endpoint for backward compatibility
@app.get(
    f"{API_PREFIX}/air_quality/history/{{geohash_str}}/{{parameter}}",
    response_model=List[TimeSeriesDataPoint],
    summary="Get Time Series History for a Geohash and Parameter",
    description="Retrieves aggregated historical air quality data for a specific parameter within a given geohash cell over a specified time window."
)
async def get_location_history_by_geohash(
    geohash_str: str = Path(..., description="The geohash string identifying the location cell.", min_length=1, max_length=12),
    parameter: str = Path(..., description="The pollutant parameter to retrieve history for (e.g., 'pm25', 'no2')."),
    window: str = Query("24h", description="Time window to fetch history from (e.g., '1h', '24h', '7d'). Format: InfluxDB duration literal."),
    aggregate: str = Query("10m", description="Aggregation window for the time series (e.g., '1m', '10m', '1h'). Format: InfluxDB duration literal.")
):
    """
    Fetches time series data for a pollutant in a geohash cell.
    """
    logger.info(f"Request for history: geohash={geohash_str}, parameter={parameter}, window={window}, aggregate={aggregate}")

    # Basic validation (more specific validation could be added)
    valid_parameters = {'pm25', 'pm10', 'no2', 'so2', 'o3', 'co'}
    if parameter not in valid_parameters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameter '{parameter}'. Valid parameters are: {', '.join(valid_parameters)}"
        )
    # Basic geohash validation (can be improved)
    if not all(c in geohash.geohash.VALID_CHARS for c in geohash_str):
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid geohash string '{geohash_str}'."
        )

    history_data = query_location_history(
        geohash_str=geohash_str,
        parameter=parameter,
        window=window,
        aggregate_window=aggregate
    )

    if not history_data:
        logger.info(f"No history data found for geohash {geohash_str}, param {parameter}, window {window}.")
        # Return empty list as per response_model=List[...]
        return []

    logger.info(f"Returning {len(history_data)} history points for geohash {geohash_str}, param {parameter}.")
    return history_data


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
    summary="Test Anomaly Broadcast via RabbitMQ",
    description="Creates a test anomaly and publishes it to the RabbitMQ broadcast exchange for testing distributed WebSocket delivery."
)
async def test_anomaly_broadcast():
    """
    Creates a test anomaly and publishes it to the RabbitMQ fanout exchange.
    All connected API instances should receive this via their consumer and broadcast locally.
    """
    logger.info("API: Creating and publishing test anomaly to broadcast exchange")

    # Create a test anomaly
    import uuid
    test_anomaly = Anomaly(
        id=f"test_anomaly_{uuid.uuid4()}",
        latitude=36.88,
        longitude=30.70,
        timestamp=datetime.now(timezone.utc),
        parameter="pm25",
        value=180.5,
        description="TEST ANOMALY - High PM2.5 level detected in Antalya (via RabbitMQ)"
    )

    # Publish the test anomaly to the broadcast exchange
    try:
        # Use the specific broadcast publish function
        success = await queue_client.publish_broadcast_message_async(test_anomaly.model_dump(mode='json'))
        if success:
            logger.info(f"API: Test anomaly {test_anomaly.id} published to broadcast exchange successfully.")
            return {"message": "Test anomaly published to broadcast exchange", "anomaly_id": test_anomaly.id}
        else:
            logger.error(f"API: FAILED to publish test anomaly {test_anomaly.id} to broadcast exchange.")
            raise HTTPException(status_code=503, detail="Failed to publish test anomaly to broadcast exchange.")
    except Exception as e:
        logger.error(f"API: Error publishing test anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error publishing test anomaly: {str(e)}")

# --- Basic Root Endpoint ---
@app.get("/", summary="Root Endpoint", description="Basic API information.")
async def read_root():
    return {"message": "Welcome to the Air Quality API. See /docs for details."}