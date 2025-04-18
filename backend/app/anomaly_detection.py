# backend/app/anomaly_detection.py
import logging
from .models import AirQualityReading, Anomaly
from .config import get_settings
from datetime import datetime, timezone
import uuid # For generating anomaly IDs
from typing import Optional, List

logger = logging.getLogger(__name__)
settings = get_settings()

def check_thresholds(reading: AirQualityReading) -> Optional[Anomaly]:
    """Checks a reading against predefined hazardous thresholds."""
    anomalies_found = []

    # Check PM2.5
    if reading.pm25 is not None and reading.pm25 > settings.threshold_pm25_hazardous:
        anomalies_found.append({
            "parameter": "pm25",
            "value": reading.pm25,
            "description": f"PM2.5 value {reading.pm25:.1f} exceeds hazardous threshold ({settings.threshold_pm25_hazardous:.1f})"
        })

    # Check PM10
    if reading.pm10 is not None and reading.pm10 > settings.threshold_pm10_hazardous:
         anomalies_found.append({
            "parameter": "pm10",
            "value": reading.pm10,
            "description": f"PM10 value {reading.pm10:.1f} exceeds hazardous threshold ({settings.threshold_pm10_hazardous:.1f})"
        })

    # Check NO2
    if reading.no2 is not None and reading.no2 > settings.threshold_no2_hazardous:
         anomalies_found.append({
            "parameter": "no2",
            "value": reading.no2,
            "description": f"NO2 value {reading.no2:.1f} exceeds hazardous threshold ({settings.threshold_no2_hazardous:.1f})"
        })

    # Add checks for SO2, O3 etc. similarly

    if not anomalies_found:
        return None

    # For simplicity, return the first detected anomaly. Could be enhanced to return multiple.
    first_anomaly = anomalies_found[0]
    anomaly_obj = Anomaly(
        id=f"anomaly_{uuid.uuid4()}",
        latitude=reading.latitude,
        longitude=reading.longitude,
        timestamp=reading.timestamp, # Use the reading's timestamp
        parameter=first_anomaly["parameter"],
        value=first_anomaly["value"],
        description=first_anomaly["description"]
    )
    logger.warning(f"Anomaly Detected: {anomaly_obj.description} at ({reading.latitude},{reading.longitude})")
    return anomaly_obj

# --- Placeholder for future detection methods ---
# def check_percentage_increase(reading: AirQualityReading) -> Optional[Anomaly]:
#    # 1. Query DB for average of 'parameter' at lat/lon over last 24h (excluding current reading)
#    # 2. Compare current reading.value to average
#    # 3. If > 50% increase, create and return Anomaly object
#    pass

# def check_spatial_difference(reading: AirQualityReading) -> Optional[Anomaly]:
#    # 1. Query DB for recent readings (e.g., last 1h) within 25km radius
#    # 2. Calculate average/median of 'parameter' for nearby points
#    # 3. Compare current reading.value to nearby average
#    # 4. If significantly different (e.g., > 2 * std dev), create and return Anomaly object
#    pass