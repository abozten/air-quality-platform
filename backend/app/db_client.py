# backend/app/db_client.py
import geohash # Import the library
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from .config import get_settings
from .models import AirQualityReading
from typing import List, Optional
import logging
from datetime import datetime, timedelta, timezone
from .models import Anomaly, PollutionDensity
import json # Needed for query formatting later

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
    Calculates average pollution density within a bounding box and time window,
    using geohash filtering if available and enabled.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return None

    # --- USE GEOHASHING ---
    use_geohash = True # Enable geohash filtering
    location_filter = ""

    if use_geohash:
        # Calculate geohashes covering the bbox using the *same precision* as stored
        bbox_geohashes = calculate_geohashes_for_bbox(
            min_lat, max_lat, min_lon, max_lon,
            precision=settings.geohash_precision_storage
        )

        if bbox_geohashes:
            # Format the list for the Flux 'contains' function set parameter
            # Use json.dumps for safe formatting of the list into a string
            flux_geohash_set = json.dumps(bbox_geohashes)
            # Filter points where the 'geohash' tag is one of the calculated prefixes
            location_filter = f'|> filter(fn: (r) => contains(value: r.geohash, set: {flux_geohash_set}))'
            logger.debug(f"Using geohash filter with {len(bbox_geohashes)} prefixes.")
        else:
            logger.warning("Could not calculate geohashes for bbox, falling back to coordinate filtering.")
            use_geohash = False # Fallback if calculation failed

    if not use_geohash:
        # Fallback to numerical filtering (less efficient for large datasets)
        # Ensure tags are treated as floats for comparison
        location_filter = f'''
          |> filter(fn: (r) => exists r.latitude and exists r.longitude)
          |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
          |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
        '''
        logger.debug("Using float coordinate filtering.")

    # Single optimized query that gets both means and count in one pass
    flux_query = f'''
    import "json" // Not strictly needed here unless converting results, but good practice

    // Define the base dataset
    base_data = from(bucket: "{influx_bucket}")
      |> range(start: -{window})
      |> filter(fn: (r) => r["_measurement"] == "air_quality")
      // Apply the chosen location filter (geohash or coordinate)
      {location_filter}
      // Filter by desired fields AFTER location filter for efficiency
      |> filter(fn: (r) => r["_field"] == "pm25" or r["_field"] == "pm10" or r["_field"] == "no2" or r["_field"] == "so2" or r["_field"] == "o3")


    // Calculate counts per field
    counts = base_data
      |> group(columns: ["_field"]) // Group only by field to get total count per field
      |> count(column: "_value")
      |> group() // Ungroup before yield
      |> yield(name: "counts")

    // Calculate means in one pass
    means = base_data
      |> group(columns: ["_field"]) // Group only by field to get overall mean per field
      |> mean(column: "_value")
      |> group() // Ungroup before yield
      |> yield(name: "means")
    '''

    logger.debug(f"Executing Flux query for density:\n{flux_query}")

    try:
        results = query_api.query(query=flux_query, org=influx_org) # Changed variable name

        mean_data = {}
        data_points_count = 0
        count_values = []

        # Extract data from tables
        for table in results: # Iterate through the yielded tables
            if table.name == "means" and table.records:
                 logger.debug(f"Processing 'means' table with {len(table.records)} records.")
                 for record in table.records:
                    field_name = record.values.get('_field') # Mean results are grouped by field
                    field_value = record.get_value()
                    if field_name:
                        mean_data[field_name] = field_value
            elif table.name == "counts" and table.records:
                 logger.debug(f"Processing 'counts' table with {len(table.records)} records.")
                 for record in table.records:
                     # Store counts for each field to potentially check consistency
                     count_values.append(record.get_value())


        if not mean_data:
            logger.info(f"No data found in bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] for window {window}")
            return None

        # Use the first count value, assuming counts are consistent across fields after filtering
        if count_values:
            data_points_count = count_values[0]
            if not all(c == data_points_count for c in count_values):
                 logger.warning(f"Inconsistent counts across fields: {count_values}. Using first value: {data_points_count}")
        else:
             logger.warning("Could not retrieve data point counts.")


        # Construct the result object
        density = PollutionDensity(
            region_name=f"BBox:[{min_lat:.3f},{min_lon:.3f} to {max_lat:.3f},{max_lon:.3f}]", # Increased precision
            average_pm25=mean_data.get('pm25'),
            average_pm10=mean_data.get('pm10'),
            average_no2=mean_data.get('no2'),
            average_so2=mean_data.get('so2'),
            average_o3=mean_data.get('o3'),
            data_points_count=data_points_count
        )
        logger.info(f"Calculated density: PM2.5={density.average_pm25 or 'N/A'}, Count={density.data_points_count}")
        return density

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying density: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Generic error querying density: {e}", exc_info=True)
        return None

def calculate_geohashes_for_bbox(min_lat, max_lat, min_lon, max_lon, precision): # Use the precision argument
    """
    Calculate a list of geohash prefixes covering the bounding box.
    (Simple sampling approach)
    """
    # Check if library is available first
    try:
        import geohash
    except ImportError:
        logger.warning("Geohash library not available for bbox calculation. Install with: pip install python-geohash")
        return []

    # This is a simplified approach - might include slightly more hashes than strictly needed
    # Consider a more precise algorithm like 'geohash_bbox' from external libs if needed
    lat_step = (max_lat - min_lat) / 10
    lon_step = (max_lon - min_lon) / 10

    geohashes = set()

    # Sample points including corners and center
    sample_lats = [min_lat] + [min_lat + i * lat_step for i in range(1, 10)] + [max_lat]
    sample_lons = [min_lon] + [min_lon + i * lon_step for i in range(1, 10)] + [max_lon]

    for lat in sample_lats:
        for lon in sample_lons:
            # Ensure the sample point is strictly within the bbox for encoding
            if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                try:
                    h = geohash.encode(lat, lon, precision=precision)
                    geohashes.add(h[:precision]) # Ensure we only add the prefix of desired length
                except Exception as e:
                     logger.warning(f"Error encoding geohash for sample point {lat},{lon}: {e}")

    # Add geohashes of the corners explicitly
    corners = [(min_lat, min_lon), (min_lat, max_lon), (max_lat, min_lon), (max_lat, max_lon)]
    for lat, lon in corners:
         try:
             h = geohash.encode(lat, lon, precision=precision)
             geohashes.add(h[:precision])
         except Exception as e:
             logger.warning(f"Error encoding geohash for corner point {lat},{lon}: {e}")


    logger.debug(f"Calculated {len(geohashes)} geohash prefixes for bbox with precision {precision}")
    return list(geohashes)

def write_air_quality_data(reading: AirQualityReading):
    """Writes a single AirQualityReading to InfluxDB, including a geohash tag."""
    if not write_api:
        logger.error("InfluxDB write_api not available.")
        return False

    if reading.timestamp.tzinfo is None:
        logger.warning(f"Timestamp for {reading.latitude},{reading.longitude} was naive. Assuming UTC.")
        timestamp_to_write = reading.timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp_to_write = reading.timestamp

    # --- START GEOHASH CALCULATION ---
    calculated_geohash = None
    if reading.latitude is not None and reading.longitude is not None:
        try:
            calculated_geohash = geohash.encode(
                reading.latitude,
                reading.longitude,
                precision=settings.geohash_precision_storage
            )
        except Exception as e:
            logger.error(f"Could not calculate geohash for {reading.latitude},{reading.longitude}: {e}")
            # Decide if you want to fail the write or just proceed without the tag
            # Proceeding without the tag for robustness:
            calculated_geohash = None
    # --- END GEOHASH CALCULATION ---

    # Create the base point structure
    point = Point("air_quality") \
        .tag("latitude", str(reading.latitude)) \
        .tag("longitude", str(reading.longitude)) \
        .time(timestamp_to_write, WritePrecision.MS)

    # Add the geohash tag IF it was calculated successfully
    if calculated_geohash:
        point.tag("geohash", calculated_geohash) # Add the geohash tag

    # Add non-null fields (as before)
    non_null_fields = {k: v for k, v in reading.model_dump().items() if k not in ['latitude', 'longitude', 'timestamp'] and v is not None}
    if not non_null_fields:
        logger.warning(f"Skipping write for {reading.latitude},{reading.longitude} as no non-null fields were provided.")
        return True # Nothing to write

    for key, value in non_null_fields.items():
        point.field(key, value) # Add fields to the point object

    # Write the point (which now includes fields and potentially the geohash tag)
    try:
        write_api.write(bucket=influx_bucket, org=influx_org, record=point)
        log_msg = f"Successfully wrote point for {reading.latitude},{reading.longitude}"
        if calculated_geohash:
            log_msg += f" (geohash: {calculated_geohash})"
        logger.debug(log_msg + f" Line Protocol: {point.to_line_protocol()}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing data: {e}", exc_info=True)
        # ... (rest of error handling) ...
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