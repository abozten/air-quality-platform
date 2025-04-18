# backend/app/db_client.py
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from .config import get_settings
from .models import AirQualityReading # Import your Pydantic model
from typing import List, Optional
import logging
from datetime import datetime,timedelta, timezone
from .models import Anomaly 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()

# Ensure URL from environment is used when running in Docker
influx_url = settings.influxdb_url
influx_token = settings.influxdb_token
influx_org = settings.influxdb_org
influx_bucket = settings.influxdb_bucket

logger.info(f"Attempting to connect to InfluxDB at {influx_url} in org '{influx_org}'")

try:
    client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=20_000)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    query_api = client.query_api()
    logger.info("InfluxDB client initialized.")

    # Check connection / readiness (Updated Check)
    try:
        ready = client.ready()
        if hasattr(ready, 'status') and ready.status == "ready": # Check status attribute
            # Safely try to get version if available
            version_info = f" Version: {ready.version}" if hasattr(ready, 'version') else ""
            logger.info(f"InfluxDB connection successful! Status: {ready.status}{version_info}")
        elif hasattr(ready, 'status'):
             logger.warning(f"InfluxDB ready check returned status: {ready.status}")
        else:
             logger.warning(f"InfluxDB ready check response object structure unexpected: {ready}")

    except Exception as e:
         logger.error(f"Error checking InfluxDB readiness: {e}", exc_info=True)


except Exception as e:
    logger.error(f"Failed to initialize InfluxDB client: {e}", exc_info=True)
    # Set APIs to None or raise an exception to prevent app startup if DB is critical
    client = None
    write_api = None
    query_api = None

from .models import Anomaly, PollutionDensity # Import necessary models

# --- Query Function for Multiple Points ---
def query_recent_points(limit: int = 50, window: str = "1h") -> List[AirQualityReading]:
    """
    Queries the latest distinct air quality readings from different locations
    within a specified time window.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return []

    # Flux query to get the last point for each lat/lon combination within the window
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> group(columns: ["latitude", "longitude"]) // Group by location
          |> last() // Get the latest point in each group
          |> group(columns: ["_measurement"]) // Ungroup before pivot
          |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value")
          |> limit(n: {limit}) // Limit the number of locations returned
    '''
    logger.debug(f"Executing Flux query for recent points:\n{flux_query}")

    results: List[AirQualityReading] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org)
        if not tables:
            return []

        for table in tables:
            for record in table.records:
                try:
                    data = record.values
                    # Convert lat/lon tags back to float, handle potential errors
                    lat = float(data.get("latitude", 0.0))
                    lon = float(data.get("longitude", 0.0))

                    reading = AirQualityReading(
                        latitude=lat,
                        longitude=lon,
                        timestamp=record.get_time(), # Pivot keeps time
                        pm25=data.get('pm25'),
                        pm10=data.get('pm10'),
                        no2=data.get('no2'),
                        so2=data.get('so2'),
                        o3=data.get('o3')
                    )
                    results.append(reading)
                except Exception as e:
                    logger.error(f"Error processing record for recent points: {e} - Record: {record.values}", exc_info=True)
                    continue # Skip faulty record

        logger.info(f"Found {len(results)} recent points.")
        return results

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying recent points: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Generic error querying recent points: {e}", exc_info=True)
        return []


# --- Query Function for Anomalies ---
def query_anomalies_from_db(start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Anomaly]:
    """
    Queries detected anomalies stored in the 'air_quality_anomalies' measurement.
    NOTE: Requires anomalies to be detected and written separately.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return []

    # Default time range (e.g., last 24 hours) if not provided
    if start_time is None and end_time is None:
        range_filter = f'|> range(start: -24h)'
    elif start_time and end_time:
         # Ensure timezone-aware before formatting
         start_iso = start_time.astimezone(timezone.utc).isoformat() if start_time else ''
         end_iso = end_time.astimezone(timezone.utc).isoformat() if end_time else ''
         range_filter = f'|> range(start: {start_iso}, stop: {end_iso})'
    elif start_time:
         start_iso = start_time.astimezone(timezone.utc).isoformat() if start_time else ''
         range_filter = f'|> range(start: {start_iso})'
    else: # Only end_time provided
        end_iso = end_time.astimezone(timezone.utc).isoformat() if end_time else ''
        # Need a start, perhaps default to beginning of time or a reasonable past limit
        range_filter = f'|> range(start: 0, stop: {end_iso})' # Or range(start: -30d, stop: ...)


    # Flux query to get anomaly records
    # Assumes measurement 'air_quality_anomalies' with tags/fields matching Anomaly model
    # Tags: latitude, longitude, parameter
    # Fields: value, description, id (or use time as ID)
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          {range_filter}
          |> filter(fn: (r) => r["_measurement"] == "air_quality_anomalies")
          |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value")
          // Add sorting if needed: |> sort(columns: ["_time"], desc: true)
    '''
    logger.debug(f"Executing Flux query for anomalies:\n{flux_query}")

    results: List[Anomaly] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org)
        if not tables:
            # This is expected if no anomalies are stored yet
            logger.info("No anomalies found in the specified range.")
            return []

        for table in tables:
            for record in table.records:
                 try:
                    data = record.values
                    lat = float(data.get("latitude", 0.0)) # Get tags if stored
                    lon = float(data.get("longitude", 0.0))

                    anomaly = Anomaly(
                        id=str(data.get("id", record.get_time().isoformat())), # Use 'id' field or timestamp as fallback ID
                        latitude=lat,
                        longitude=lon,
                        timestamp=record.get_time(),
                        parameter=str(data.get("parameter", "unknown")), # Tag or field
                        value=float(data.get("value", 0.0)), # Field
                        description=str(data.get("description", "")) # Field
                    )
                    results.append(anomaly)
                 except Exception as e:
                    logger.error(f"Error processing anomaly record: {e} - Record: {record.values}", exc_info=True)
                    continue # Skip faulty record

        logger.info(f"Found {len(results)} anomalies.")
        return results

    except InfluxDBError as e:
        # Don't treat "no data found" as a critical error for anomalies yet
        if "no series found" in str(e).lower() or "no data found" in str(e).lower():
             logger.info("No anomaly data found for the specified query.")
             return []
        logger.error(f"InfluxDB Error querying anomalies: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Generic error querying anomalies: {e}", exc_info=True)
        return []

def write_anomaly_data(anomaly: Anomaly):
    """Writes a detected Anomaly to InfluxDB."""
    if not write_api:
        logger.error("InfluxDB write_api not available for writing anomaly.")
        return False

    # Ensure timestamp is timezone-aware
    if anomaly.timestamp.tzinfo is None:
        timestamp_to_write = anomaly.timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp_to_write = anomaly.timestamp

    point = (
        Point("air_quality_anomalies") # Different measurement name
        .tag("latitude", str(anomaly.latitude))
        .tag("longitude", str(anomaly.longitude))
        .tag("parameter", anomaly.parameter) # Tag the parameter causing anomaly
        .field("value", anomaly.value) # Store the anomalous value
        .field("description", anomaly.description) # Store the description
        .field("id", anomaly.id) # Store the unique ID
        .time(timestamp_to_write, WritePrecision.MS)
    )

    try:
        write_api.write(bucket=influx_bucket, org=influx_org, record=point)
        logger.info(f"Successfully wrote anomaly: {anomaly.id} - {anomaly.description}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing anomaly data: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Generic error writing anomaly data: {e}", exc_info=True)
        return False

# --- Query Function for Pollution Density ---
def query_density_in_bbox(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float, window: str = "24h"
) -> Optional[PollutionDensity]:
    """
    Calculates average pollution density within a bounding box and time window.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return None

    # Construct filters for latitude and longitude using string tags
    # Note: This requires lat/lon to be stored as string tags.
    # For numerical range filtering, InfluxDB Cloud or specific setups are needed.
    # Alternative: Query broader range and filter in Python (less efficient).
    # Let's assume string tags for now for broader compatibility.
    # A better approach would be geohashing if performance becomes an issue.

    # Query to calculate mean values and count within the bbox and window
    flux_query = f'''
      all_data = from(bucket: "{influx_bucket}")
        |> range(start: -{window})
        |> filter(fn: (r) => r["_measurement"] == "air_quality")
        // Attempt numerical filtering (might only work on InfluxDB Cloud or specific versions)
        |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
        |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
        // Consider adding filter(fn: (r) => r._value != nil) if needed

      // Calculate means
      means = all_data
        |> keep(columns: ["_field", "_value"]) // Keep only fields needed for mean
        |> group(columns: ["_field"])
        |> mean()
        |> group() // Ungroup
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")

      // Calculate count
      count_val = all_data
        |> count() // Count records per field
        |> first() // Take one count value (assuming all fields have same count)
        |> findColumn(fn: (key) => true, column: "_value") // Extract the count value

      // Combine results (using join or map - map might be simpler here if structure is known)
      // Fetching separately and combining in Python might be easier than complex Flux join/union
      means // Return the table with means
    '''

    # --- Alternative approach: Fetch separately and combine in Python ---
    flux_query_mean = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          // Assuming tags are strings - this is less efficient but more compatible
          |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
          |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
          |> filter(fn: (r) => r["_field"] == "pm25" or r["_field"] == "pm10" or r["_field"] == "no2" or r["_field"] == "so2" or r["_field"] == "o3")
          |> mean() // Calculate mean per field
          |> group(columns: ["_field"]) // Group by field to get one row per field mean
          |> first() // Get the single mean value row for each field
          |> group() // Ungroup
          |> pivot(rowKey:["_measurement"], columnKey: ["_field"], valueColumn: "_value") // Pivot to get fields as columns
    '''
    flux_query_count = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          // Same location filter
          |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
          |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
          |> filter(fn: (r) => r["_field"] == "pm25") // Count based on one representative field
          |> count()
          |> keep(columns: ["_value"]) // Keep only the count value
    '''

    logger.debug(f"Executing Flux query for density means:\n{flux_query_mean}")
    logger.debug(f"Executing Flux query for density count:\n{flux_query_count}")

    try:
        # Execute mean query
        mean_tables = query_api.query(query=flux_query_mean, org=influx_org)
        mean_data = {}
        if mean_tables and mean_tables[0].records:
            mean_data = mean_tables[0].records[0].values
            logger.debug(f"Mean query result: {mean_data}")
        else:
             logger.info(f"No data found in bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] for mean calculation.")
             # Return None or default density object? Returning None for now.
             return None

        # Execute count query
        count_tables = query_api.query(query=flux_query_count, org=influx_org)
        data_points_count = 0
        if count_tables and count_tables[0].records:
            data_points_count = count_tables[0].records[0].get_value()
            logger.debug(f"Count query result: {data_points_count}")
        else:
            # Should generally not happen if mean query returned data, but handle defensively
            logger.warning(f"Count query returned no results, although mean query did.")


        # Construct the result object
        density = PollutionDensity(
            region_name=f"BBox:[{min_lat:.2f},{min_lon:.2f} to {max_lat:.2f},{max_lon:.2f}]", # Describe the region
            average_pm25=mean_data.get('pm25'), # Will be None if field wasn't present
            average_pm10=mean_data.get('pm10'),
            # Add other averages as needed from mean_data
            data_points_count=data_points_count
        )
        logger.info(f"Calculated density: {density}")
        return density

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying density: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Generic error querying density: {e}", exc_info=True)
        return None


def write_air_quality_data(reading: AirQualityReading):
    """Writes a single AirQualityReading to InfluxDB."""
    if not write_api:
        logger.error("InfluxDB write_api not available.")
        return False # Indicate failure

    # Ensure the timestamp from the reading is timezone-aware (it should be from main.py)
    if reading.timestamp.tzinfo is None:
        logger.warning(f"Timestamp for {reading.latitude},{reading.longitude} was naive. Assuming UTC.")
        timestamp_to_write = reading.timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp_to_write = reading.timestamp

    point = (
        Point("air_quality") # Measurement name
        .tag("latitude", str(reading.latitude)) # Tags are indexed
        .tag("longitude", str(reading.longitude))
        .field("pm25", reading.pm25) # Fields are data values
        .field("pm10", reading.pm10)
        .field("no2", reading.no2)
        .field("so2", reading.so2)
        .field("o3", reading.o3)
        # --- CHANGE HERE ---
        # Pass the datetime object directly. Specify precision.
        .time(timestamp_to_write, WritePrecision.MS)
        # --- END CHANGE ---
    )

    # Filter out None fields before writing, as InfluxDB doesn't store null fields natively
    # Rebuild the point adding only non-None fields (tags and time are already set)
    # This prevents errors if some optional fields are None
    filtered_point = Point("air_quality") \
        .tag("latitude", str(reading.latitude)) \
        .tag("longitude", str(reading.longitude)) \
        .time(timestamp_to_write, WritePrecision.MS)

    non_null_fields = {k: v for k, v in reading.model_dump().items() if k not in ['latitude', 'longitude', 'timestamp'] and v is not None}
    if not non_null_fields:
        logger.warning(f"Skipping write for {reading.latitude},{reading.longitude} as no non-null fields were provided.")
        return True # Technically not a write failure, just nothing to write

    for key, value in non_null_fields.items():
        filtered_point.field(key, value)


    try:
        # Write the filtered point
        write_api.write(bucket=influx_bucket, org=influx_org, record=filtered_point)
        logger.debug(f"Successfully wrote point: {filtered_point.to_line_protocol()}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing data: {e}", exc_info=True)
        if hasattr(e, 'response'):
             logger.error(f"InfluxDB Response Headers: {e.response.headers}")
             logger.error(f"InfluxDB Response Body: {e.response.data}")
        return False
    except Exception as e:
        logger.error(f"Generic error writing data: {e}", exc_info=True)
        return False

# --- Example Query Function ---
def query_latest_location_data(lat: float, lon: float, window: str = "1h") -> Optional[dict]:
    """Queries the latest data point for a location within a window."""
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return None

    # Construct Flux query
    # Note: Comparing floats directly can be tricky. Consider querying ranges or geohashing later.
    # This simple query assumes string tags for lat/lon.
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => r["latitude"] == "{lat}")
          |> filter(fn: (r) => r["longitude"] == "{lon}")
          |> last() // Get the most recent point in the window for each field
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") // Reshape fields into columns
    '''
    logger.debug(f"Executing Flux query:\n{flux_query}")
    try:
        tables = query_api.query(query=flux_query, org=influx_org)

        if not tables or not tables[0].records:
             logger.info(f"No data found for lat={lat}, lon={lon} in the last {window}")
             return None

        # Process the result (pivot makes this easier)
        record = tables[0].records[0] # Get the first (and only) record after pivot
        data = record.values # Dictionary of fields and values
        # Add back time and tags if needed
        data["timestamp"] = record.get_time()
        data["latitude"] = float(record.values.get("latitude", lat)) # Get from record or use input
        data["longitude"] = float(record.values.get("longitude", lon))

        logger.debug(f"Query result for {lat},{lon}: {data}")
        return data # Return the dictionary representing the pivoted record

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying data: {e}", exc_info=True)
        if hasattr(e, 'response'):
             logger.error(f"InfluxDB Response Headers: {e.response.headers}")
             logger.error(f"InfluxDB Response Body: {e.response.data}")
        return None
    except Exception as e:
        logger.error(f"Generic error querying data: {e}", exc_info=True)
        return None

# --- Add more query functions as needed ---
# e.g., query_points_in_bbox, query_anomalies, query_density etc.

# Optional: Close client on shutdown (FastAPI events or lifespan manager)
def close_influx_client():
    if client:
        logger.info("Closing InfluxDB client.")
        client.close()