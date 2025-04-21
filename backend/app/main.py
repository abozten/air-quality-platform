# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Query, HTTPException, Body, status
from .models import IngestRequest, AirQualityReading
from .db_client import (
    query_latest_location_data,
    close_influx_client,
    write_air_quality_data
)
from . import db_client
from . import queue_client
from .models import AirQualityReading, Anomaly, PollutionDensity, AggregatedAirQualityPoint
from .aggregation import aggregate_by_geohash



# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Startup: Initializing resources...")
    # Initialize RabbitMQ connection pool
    await queue_client.initialize_rabbitmq_pool()
    # Initialize other resources if needed (e.g., async InfluxDB client)
    yield
    logger.info("API Shutdown: Cleaning up resources...")
    # Close RabbitMQ connection pool
    await queue_client.close_rabbitmq_pool()
    # Close InfluxDB connection (synchronous for now)
    db_client.close_influx_client()
    logger.info("Resource cleanup finished.")

# Update FastAPI app instance to use lifespan manager
app = FastAPI(
    title="Air Quality API",
    description="API for collecting, analyzing, and visualizing air quality data.",
    version="0.1.0",
    lifespan=lifespan # Add lifespan manager
)



from .models import AirQualityReading, Anomaly, PollutionDensity




# --- CORS Configuration ---
origins = [
    "http://localhost:3000",
    "localhost:3000",
    "http://localhost:5173", # Vite default port
    "localhost:5173",
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

# Import the new query functions
from .db_client import (
    query_latest_location_data,
    query_recent_points,
    query_anomalies_from_db,
    query_density_in_bbox,
    close_influx_client
)

# --- Endpoint for Multiple Points ---
@app.get(f"{API_PREFIX}/air_quality/points", response_model=List[AggregatedAirQualityPoint])
async def get_multiple_air_quality_points(
    limit: int = Query(50, gt=0, le=200, description="Max number of geohash grid cells to return"),
    window: str = Query("1h", description="Time window to look for latest data (e.g., '1h', '24h', '5m')"),
    geohash_precision: int = Query(6, ge=1, le=12, description="Geohash precision for spatial aggregation")
):
    """
    Get a list of recent air quality readings aggregated by geohash grid cells.
    """
    logger.info(f"Request received for recent points: limit={limit}, window={window}, geohash_precision={geohash_precision}")
    readings = query_recent_points(limit=limit * 2, window=window)  # Fetch more to allow for aggregation
    if not readings:
        return []
    aggregated = aggregate_by_geohash(readings, precision=geohash_precision, max_cells=limit)
    return aggregated

# --- Endpoint for Anomalies ---
@app.get(f"{API_PREFIX}/anomalies", response_model=List[Anomaly])
async def list_anomalies(
    start_time: Optional[datetime] = Query(None, description="Start time (ISO 8601 format)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO 8601 format)")
):
    """
    List detected anomalies stored in InfluxDB within a given time range.
    Defaults to the last 24 hours if no range is provided.
    NOTE: Requires a separate process to detect and write anomalies.
    """
    logger.info(f"Request received for anomalies: start={start_time}, end={end_time}")
    anomalies = query_anomalies_from_db(start_time=start_time, end_time=end_time)
    if anomalies is None: # query_anomalies_from_db now returns list or empty list
        return []
    return anomalies

# --- Endpoint for Pollution Density ---
@app.get(f"{API_PREFIX}/pollution_density", response_model=Optional[PollutionDensity])
async def get_pollution_density_for_bbox(
    min_lat: float = Query(..., description="Minimum latitude of the bounding box"),
    max_lat: float = Query(..., description="Maximum latitude of the bounding box"),
    min_lon: float = Query(..., description="Minimum longitude of the bounding box"),
    max_lon: float = Query(..., description="Maximum longitude of the bounding box"),
    window: str = Query("24h", description="Time window for averaging (e.g., '1h', '24h')")
):
    """
    Get the aggregated pollution density (average values) for a specified geographic bounding box from InfluxDB.
    """
    logger.info(f"Request received for density: bbox=[{min_lat},{min_lon} to {max_lat},{max_lon}], window={window}")
    # Basic validation for bounding box
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(status_code=400, detail="Invalid bounding box coordinates.")

    density_data = query_density_in_bbox(
        min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, window=window
    )

    if not density_data:
        # Return 404 if no data found in the area/timeframe
        # raise HTTPException(status_code=404, detail="No data found for the specified region and time window.")
        # Or return null as per Optional[PollutionDensity]
        return None

    return density_data


    
@app.get(f"{API_PREFIX}/air_quality/location", response_model=Optional[AirQualityReading]) # Response can be None now
async def get_air_quality_for_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude of the location"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude of the location")
):
    """
    Get the latest air quality data for a specific location from InfluxDB.
    Searches within the last hour by default.
    """
    logger.info(f"Request received for lat={lat}, lon={lon}")
    # Call the database query function
    data = query_latest_location_data(lat=lat, lon=lon, window="1h")

    if not data:
        # Option 1: Return 404 Not Found
        # raise HTTPException(status_code=404, detail="No recent data found for this location")
        # Option 2: Return null/None (as allowed by Optional[AirQualityReading])
         logger.warning(f"No data found for {lat},{lon}. Returning null.")
         return None


    # Convert the dictionary result back to Pydantic model if needed
    # Ensure the keys match the model fields exactly
    try:
        # Map InfluxDB fields back to Pydantic model fields carefully
        reading = AirQualityReading(
            latitude=data.get('latitude', lat), # Ensure correct type
            longitude=data.get('longitude', lon),
            timestamp=data.get('timestamp'), # Ensure correct type
            pm25=data.get('pm25'),
            pm10=data.get('pm10'),
            no2=data.get('no2'),
            so2=data.get('so2'),
            o3=data.get('o3')
        )
        return reading
    except Exception as e:
         logger.error(f"Error converting query result to Pydantic model: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Internal server error processing data")

#POST endpoint for ingesting air quality data
@app.post(f"{API_PREFIX}/air_quality/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_air_quality_data(
    ingest_data: IngestRequest = Body(...)
):
    """
    Receives data, validates, and publishes ASYNCHRONOUSLY to the queue via connection pool.
    """
    logger.info(f"API: Async Pool Received ingest request: {ingest_data.model_dump()}")

    # Call the publish function which now uses the pool
    success = await queue_client.publish_message_async(ingest_data.model_dump())

    if success:
        # Log less verbosely on success perhaps
        # logger.info(f"API: Async Pool published data for {ingest_data.latitude}, {ingest_data.longitude}")
        return {"message": "Data point accepted for processing"}
    else:
        logger.error(f"API: Async Pool FAILED to publish data for {ingest_data.latitude}, {ingest_data.longitude}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue data for processing after retries. Service may be temporarily unavailable."
        )
