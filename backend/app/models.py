# backend/app/models.py
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone # Ensure timezone is imported

# --- Request Models ---

class IngestRequest(BaseModel):
    """Data model for incoming sensor readings via the /ingest endpoint."""
    latitude: float = Field(..., example=51.5074, ge=-90, le=90)
    longitude: float = Field(..., example=-0.1278, ge=-180, le=180)
    # Make pollutant values optional, worker can handle missing data
    pm25: Optional[float] = Field(None, example=12.5, ge=0)
    pm10: Optional[float] = Field(None, example=25.0, ge=0)
    no2: Optional[float] = Field(None, example=30.1, ge=0)
    so2: Optional[float] = Field(None, example=5.5, ge=0)
    o3: Optional[float] = Field(None, example=45.8, ge=0)

    @field_validator('pm25', 'pm10', 'no2', 'so2', 'o3')
    def check_non_negative(cls, value):
        if value is not None and value < 0:
            raise ValueError('Pollutant values cannot be negative')
        return value

# --- Data Storage/Internal Models ---

class AirQualityReading(BaseModel):
    """Represents a single, processed air quality reading stored in the database."""
    latitude: float = Field(..., example=51.5074, ge=-90, le=90)
    longitude: float = Field(..., example=-0.1278, ge=-180, le=180)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Default to current UTC time
    pm25: Optional[float] = Field(None, example=12.5, ge=0)
    pm10: Optional[float] = Field(None, example=25.0, ge=0)
    no2: Optional[float] = Field(None, example=30.1, ge=0)
    so2: Optional[float] = Field(None, example=5.5, ge=0)
    o3: Optional[float] = Field(None, example=45.8, ge=0)

    # Ensure timestamp is timezone-aware (UTC) upon validation/creation
    @field_validator('timestamp')
    def ensure_timezone_aware(cls, v):
        if v.tzinfo is None:
            # If naive, assume it's UTC (or handle based on specific needs)
            return v.replace(tzinfo=timezone.utc)
        # If aware, convert to UTC for consistency
        return v.astimezone(timezone.utc)

class Anomaly(BaseModel):
    """Represents a detected anomaly event stored in the database."""
    id: str = Field(..., example="anomaly_a1b2c3d4", description="Unique identifier for the anomaly event.")
    latitude: float = Field(..., example=40.7128, ge=-90, le=90)
    longitude: float = Field(..., example=-74.0060, ge=-180, le=180)
    timestamp: datetime = Field(..., example="2023-10-27T10:00:00Z", description="Timestamp when the anomaly occurred (UTC).")
    parameter: str = Field(..., example="pm25", description="The pollutant parameter that triggered the anomaly.")
    value: float = Field(..., example=255.3, description="The measured value of the parameter that caused the anomaly.")
    description: str = Field(..., example="PM2.5 value 255.3 exceeds hazardous threshold (250.0)", description="Description of the anomaly.")

    @field_validator('timestamp')
    def ensure_anomaly_timezone_aware(cls, v):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


# --- Response Models for Specific Endpoints ---

class PollutionDensity(BaseModel):
    """Response model for the /pollution_density endpoint."""
    region_name: str = Field(..., example="BBox:[51.4,-0.2 to 51.6,-0.1]", description="Identifier for the queried region (e.g., bounding box coordinates).")
    average_pm25: Optional[float] = Field(None, example=22.3, description="Average PM2.5 value in the region for the time window.")
    average_pm10: Optional[float] = Field(None, example=45.1, description="Average PM10 value.")
    average_no2: Optional[float] = Field(None, example=33.5, description="Average NO2 value.")
    average_so2: Optional[float] = Field(None, example=4.9, description="Average SO2 value.")
    average_o3: Optional[float] = Field(None, example=58.2, description="Average O3 value.")
    data_points_count: int = Field(..., example=150, description="Number of data points used to calculate the averages (represents overall data density).")

# +++ NEW Model for Time Series Data Points +++
class TimeSeriesDataPoint(BaseModel):
    timestamp: datetime = Field(..., description="Timestamp for the data point (UTC)")
    value: float = Field(..., description="Aggregated value at this timestamp")

class AggregatedAirQualityPoint(BaseModel):
    """Response model for a single aggregated point in the /air_quality/points endpoint."""
    geohash: str = Field(..., example="u10hfg", description="Geohash string representing the grid cell.")
    latitude: float = Field(..., example=51.501, description="Representative latitude for the geohash cell center (or average point).")
    longitude: float = Field(..., example=-0.123, description="Representative longitude.")
    avg_pm25: Optional[float] = Field(None, example=15.2, description="Average PM2.5 value within this cell.")
    avg_pm10: Optional[float] = Field(None, example=28.9, description="Average PM10 value.")
    avg_no2: Optional[float] = Field(None, example=35.1, description="Average NO2 value.")
    avg_so2: Optional[float] = Field(None, example=4.8, description="Average SO2 value.")
    avg_o3: Optional[float] = Field(None, example=55.3, description="Average O3 value.")
    count: int = Field(..., example=10, description="Number of raw data points aggregated into this cell.")