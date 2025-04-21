# backend/app/models.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone # Ensure timezone is imported

# Note: Pydantic v2 uses model_dump() instead of dict() for serialization
# and model_validate() or direct model(**data) for validation.

class IngestRequest(BaseModel):
    """Model for incoming data ingestion requests."""
    # Timestamp is NOT included here; the processing worker will add it
    latitude: float = Field(..., example=51.5074)
    longitude: float = Field(..., example=-0.1278)
    pm25: Optional[float] = Field(None, example=12.5)
    pm10: Optional[float] = Field(None, example=25.0)
    no2: Optional[float] = Field(None, example=30.1)
    so2: Optional[float] = Field(None, example=5.5)
    o3: Optional[float] = Field(None, example=45.8)

class AirQualityReading(BaseModel):
    """Model for an individual air quality reading stored/retrieved."""
    latitude: float = Field(..., example=51.5074)
    longitude: float = Field(..., example=-0.1278)
    # Use timezone-aware datetimes, default to UTC now if not provided (should come from worker)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pm25: Optional[float] = Field(None, example=12.5)
    pm10: Optional[float] = Field(None, example=25.0)
    no2: Optional[float] = Field(None, example=30.1)
    so2: Optional[float] = Field(None, example=5.5)
    o3: Optional[float] = Field(None, example=45.8)

class Anomaly(BaseModel):
    """Model representing a detected anomaly."""
    id: str = Field(..., example="anomaly_12345") # Unique ID for the anomaly event
    latitude: float = Field(..., example=40.7128)
    longitude: float = Field(..., example=-74.0060)
    timestamp: datetime = Field(..., example="2023-10-27T10:00:00Z") # When the anomaly occurred
    parameter: str = Field(..., example="pm25") # Which parameter triggered the anomaly
    value: float = Field(..., example=155.0) # The value of the parameter at the time
    description: str = Field(..., example="Exceeds WHO 'Hazardous' level") # Human-readable description

class PollutionDensity(BaseModel):
    """Model for aggregated pollution data (density) over a region/time."""
    region_name: str = Field(..., example="Central London") # Identifier or description of the region
    average_pm25: Optional[float] = Field(None, example=22.3)
    average_pm10: Optional[float] = Field(None, example=45.1)
    average_no2: Optional[float] = Field(None, example=35.0) # Added other averages
    average_so2: Optional[float] = Field(None, example=8.0)
    average_o3: Optional[float] = Field(None, example=50.5)
    data_points_count: int = Field(..., example=150) # Number of points contributing to the average