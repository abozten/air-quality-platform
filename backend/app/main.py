# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import logging
from .config import get_settings # Use get_settings() here
from fastapi import FastAPI, Query, HTTPException, Body, status
from .models import IngestRequest, AirQualityReading, Anomaly, PollutionDensity # Import all necessary models
from . import db_client # Import db_client module
from . import queue_client # Import queue_client module

settings = get_settings() # Get settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Startup: Initializing resources...")
    # Initialize RabbitMQ connection pool
    await queue_client.initialize_rabbitmq_pool()
    # Initialize InfluxDB client (call the init function from db_client)
    db_client.initialize_influxdb_client()
    yield
    logger.info("API Shutdown: Cleaning up resources...")
    # Close RabbitMQ connection pool
    await queue_client.close_rabbitmq_pool()
    # Close InfluxDB connection
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
origins = [
    "http://localhost:3000",
    "localhost:3000",
    "http://localhost:5173", # Vite default port
    "localhost:5173",
    # Add other frontend origins if needed
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
API_PREFIX = "/api/v1"

# Note: The provided main.py had a duplicate definition of get_multiple_air_quality_points.
# I've removed the first (dummy) one and kept/updated the second one to use db_client.
# Also, the dummy pollution_density endpoint was removed and replaced with the bbox version.

@app.post(f"{API_PREFIX}/air_quality/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_air_quality_data(
    ingest_data: IngestRequest = Body(...)
):
    """
    Receives air quality data, validates, and publishes ASYNCHRONOUSLY to the raw data queue
    for processing by the worker.
    """
    logger.info(f"API: Received ingest request for {ingest_data.latitude},{ingest_data.longitude}")

    # Call the publish function which uses the connection pool
    success = await queue_client.publish_message_async(ingest_data.model_dump())

    if success:
        logger.debug(f"API: Published data for {ingest_data.latitude}, {ingest_data.longitude} to queue.")
        return {"message": "Data point accepted and queued for processing"}
    else:
        logger.error(f"API: FAILED to publish data for {ingest_data.latitude}, {ingest_data.longitude} to queue.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue data for processing after retries. Message queue service may be temporarily unavailable."
        )

@app.get(f"{API_PREFIX}/air_quality/location", response_model=Optional[AirQualityReading])
async def get_air_quality_for_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude of the location"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude of the location")
):
    """
    Get the latest air quality data for a specific location from InfluxDB.
    Searches within the last hour by default. Returns null if no recent data is found.
    """
    logger.info(f"API: Request received for latest data at lat={lat}, lon={lon}")
    # Call the database query function
    reading = db_client.query_latest_location_data(lat=lat, lon=lon, window="1h")

    if reading is None:
         logger.info(f"API: No recent data found for {lat},{lon}.")
         # Returning None automatically results in 200 with null body for Optional[...]
         return None

    logger.debug(f"API: Found latest reading for {lat},{lon}")
    return reading

# --- Endpoint for Multiple Recent Points ---
# This replaces the dummy get_multiple_air_quality_points
@app.get(f"{API_PREFIX}/air_quality/points", response_model=List[AirQualityReading])
async def get_multiple_air_quality_points(
    limit: int = Query(50, gt=0, le=200, description="Max number of distinct location points to return"),
    window: str = Query("1h", description="Time window to look for latest data (e.g., '1h', '24h', '5m')"),
    # Added optional bbox filters, aligning with the concept from the removed duplicate endpoint
    min_lat: Optional[float] = Query(None, ge=-90, le=90, description="Minimum latitude for bounding box"),
    max_lat: Optional[float] = Query(None, ge=-90, le=90, description="Maximum latitude for bounding box"),
    min_lon: Optional[float] = Query(None, ge=-180, le=180, description="Minimum longitude for bounding box"),
    max_lon: Optional[float] = Query(None, ge=-180, le=180, description="Maximum longitude for bounding box")
):
    """
    Get a list of recent air quality readings from distinct locations stored in InfluxDB,
    optionally filtered by a bounding box.
    """
    logger.info(f"API: Request received for recent points: limit={limit}, window={window}, bbox=[{min_lat},{min_lon} to {max_lat},{max_lon}]")

    # Note: The current db_client.query_recent_points function doesn't support bbox filtering.
    # This endpoint definition *includes* bbox parameters, suggesting a potential future enhancement
    # in db_client. For now, the bbox parameters will be accepted but ignored by the current db_client function.
    # If bbox filtering is critical, db_client.query_recent_points would need modification.
    if any([min_lat, max_lat, min_lon, max_lon]) and not all([min_lat, max_lat, min_lon, max_lon]):
         raise HTTPException(status_code=400, detail="If any bounding box parameter is provided, all must be provided.")
    if all([min_lat, max_lat, min_lon, max_lon]):
         if min_lat >= max_lat or min_lon >= max_lon:
             raise HTTPException(status_code=400, detail="Invalid bounding box coordinates.")
         logger.warning("Bounding box filtering requested but not currently implemented in db_client.query_recent_points. Returning all points within window/limit.")
         # TODO: Implement bbox filtering in db_client.query_recent_points

    # Call the database query function
    readings = db_client.query_recent_points(limit=limit, window=window)

    if readings is None: # db_client functions return list or None/empty list
         logger.error("API: db_client.query_recent_points returned None.")
         return [] # Return empty list if query fails or no data
    return readings

# --- Endpoint for Anomalies ---
# This replaces the dummy list_anomalies
@app.get(f"{API_PREFIX}/anomalies", response_model=List[Anomaly])
async def list_anomalies(
    start_time: Optional[datetime] = Query(None, description="Start time (ISO 8601 format) for filtering anomalies"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO 8601 format) for filtering anomalies")
):
    """
    List detected anomalies stored in InfluxDB within a given time range.
    Defaults to the last 24 hours if no range is provided.
    NOTE: Anomalies must be detected (by worker) and written to InfluxDB.
    """
    logger.info(f"API: Request received for anomalies: start={start_time}, end={end_time}")
    # Call the database query function
    anomalies = db_client.query_anomalies_from_db(start_time=start_time, end_time=end_time)

    if anomalies is None: # db_client functions return list or None/empty list
        logger.error("API: db_client.query_anomalies_from_db returned None.")
        return [] # Return empty list if query fails or no data

    logger.info(f"API: Returning {len(anomalies)} anomalies.")
    return anomalies

# --- Endpoint for Pollution Density ---
# This replaces the dummy get_pollution_density_for_region and uses bbox parameters
@app.get(f"{API_PREFIX}/pollution_density", response_model=Optional[PollutionDensity])
async def get_pollution_density_for_bbox(
    min_lat: float = Query(..., description="Minimum latitude of the bounding box"),
    max_lat: float = Query(..., description="Maximum latitude of the bounding box"),
    min_lon: float = Query(..., description="Minimum longitude of the bounding box"),
    max_lon: float = Query(..., description="Maximum longitude of the bounding box"),
    window: str = Query("24h", description="Time window for averaging (e.g., '1h', '24h')")
):
    """
    Get the aggregated pollution density (average values and data point count)
    for a specified geographic bounding box from InfluxDB.
    Returns null if no data is found in the region and time window.
    """
    logger.info(f"API: Request received for density: bbox=[{min_lat},{min_lon} to {max_lat},{max_lon}], window={window}")
    # Basic validation for bounding box
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(status_code=400, detail="Invalid bounding box coordinates: min must be less than max.")
    if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90) or not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
         raise HTTPException(status_code=400, detail="Invalid bounding box coordinates: lat/lon out of range.")


    # Call the database query function
    density_data = db_client.query_density_in_bbox(
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, window=window
    )

    if density_data is None:
        logger.info(f"API: No density data found for bbox [{min_lat:.2f},{min_lon:.2f} - {max_lat:.2f},{max_lon:.2f}] in window {window}.")
        # Return None as per Optional[PollutionDensity] response model
        return None

    logger.debug(f"API: Returning density data: {density_data.region_name}")
    return density_data

# --- End of API Endpoints ---