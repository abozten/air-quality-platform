# backend/app/main.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import logging

# Import database connection functions
from .database import connect_to_db, close_db_connection, get_db_pool, DATABASE_URL

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application startup...")
    await connect_to_db() # Establish DB pool
    yield # Application runs here
    # Shutdown logic
    logger.info("Application shutdown...")
    await close_db_connection() # Close DB pool



# Import models and dummy data functions
from .models import AirQualityReading, Anomaly, PollutionDensity
from .dummy_data import (
    create_dummy_air_quality,
    create_multiple_dummy_readings,
    create_dummy_anomalies,
    create_dummy_pollution_density
)

app = FastAPI(
    title="Air Quality API",
    description="API for collecting, analyzing, and visualizing air quality data.",
    version="0.1.0"
)

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

@app.get("/")
async def read_root():
    # Check DB connection status (optional)
    pool = await get_db_pool()
    db_status = "Connected" if pool else "Disconnected"
    return {"message": "Welcome to the Air Quality API!", "database_status": db_status}

@app.get(f"{API_PREFIX}/air_quality/location", response_model=AirQualityReading)
async def get_air_quality_for_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude of the location"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude of the location")
):
    """
    Get the latest (dummy) air quality data for a specific location.
    """
    # In a real scenario, you would query your database for the latest data near lat/lon
    print(f"Request received for lat={lat}, lon={lon}") # For debugging
    reading = create_dummy_air_quality(lat, lon)
    return reading

@app.get(f"{API_PREFIX}/air_quality/points", response_model=List[AirQualityReading])
async def get_multiple_air_quality_points(
    limit: int = Query(20, gt=0, le=100, description="Number of data points to return")
):
    """
    Get a list of recent (dummy) air quality readings from various locations.
    Used to populate the map initially.
    """
    readings = create_multiple_dummy_readings(count=limit)
    return readings


@app.get(f"{API_PREFIX}/anomalies", response_model=List[Anomaly])
async def list_anomalies(
    start_time: Optional[datetime] = Query(None, description="Start time for filtering anomalies (ISO 8601 format)"),
    end_time: Optional[datetime] = Query(None, description="End time for filtering anomalies (ISO 8601 format)")
):
    """
    List detected (dummy) anomalies within a given time range.
    Defaults to the last 24 hours if no range is provided.
    """
    anomalies = create_dummy_anomalies(start_time, end_time)
    return anomalies

@app.get(f"{API_PREFIX}/pollution_density", response_model=PollutionDensity)
async def get_pollution_density_for_region(
    region: str = Query(..., description="Identifier for the geographic region (e.g., city name, bounding box)")
):
    """
    Get the aggregated (dummy) pollution density for a specified region.
    """
    # In a real implementation, 'region' might be parsed to define coordinates
    # or match a predefined area name in the database.
    if not region:
         raise HTTPException(status_code=400, detail="Region parameter is required")
    density_data = create_dummy_pollution_density(region)
    return density_data

