# backend/app/dummy_data.py
import random
from datetime import datetime, timedelta
from .models import AirQualityReading, Anomaly, PollutionDensity
import uuid
from typing import Optional, List

def create_dummy_air_quality(lat: float, lon: float) -> AirQualityReading:
    """Generates a single dummy air quality reading."""
    return AirQualityReading(
        latitude=lat,
        longitude=lon,
        timestamp=datetime.utcnow() - timedelta(minutes=random.randint(0, 60)),
        pm25=round(random.uniform(5.0, 80.0), 1),
        pm10=round(random.uniform(10.0, 150.0), 1),
        no2=round(random.uniform(10.0, 100.0), 1),
        so2=round(random.uniform(1.0, 20.0), 1),
        o3=round(random.uniform(20.0, 150.0), 1),
    )

def create_multiple_dummy_readings(count=20):
    """Generates a list of dummy readings at various locations."""
    readings = []
    for _ in range(count):
        lat = random.uniform(-90, 90)
        lon = random.uniform(-180, 180)
        readings.append(create_dummy_air_quality(lat, lon))
    return readings

def create_dummy_anomalies(start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, count=5) -> List[Anomaly]:
    """Generates a list of dummy anomalies."""
    anomalies = []
    if start_time is None:
        start_time = datetime.utcnow() - timedelta(days=1)
    if end_time is None:
        end_time = datetime.utcnow()

    time_range_seconds = int((end_time - start_time).total_seconds())

    for i in range(count):
        ts = start_time + timedelta(seconds=random.randint(0, time_range_seconds))
        param = random.choice(["pm25", "pm10", "no2"])
        desc = random.choice([
            "Exceeds WHO 'Hazardous' level",
            "Value increased >50% vs 24h avg",
            "Unexpected spike compared to nearby areas"
        ])
        anomalies.append(Anomaly(
            id=f"anomaly_{uuid.uuid4()}",
            latitude=random.uniform(30, 60), # Focus anomalies in northern hemisphere for demo
            longitude=random.uniform(-20, 40),
            timestamp=ts,
            parameter=param,
            value=round(random.uniform(100.0, 300.0), 1),
            description=desc
        ))
    return anomalies

def create_dummy_pollution_density(region: str) -> PollutionDensity:
    """Generates dummy density data for a region."""
    # In reality, this would query and aggregate data from the database
    return PollutionDensity(
        region_name=region,
        average_pm25=round(random.uniform(10.0, 50.0), 1),
        average_pm10=round(random.uniform(20.0, 90.0), 1),
        data_points_count=random.randint(50, 500)
    )