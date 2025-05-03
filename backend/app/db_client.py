# backend/app/db_client.py
import geohash # Import the library
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from .config import get_settings
from .models import AirQualityReading
from typing import List, Optional, Set
import logging
from datetime import datetime, timedelta, timezone
from .models import Anomaly, PollutionDensity
import json # Needed for query formatting
from math import radians, cos, sin, sqrt, atan2

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
    client = None
    write_api = None
    query_api = None

def query_raw_points_in_bbox(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float,
    window: str = "1h", limit: int = 5000
) -> List[AirQualityReading]:
    """
    Queries raw (unaggregated) air quality readings within a given bounding box
    and time window. Returns a list of AirQualityReading objects.
    A limit is applied to prevent excessive data retrieval.
    FIXED: Handles potential float conversion errors before filtering.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available for bbox query.")
        return []

    if min_lat >= max_lat or min_lon >= max_lon:
        logger.warning(f"Invalid bounding box received: {min_lat},{min_lon} -> {max_lat},{max_lon}")
        return []

    # Flux query - FIXED
    flux_query = f'''
        import "math"
        import "types"

        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => exists r.latitude and exists r.longitude) // Ensure tags exist
          // Map tags to potential floats. Conversion errors might result in null or error state.
          |> map(fn: (r) => ({{ r with
                latitude_float: float(v: r.latitude),
                longitude_float: float(v: r.longitude)
             }}))
          // *** FIX: Add filter *after* map to ensure conversion resulted in numeric types ***
          |> filter(fn: (r) =>
                 types.isNumeric(v: r.latitude_float) and
                 types.isNumeric(v: r.longitude_float)
             )
          // Now, safely filter by the numeric lat/lon ranges
          |> filter(fn: (r) =>
                 r.latitude_float >= {min_lat} and r.latitude_float <= {max_lat} and
                 r.longitude_float >= {min_lon} and r.longitude_float <= {max_lon}
             )
          // Filter the actual measurement value (_value column)
          |> filter(fn: (r) => types.isNumeric(v: r._value) and not math.isNaN(f: r._value))
          // Pivot fields into columns
          |> pivot(
                rowKey:["_time", "latitude", "longitude", "geohash"], // Keep original tags + geohash
                columnKey: ["_field"],
                valueColumn: "_value"
             )
          |> limit(n: {limit}) // Apply limit
    '''
    logger.debug(f"Executing FIXED Flux query for raw points in bbox (limit {limit}):\n{flux_query}")

    results: List[AirQualityReading] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org)
        if not tables:
            logger.info(f"No raw points found in bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] window {window}.")
            return []

        processed_times = set()

        for table in tables:
            for record in table.records:
                record_time = record.get_time()
                point_key = (record_time, record.values.get("latitude"), record.values.get("longitude"))

                if point_key in processed_times:
                    continue
                processed_times.add(point_key)

                try:
                    data = record.values
                    lat_str = data.get("latitude")
                    lon_str = data.get("longitude")

                    if lat_str is None or lon_str is None:
                        # This check might be redundant now due to the improved Flux filter, but keep for safety
                        logger.warning(f"Skipping record due to missing lat/lon tag after pivot/filter: {data}")
                        continue

                    # Ensure conversion here matches the Pydantic model types
                    reading = AirQualityReading(
                        latitude=float(lat_str),
                        longitude=float(lon_str),
                        timestamp=record_time,
                        pm25=data.get('pm25'), # Already pivoted, access directly
                        pm10=data.get('pm10'),
                        no2=data.get('no2'),
                        so2=data.get('so2'),
                        o3=data.get('o3'),
                    )
                    results.append(reading)
                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"Error processing raw point record (parsing/type error): {e} - Record: {record.values}", exc_info=False)
                except Exception as e:
                    logger.error(f"Unexpected error processing raw point record: {e} - Record: {record.values}", exc_info=True)

        logger.info(f"Retrieved {len(results)} raw points from bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] window {window}.")
        return results

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying raw points in bbox: {e}", exc_info=True)
        if hasattr(e, 'response') and e.response and hasattr(e.response, 'data'):
             # Log the detailed Flux error message from the response body
             flux_error_msg = e.response.data.decode() if isinstance(e.response.data, bytes) else str(e.response.data)
             logger.error(f"InfluxDB Response Body: {flux_error_msg}")
        return []
    except Exception as e:
        logger.error(f"Generic error querying raw points in bbox: {e}", exc_info=True)
        return []
# --- Query Function for Multiple Points  (air_quality/points)--- DEPRECATED ---
def query_recent_points(limit: int = 50, window: str = "1h") -> List[AirQualityReading]:
    """
    Queries the latest distinct air quality readings from different locations
    within a specified time window.
    This function retrieves *raw* points which can then be aggregated.
    It does not perform aggregation itself.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return []

    # Flux query to get the last point for each lat/lon combination within the window
    # Note: Grouping by lat/lon tags might be slow on large datasets without indices.
    # Consider using geohash tag for grouping if performance is an issue.
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => exists r.latitude and exists r.longitude) // Ensure coords exist
          |> group(columns: ["latitude", "longitude"]) // Group by exact location
          |> last() // Get the latest point in each group
          |> group(columns: ["_measurement"]) // Ungroup before pivot
          |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value")
          |> limit(n: {limit}) // Limit the number of distinct locations returned
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
                    lat_str = data.get("latitude")
                    lon_str = data.get("longitude")
                    if lat_str is None or lon_str is None:
                        logger.warning(f"Skipping record due to missing lat/lon tag: {data}")
                        continue
                    lat = float(lat_str)
                    lon = float(lon_str)

                    reading = AirQualityReading(
                        latitude=lat,
                        longitude=lon,
                        timestamp=record.get_time(), # Pivot keeps time
                        pm25=data.get('pm25'),
                        pm10=data.get('pm10'),
                        no2=data.get('no2'),
                        so2=data.get('so2'),
                        o3=data.get('o3')
                        # Add other potential fields here if needed
                    )
                    results.append(reading)
                except (ValueError, TypeError) as e:
                    logger.error(f"Error processing record for recent points (ValueError/TypeError): {e} - Record: {record.values}", exc_info=False)
                    continue # Skip faulty record
                except Exception as e:
                    logger.error(f"Error processing record for recent points: {e} - Record: {record.values}", exc_info=True)
                    continue # Skip faulty record

        logger.info(f"Retrieved {len(results)} recent points.")
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
        range_filter = f'|> range(start: -24h)' # Default range is fine
    elif start_time and end_time:
         # Ensure timezone-aware before formatting
         # CORRECTED: Remove manual '+ 'Z''
         start_iso = start_time.astimezone(timezone.utc).isoformat()
         end_iso = end_time.astimezone(timezone.utc).isoformat()
         range_filter = f'|> range(start: {start_iso}, stop: {end_iso})'
    elif start_time:
         # CORRECTED: Remove manual '+ 'Z''
         start_iso = start_time.astimezone(timezone.utc).isoformat()
         range_filter = f'|> range(start: {start_iso})'
    else: # Only end_time provided
        # CORRECTED: Remove manual '+ 'Z''
        end_iso = end_time.astimezone(timezone.utc).isoformat()
        # Default start to 0 (beginning of Unix time) is suitable for InfluxDB
        range_filter = f'|> range(start: 0, stop: {end_iso})'


    # Flux query to get anomaly records
    # Flux query to get anomaly records
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          {range_filter}
          |> filter(fn: (r) => r["_measurement"] == "air_quality_anomalies")
          // CORRECTED FILTER: Ensure necessary TAGS exist, and the FIELD is one we will pivot.
          |> filter(fn: (r) => exists r.latitude and exists r.longitude and exists r.parameter and exists r.id) // Check tags
          |> filter(fn: (r) => r["_field"] == "value" or r["_field"] == "description") // Check if field is one of the expected ones
          // Pivot includes tags needed to uniquely identify the anomaly event row
          |> pivot(rowKey:["_time", "id", "latitude", "longitude", "parameter"], columnKey: ["_field"], valueColumn: "_value")
          // Optional: Add a filter *after* pivot if you STRICTLY require both value and description to be present
          // |> filter(fn: (r) => exists r.value and exists r.description)
          |> sort(columns: ["_time"], desc: true) // Optional: sort by time descending
    '''
    logger.debug(f"Executing Flux query for anomalies:\n{flux_query}")

    results: List[Anomaly] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org) # LINE 172 where error occurred
        
        if not tables:
            logger.info("No anomalies found in the specified range.")
            return []

        for table in tables:
            for record in table.records:
                 try:
                    data = record.values
                    # Tags are included in the pivoted rowKey and should be directly accessible
                    lat_str = data.get("latitude")
                    lon_str = data.get("longitude")
                    param_str = data.get("parameter")
                    id_str = data.get("id")
                    val_float = data.get("value") # This is a field from pivot
                    desc_str = data.get("description") # This is a field from pivot

                    # Basic check for required fields/tags after pivot
                    if None in [lat_str, lon_str, param_str, id_str, val_float, desc_str]:
                        logger.warning(f"Skipping anomaly record due to missing fields/tags after pivot: {data}")
                        continue

                    anomaly = Anomaly(
                        id=str(id_str),
                        latitude=float(lat_str),
                        longitude=float(lon_str),
                        timestamp=record.get_time(), # Get timestamp from record metadata
                        parameter=str(param_str),
                        value=float(val_float),
                        description=str(desc_str)
                    )
                    results.append(anomaly)
                 except (ValueError, TypeError, KeyError) as e: # Catch potential parsing errors
                    logger.error(f"Error processing anomaly record (parsing/type error): {e} - Record: {record.values}", exc_info=False)
                    continue # Skip faulty record
                 except Exception as e:
                    logger.error(f"Unexpected error processing anomaly record: {e} - Record: {record.values}", exc_info=True)
                    continue # Skip faulty record

        logger.info(f"Found {len(results)} anomalies.")
        return results

    except InfluxDBError as e:
        # Check if the error is the specific "invalid" code from the log
        if e.response and e.response.status == 400:
            logger.error(f"InfluxDB Bad Request (400) querying anomalies. Invalid Flux Query likely. Error: {e}", exc_info=True)
            logger.error(f"InfluxDB Response Body: {e.response.data}") # Log body for details
        elif "no series found" in str(e).lower() or "no data found" in str(e).lower():
             logger.info("No anomaly data found for the specified query.")
        else:
            logger.error(f"InfluxDB Error querying anomalies: {e}", exc_info=True)
        return [] # Return empty list on error
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
        timestamp_to_write = anomaly.timestamp.astimezone(timezone.utc)

    point = (
        Point("air_quality_anomalies") # Different measurement name
        .tag("latitude", str(anomaly.latitude)) # Tag for location
        .tag("longitude", str(anomaly.longitude)) # Tag for location
        .tag("parameter", anomaly.parameter) # Tag the parameter causing anomaly
        .tag("id", anomaly.id) # Tag the unique ID for potential lookup/grouping
        .field("value", anomaly.value) # Store the anomalous value
        .field("description", anomaly.description) # Store the description
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
# --- Helper: calculate_geohashes_for_bbox (FIXED) ---
# Define the standard geohash base32 characters
GEOHASH_BASE32_CHARS = "0123456789bcdefghjkmnpqrstuvwxyz"

# --- Helper for BBox Geohash Calculation ---
def calculate_geohashes_for_bbox(min_lat, max_lat, min_lon, max_lon, precision) -> List[str]:
    """
    Calculates a list of geohash prefixes of the given precision
    that cover the bounding box.
    Uses a recursive approach for better coverage. (FIXED)
    """
    try:
        import geohash
    except ImportError:
        logger.warning("Geohash library not available for bbox calculation.")
        raise # Re-raise so the caller knows it failed

    checked_hashes: Set[str] = set()
    hashes_in_bbox: Set[str] = set()

    def check_hash(h: str):
        if h in checked_hashes: return
        checked_hashes.add(h)
        try: gh_bbox = geohash.bbox(h)
        except Exception as e:
            # This can happen for invalid hash strings during recursion, log quietly
            logger.debug(f"Could not decode geohash '{h}' during bbox check: {e}")
            return

        hash_min_lat, hash_max_lat = gh_bbox['s'], gh_bbox['n']
        hash_min_lon, hash_max_lon = gh_bbox['w'], gh_bbox['e']
        intersects = (hash_min_lat <= max_lat and hash_max_lat >= min_lat and
                      hash_min_lon <= max_lon and hash_max_lon >= min_lon)
        if not intersects: return

        if len(h) == precision:
            hashes_in_bbox.add(h)
            return

        if len(h) < precision:
            # Check neighbors and subdivide
            neighbors = geohash.neighbors(h)
            # *** FIX: Use the manually defined GEOHASH_BASE32_CHARS ***
            all_to_check = list(neighbors) + [h + char for char in GEOHASH_BASE32_CHARS]
            for next_h in all_to_check:
                 # Optimization: check length before recursive call
                 if len(next_h) <= precision:
                    check_hash(next_h)

    # Start check from a few points
    initial_hashes = set()
    points_to_encode = [
        ( (min_lat + max_lat) / 2, (min_lon + max_lon) / 2 ), # Center
        (min_lat, min_lon), (min_lat, max_lon), (max_lat, min_lon), (max_lat, max_lon) # Corners
    ]
    # Start coarse, but not too coarse to miss details in small target precisions
    start_precision = min(precision, 4) if precision > 1 else 1
    for p_lat, p_lon in points_to_encode:
        try:
            # Ensure coordinates are valid before encoding
            if -90 <= p_lat <= 90 and -180 <= p_lon <= 180:
                initial_hashes.add(geohash.encode(p_lat, p_lon, precision=start_precision))
            else:
                 logger.warning(f"Skipping invalid coordinate for initial hash: {p_lat},{p_lon}")
        except Exception as e: logger.warning(f"Could not encode initial point {p_lat},{p_lon}: {e}")

    if not initial_hashes:
        # This might happen if the input bbox itself is invalid or extremely small
        logger.error(f"Could not generate any initial geohashes for bbox check: [{min_lat},{min_lon} to {max_lat},{max_lon}]")
        # Attempt a single geohash at the target precision from the center as a last resort
        try:
             center_lat = (min_lat + max_lat) / 2
             center_lon = (min_lon + max_lon) / 2
             if -90 <= center_lat <= 90 and -180 <= center_lon <= 180:
                 center_hash = geohash.encode(center_lat, center_lon, precision=precision)
                 logger.info(f"Using single center hash '{center_hash}' as fallback for bbox.")
                 return [center_hash]
        except Exception:
             logger.error("Failed fallback to single center hash.")
             return [] # Truly failed

    for h in initial_hashes: check_hash(h)

    result = list(hashes_in_bbox)
    logger.debug(f"Calculated {len(result)} geohash prefixes for bbox with precision {precision}")
    return result


# --- Query Function for Pollution Density ---
def query_density_in_bbox(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float, window: str = "24h"
) -> Optional[PollutionDensity]:
    """
    Calculates average pollution density within a bounding box and time window,
    primarily using geohash filtering based on the storage precision. (FIXED AGAIN)
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return None

    location_filter = ""
    bbox_geohashes = []
    try:
        bbox_geohashes = calculate_geohashes_for_bbox(
            min_lat, max_lat, min_lon, max_lon,
            precision=7
        )
    except ImportError:
         logger.warning("Geohash library not installed. Cannot use geohash filtering for density query.")
    except Exception as e:
        logger.error(f"Error calculating geohashes for bbox density query: {e}", exc_info=True)

    if bbox_geohashes:
        flux_geohash_set = json.dumps(bbox_geohashes)
        location_filter = f'|> filter(fn: (r) => contains(value: r.geohash, set: {flux_geohash_set}))'
        logger.debug(f"Density query using geohash filter with {len(bbox_geohashes)} prefixes (precision {7}).")
    else:
        # Fallback to coordinate filtering
        logger.warning(f"Density query falling back to coordinate filtering for bbox [{min_lat},{min_lon} - {max_lat},{max_lon}]. This may be less efficient.")
        location_filter = f'''
          |> filter(fn: (r) => exists r.latitude and exists r.longitude)
          |> map(fn: (r) => ({{ r with latitude_float: float(v: r.latitude), longitude_float: float(v: r.longitude) }}))
          |> filter(fn: (r) => r.latitude_float >= {min_lat} and r.latitude_float <= {max_lat} and r.longitude_float >= {min_lon} and r.longitude_float <= {max_lon})
        '''

    # *** FIXES applied to the Flux query string ***
    flux_query = f'''
    import "math"
    import "types" // Import types package for type testing

    base_data = from(bucket: "{influx_bucket}")
      |> range(start: -{window})
      |> filter(fn: (r) => r["_measurement"] == "air_quality")
      {location_filter} // Apply geohash or coordinate filter
      |> filter(fn: (r) => r["_field"] == "pm25" or r["_field"] == "pm10" or r["_field"] == "no2" or r["_field"] == "so2" or r["_field"] == "o3")
      // Ensure values are valid numbers using correct Flux syntax and type check
      // Check type first, then check for NaN only (remove null check)
      |> filter(fn: (r) =>
            types.isNumeric(v: r._value) and // Ensure it's a numeric type first
            not math.isNaN(f: r._value)      // Check for NaN
        ) // <-- Removed 'null' check, only type and NaN check remain

    counts = base_data
      |> group(columns: ["_field"])
      |> count()
      |> group()
      |> yield(name: "counts")

    means = base_data // <-- FIX: Corrected typo from base_da to base_data
      |> group(columns: ["_field"])
      |> mean()
      |> group()
      |> yield(name: "means")
    '''

    logger.debug(f"Executing Flux query for density:\n{flux_query}")
    logger.info(f"{flux_query}")
    try:
        query_results = query_api.query(query=flux_query, org=influx_org)

        mean_data = {}
        count_data = {}
        data_points_count = 0 # Overall count, might be approximated if counts per field differ slightly

        # Extract data from yielded tables
        for table in query_results:
            if not table.records:
                continue # Skip empty tables

            # Get the yielded table name from metadata
            table_name = getattr(table, '_table', None)
            if table_name and hasattr(table_name, '_metadata'):
                yield_name = table_name._metadata.get('name')
            else:
                yield_name = None

            field_name = table.records[0].values.get('_field') # Field name should be consistent within a yielded table
            if not field_name:
                continue # Skip tables without field info

            if yield_name == "means":
                logger.debug(f"Processing 'means' table for field '{field_name}'")
                mean_value = table.records[0].get_value() # Get the calculated mean
                if mean_value is not None:
                    mean_data[field_name] = mean_value
            elif yield_name == "counts":
                logger.debug(f"Processing 'counts' table for field '{field_name}'")
                count_value = table.records[0].get_value() # Get the calculated count
                if count_value is not None:
                    count_data[field_name] = count_value

        if not mean_data and not count_data:
            logger.info(f"No valid data found in bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] for window {window}")
            return None

        # Determine the overall count - use max count found across metrics as a reasonable representation
        if count_data:
            data_points_count = max(count_data.values()) if count_data else 0
            # Log if counts differ significantly (could indicate data sparsity for some metrics)
            if len(set(count_data.values())) > 1:
                 logger.warning(f"Inconsistent counts across fields: {count_data}. Using max value: {data_points_count}")
        else:
             logger.warning("Could not retrieve data point counts.")


        # Construct the result object
        density = PollutionDensity(
            region_name=f"BBox:[{min_lat:.4f},{min_lon:.4f} to {max_lat:.4f},{max_lon:.4f}]", # Increased precision for display
            average_pm25=mean_data.get('pm25'),
            average_pm10=mean_data.get('pm10'),
            average_no2=mean_data.get('no2'),
            average_so2=mean_data.get('so2'),
            average_o3=mean_data.get('o3'),
            data_points_count=data_points_count
        )
        logger.info(f"Calculated density for bbox: PM2.5={density.average_pm25 or 'N/A'}, Count={density.data_points_count}")
        return density

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying density: {e}", exc_info=True)
        if hasattr(e, 'response') and e.response and hasattr(e.response, 'data'):
             # Log the response body which contains the Flux error message
             logger.error(f"InfluxDB Response Body: {e.response.data.decode() if isinstance(e.response.data, bytes) else e.response.data}")
        return None
    except Exception as e:
        logger.error(f"Generic error querying density: {e}", exc_info=True)
        return None



def write_air_quality_data(reading: AirQualityReading):
    """
    Writes a single AirQualityReading to InfluxDB, including a geohash tag
    calculated using the `geohash_precision_storage` setting.
    """
    if not write_api:
        logger.error("InfluxDB write_api not available.")
        return False

    if reading.timestamp.tzinfo is None:
        # logger.warning(f"Timestamp for {reading.latitude},{reading.longitude} was naive. Assuming UTC.")
        timestamp_to_write = reading.timestamp.replace(tzinfo=timezone.utc)
    else:
        # Ensure it's UTC for consistency in InfluxDB
        timestamp_to_write = reading.timestamp.astimezone(timezone.utc)

    # --- START GEOHASH CALCULATION ---
    calculated_geohash = None
    if reading.latitude is not None and reading.longitude is not None:
        try:
            # Use the precision defined in settings for storing geohashes
            storage_precision = settings.geohash_precision_storage
            calculated_geohash = geohash.encode(
                reading.latitude,
                reading.longitude,
                precision=storage_precision # Use storage precision
            )
        except ImportError:
            logger.warning("Geohash library not available for writing geohash tag. Install: pip install python-geohash")
            calculated_geohash = None
        except Exception as e:
            logger.error(f"Could not calculate geohash (precision {storage_precision}) for {reading.latitude},{reading.longitude}: {e}")
            # Proceed without the tag for robustness
            calculated_geohash = None
    # --- END GEOHASH CALCULATION ---

    # Create the base point structure
    # Store lat/lon also as tags for potential simple queries, but rely on geohash for spatial ones
    point = Point("air_quality") \
        .tag("latitude", str(reading.latitude)) \
        .tag("longitude", str(reading.longitude)) \
        .time(timestamp_to_write, WritePrecision.MS)

    # Add the geohash tag IF it was calculated successfully
    if calculated_geohash:
        point.tag("geohash", calculated_geohash) # Add the geohash tag

    # Add non-null fields
    non_null_fields = {
        k: v for k, v in reading.model_dump().items()
        if k not in ['latitude', 'longitude', 'timestamp'] and v is not None
    }

    if not non_null_fields:
        logger.warning(f"Skipping write for {reading.latitude},{reading.longitude} at {timestamp_to_write} as no pollutant fields were provided.")
        return True # Indicate skipped, not failed

    for key, value in non_null_fields.items():
        point.field(key, float(value)) # Ensure values are floats

    # Write the point
    try:
        write_api.write(bucket=influx_bucket, org=influx_org, record=point)
        log_msg = f"Wrote point: lat={reading.latitude}, lon={reading.longitude}"
        if calculated_geohash:
            log_msg += f", geohash={calculated_geohash} (p{storage_precision})"
        # Log full line protocol only in DEBUG level
        logger.debug(log_msg + f" Line Protocol: {point.to_line_protocol()}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing data point: {e}", exc_info=True)
        if hasattr(e, 'response'):
             logger.error(f"InfluxDB Response Headers: {e.response.headers}")
             logger.error(f"InfluxDB Response Body: {e.response.data}")
        logger.error(f"Failed Point Line Protocol: {point.to_line_protocol()}")
        return False
    except Exception as e:
        logger.error(f"Generic error writing data point: {e}", exc_info=True)
        logger.error(f"Failed Point Line Protocol: {point.to_line_protocol()}")
        return False

# --- Example Query Function ---
def query_latest_location_data(
    lat: float,
    lon: float,
    precision: int,  # Precision for the geohash lookup
    window: str = "1h"  # Time window to look back
) -> Optional[AirQualityReading]:
    """
    Queries the latest data point within a specific geohash cell, determined
    by the given lat/lon and precision. If no data is found, estimate by
    expanding the search to a 50 km radius and averaging available points.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available.")
        return None
    if not geohash:
        logger.error("Geohash library not available. Cannot perform geohash-based query.")
        return None

    try:
        # Calculate the target geohash for the given coordinates and precision
        target_geohash = geohash.encode(lat, lon, precision=precision)
        logger.info(f"Querying latest data for geohash '{target_geohash}' (precision {precision}) near ({lat},{lon}), window '{window}'")
    except Exception as e:
        logger.error(f"Failed to calculate geohash for ({lat},{lon}) with precision {precision}: {e}", exc_info=True)
        return None

    # Construct Flux query filtering by the calculated geohash tag
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => r["geohash"] == "{target_geohash}") // Filter by the specific geohash tag
          |> last() // Get the most recent point for each field within this geohash cell
          |> pivot(rowKey:["_time", "geohash", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value") // Reshape fields into columns, keep original tags
    '''
    logger.debug(f"Executing Flux query for specific geohash cell:\n{flux_query}")

    try:
        tables = query_api.query(query=flux_query, org=influx_org)

        if tables and tables[0].records:
            # Process the result (pivot makes this easier)
            record = tables[0].records[0]  # Get the first (and only) record after pivot
            data = record.values  # Dictionary of fields and tags included in pivot rowKey

            # Convert the dictionary result back to Pydantic model
            try:
                stored_lat = float(data.get('latitude', lat))
                stored_lon = float(data.get('longitude', lon))

                reading = AirQualityReading(
                    latitude=stored_lat,
                    longitude=stored_lon,
                    timestamp=record.get_time(),
                    pm25=data.get('pm25'),
                    pm10=data.get('pm10'),
                    no2=data.get('no2'),
                    so2=data.get('so2'),
                    o3=data.get('o3')
                )
                logger.debug(f"Query result for geohash {target_geohash}: {reading}")
                return reading
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Error converting query result for geohash {target_geohash} to Pydantic model: {e}. Data: {data}", exc_info=False)
                return None

        # --- No data found: Estimate using 50 km radius ---
        logger.info(f"No data found for geohash '{target_geohash}' (precision {precision}) near {lat},{lon} in the last {window}. Estimating using 50 km radius.")

        # Approximate 50 km in degrees (1 deg lat ~ 111 km)
        delta_deg = 50.0 / 111.0
        min_lat = lat - delta_deg
        max_lat = lat + delta_deg
        min_lon = lon - delta_deg
        max_lon = lon + delta_deg

        # Query all points in the bounding box in the time window
        flux_query_radius = f'''
            from(bucket: "{influx_bucket}")
              |> range(start: -{window})
              |> filter(fn: (r) => r["_measurement"] == "air_quality")
              |> filter(fn: (r) => exists r.latitude and exists r.longitude)
              |> map(fn: (r) => ({{ r with latitude_float: float(v: r.latitude), longitude_float: float(v: r.longitude) }}))
              |> filter(fn: (r) => r.latitude_float >= {min_lat} and r.latitude_float <= {max_lat} and r.longitude_float >= {min_lon} and r.longitude_float <= {max_lon})
              |> sort(columns: ["_time"], desc: true)
              |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value")
        '''
        logger.debug(f"Executing Flux query for 50km radius estimate:\n{flux_query_radius}")

        tables_radius = query_api.query(query=flux_query_radius, org=influx_org)
        points = []
        for table in tables_radius:
            for record in table.records:
                data = record.values
                try:
                    stored_lat = float(data.get('latitude', lat))
                    stored_lon = float(data.get('longitude', lon))
                    # Calculate distance to center (lat, lon)
                    R = 6371.0  # Earth radius in km
                    dlat = radians(stored_lat - lat)
                    dlon = radians(stored_lon - lon)
                    a = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(stored_lat)) * sin(dlon / 2) ** 2
                    c = 2 * atan2(sqrt(a), sqrt(1 - a))
                    distance = R * c
                    if distance <= 50.0:
                        points.append({
                            "latitude": stored_lat,
                            "longitude": stored_lon,
                            "timestamp": record.get_time(),
                            "pm25": data.get('pm25'),
                            "pm10": data.get('pm10'),
                            "no2": data.get('no2'),
                            "so2": data.get('so2'),
                            "o3": data.get('o3')
                        })
                except Exception as e:
                    logger.debug(f"Skipping record in radius estimate: {e}")

        if not points:
            logger.info(f"No data found within 50 km radius of ({lat},{lon}) in the last {window}.")
            return None

        # Average the values for estimate
        def safe_float(val):
            try:
                return float(val)
            except Exception:
                return None

        def avg(values):
            vals = [safe_float(v) for v in values if v is not None]
            return sum(vals) / len(vals) if vals else None

        pm25_avg = avg([p["pm25"] for p in points])
        pm10_avg = avg([p["pm10"] for p in points])
        no2_avg = avg([p["no2"] for p in points])
        so2_avg = avg([p["so2"] for p in points])
        o3_avg = avg([p["o3"] for p in points])

        # Use the most recent timestamp among the points
        latest_ts = max((p["timestamp"] for p in points if p["timestamp"]), default=None)

        estimate = AirQualityReading(
            latitude=lat,
            longitude=lon,
            timestamp=latest_ts,
            pm25=pm25_avg,
            pm10=pm10_avg,
            no2=no2_avg,
            so2=so2_avg,
            o3=o3_avg
        )
        logger.info(f"Estimated air quality at ({lat},{lon}) using {len(points)} points within 50 km radius.")
        return estimate

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying specific geohash cell data ({target_geohash}): {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Generic error querying specific geohash cell data ({target_geohash}): {e}", exc_info=True)
        return None
def close_influx_client():
    if client:
        logger.info("Closing InfluxDB client.")
        try:
            client.close()
        except Exception as e:
            logger.error(f"Error closing InfluxDB client: {e}", exc_info=True)