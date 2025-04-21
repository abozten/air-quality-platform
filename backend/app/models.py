# backend/app/models.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone # Ensure timezone is imported

class IngestRequest(BaseModel):
    # Timestamp is optional in request, will default to now if not provided
    # Alternatively, you could make it mandatory from the script
    latitude: float = Field(..., example=51.5074)
    longitude: float = Field(..., example=-0.1278)
    pm25: Optional[float] = Field(None, example=12.5)
    pm10: Optional[float] = Field(None, example=25.0)
    no2: Optional[float] = Field(None, example=30.1)
    so2: Optional[float] = Field(None, example=5.5)
    o3: Optional[float] = Field(None, example=45.8)

class AirQualityReading(BaseModel):
    latitude: float = Field(..., example=51.5074)
    longitude: float = Field(..., example=-0.1278)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    pm25: Optional[float] = Field(None, example=12.5)
    pm10: Optional[float] = Field(None, example=25.0)
    no2: Optional[float] = Field(None, example=30.1)
    so2: Optional[float] = Field(None, example=5.5)
    o3: Optional[float] = Field(None, example=45.8)

class Anomaly(BaseModel):
    id: str = Field(..., example="anomaly_12345")
    latitude: float = Field(..., example=40.7128)
    longitude: float = Field(..., example=-74.0060)
    timestamp: datetime = Field(..., example="2023-10-27T10:00:00Z")
    parameter: str = Field(..., example="pm25")
    value: float = Field(..., example=155.0)
    description: str = Field(..., example="Exceeds WHO 'Hazardous' level")

class PollutionDensity(BaseModel):
    region_name: str = Field(..., example="Central London")
    average_pm25: Optional[float] = Field(None, example=22.3)
    average_pm10: Optional[float] = Field(None, example=45.1)
    # Add other averages as needed
    data_points_count: int = Field(..., example=150)


class AggregatedAirQualityPoint(BaseModel):
    geohash: str = Field(..., example="u10hfg")
    latitude: float = Field(..., example=51.501)
    longitude: float = Field(..., example=-0.123)
    avg_pm25: Optional[float] = Field(None, example=15.2)
    avg_pm10: Optional[float] = Field(None, example=28.9)
    avg_no2: Optional[float] = Field(None, example=35.1)
    avg_so2: Optional[float] = Field(None, example=4.8)
    avg_o3: Optional[float] = Field(None, example=55.3)
    count: int = Field(..., example=10, description="Number of raw points aggregated in this cell")

# For request query parameters if needed later
# class TimeRangeQuery(BaseModel):
#     start_time: Optional[datetime] = None
#     end_time: Optional[datetime] = None