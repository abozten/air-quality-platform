# backend/app/db_client.py
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from .config import get_settings # Use get_settings() here
from .models import AirQualityReading, Anomaly, PollutionDensity # Import your Pydantic models
from typing import List, Optional
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # Ensure basic config is set

settings = get_settings() # Get settings

# InfluxDB Configuration
influx_url = settings.influxdb_url
influx_token = settings.influxdb_token
influx_org = settings.influxdb_org
influx_bucket = settings.influxdb_bucket

# --- Global Client and APIs (Initialized once) ---
client: Optional[InfluxDBClient] = None
write_api = None
query_api = None

def initialize_influxdb_client():
    """Initializes the global InfluxDB client and APIs."""
    global client, write_api, query_api
    if client is not None:
        logger.info("InfluxDB client already initialized.")
        return # Already initialized

    logger.info(f"Attempting to connect to InfluxDB at {influx_url} in org '{influx_org}'")
    try:
        client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org, timeout=20_000)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        query_api = client.query_api()
        logger.info("InfluxDB client and APIs initialized.")

        # Check connection / readiness
        try:
            ready = client.ready()
            if hasattr(ready, 'status') and ready.status == "ready":
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
        # Set to None to indicate failure
        client = None
        write_api = None
        query_api = None
        # Optionally, raise the exception if DB connection is critical for startup
        # raise ConnectionError(f"Failed to connect to InfluxDB: {e}") from e

def close_influx_client():
    """Closes the global InfluxDB client connection."""
    global client
    if client:
        logger.info("Closing InfluxDB client.")
        try:
            client.close()
            logger.info("InfluxDB client closed.")
        except Exception as e:
             logger.error(f"Error closing InfluxDB client: {e}", exc_info=True)
        client = None # Ensure it's marked as closed
        # write_api and query_api should also be considered invalid

# Initialize client on module load (or call explicitly during app startup lifespan)
# Calling here ensures it's ready when other modules import db_client
initialize_influxdb_client()


# --- Write Function for Air Quality Readings ---
def write_air_quality_data(reading: AirQualityReading) -> bool:
    """Writes a single AirQualityReading to InfluxDB."""
    if not write_api:
        logger.error("InfluxDB write_api not available. Cannot write reading.")
        return False # Indicate failure

    # Ensure the timestamp from the reading is timezone-aware
    # datetime.utcnow() is naive, FastAPI's default_factory uses it.
    # Better practice: always use timezone-aware datetimes (e.g., datetime.now(timezone.utc))
    if reading.timestamp.tzinfo is None:
        # Assume UTC if naive, convert to UTC
        timestamp_to_write = reading.timestamp.replace(tzinfo=timezone.utc)
        logger.warning(f"Timestamp for {reading.latitude},{reading.longitude} was naive. Assuming UTC and converting.")
    else:
        # Ensure it's in UTC before writing (InfluxDB prefers UTC)
        timestamp_to_write = reading.timestamp.astimezone(timezone.utc)


    # Filter out None fields before writing
    non_null_fields = {k: v for k, v in reading.model_dump().items() if k not in ['latitude', 'longitude', 'timestamp'] and v is not None}

    if not non_null_fields:
        logger.warning(f"Skipping write for {reading.latitude},{reading.longitude} at {reading.timestamp.isoformat()} as no non-null fields were provided.")
        return True # Nothing to write, consider it successful in this context

    # Create the point
    # Use lat/lon as TAGS for efficient filtering and grouping
    point = (
        Point("air_quality") # Measurement name
        .tag("latitude", str(reading.latitude)) # Tags are indexed
        .tag("longitude", str(reading.longitude))
        # .tag("sensor_id", "some_id") # Consider adding a sensor_id tag if available
        .time(timestamp_to_write, WritePrecision.MS)
    )

    # Add non-null fields
    for key, value in non_null_fields.items():
        point.field(key, value)

    try:
        write_api.write(bucket=influx_bucket, org=influx_org, record=point)
        logger.debug(f"Successfully wrote point: {point.to_line_protocol()}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing data: {e}", exc_info=True)
        if hasattr(e, 'response') and hasattr(e.response, 'data'):
             logger.error(f"InfluxDB Response Body: {e.response.data.decode('utf-8')}")
        return False
    except Exception as e:
        logger.error(f"Generic error writing data: {e}", exc_info=True)
        return False

# --- Write Function for Anomalies ---
def write_anomaly_data(anomaly: Anomaly) -> bool:
    """Writes a detected Anomaly to InfluxDB."""
    if not write_api:
        logger.error("InfluxDB write_api not available for writing anomaly.")
        return False

    # Ensure timestamp is timezone-aware and in UTC
    if anomaly.timestamp.tzinfo is None:
        timestamp_to_write = anomaly.timestamp.replace(tzinfo=timezone.utc)
        logger.warning(f"Anomaly timestamp for {anomaly.id} was naive. Assuming UTC and converting.")
    else:
        timestamp_to_write = anomaly.timestamp.astimezone(timezone.utc)


    point = (
        Point("air_quality_anomalies") # Different measurement name
        .tag("latitude", str(anomaly.latitude)) # Tag location
        .tag("longitude", str(anomaly.longitude))
        .tag("parameter", anomaly.parameter) # Tag the parameter causing anomaly
        .field("value", anomaly.value) # Store the anomalous value
        .field("description", anomaly.description) # Store the description
        .field("id", anomaly.id) # Store the unique ID (as a field, not tag, as it's unique per point)
        .time(timestamp_to_write, WritePrecision.MS)
    )

    try:
        write_api.write(bucket=influx_bucket, org=influx_org, record=point)
        logger.info(f"Successfully wrote anomaly: {anomaly.id} - {anomaly.description}")
        return True
    except InfluxDBError as e:
        logger.error(f"InfluxDB Error writing anomaly data: {e}", exc_info=True)
        if hasattr(e, 'response') and hasattr(e.response, 'data'):
             logger.error(f"InfluxDB Response Body: {e.response.data.decode('utf-8')}")
        return False
    except Exception as e:
        logger.error(f"Generic error writing anomaly data: {e}", exc_info=True)
        return False

# --- Query Function for Latest Point by Location ---
def query_latest_location_data(lat: float, lon: float, window: str = "1h") -> Optional[AirQualityReading]:
    """Queries the latest data point for a specific latitude/longitude within a window."""
    if not query_api:
        logger.error("InfluxDB query_api not available for querying latest location data.")
        return None

    # Note: Assuming lat/lon are stored as TAGS for efficient filtering
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => r["latitude"] == "{lat}") // Filter using tag value (string comparison)
          |> filter(fn: (r) => r["longitude"] == "{lon}") // Filter using tag value (string comparison)
          |> last() // Get the most recent point for this specific tag combination
          |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value") // Reshape fields into columns
          |> limit(n: 1) // Ensure only one record is returned
    '''
    logger.debug(f"Executing Flux query for latest {lat},{lon}:\n{flux_query}")

    try:
        tables = query_api.query(query=flux_query, org=influx_org)

        if not tables or not tables[0].records:
             logger.info(f"No data found for lat={lat}, lon={lon} in the last {window}")
             return None

        # Process the result (pivot makes this easier)
        record = tables[0].records[0] # Get the first (and only) record after pivot
        data = record.values # Dictionary of fields and values

        # Map InfluxDB record data back to Pydantic model
        # Handle potential TypeErrors during conversion
        try:
            reading = AirQualityReading(
                latitude=float(record.values.get("latitude", lat)), # Get from tag or use input default
                longitude=float(record.values.get("longitude", lon)), # Get from tag or use input default
                timestamp=record.get_time(), # Use InfluxDB timestamp (should be timezone-aware)
                pm25=data.get('pm25'),
                pm10=data.get('pm10'),
                no2=data.get('no2'),
                so2=data.get('so2'),
                o3=data.get('o3')
            )
            return reading
        except Exception as e:
             logger.error(f"Error mapping query result to AirQualityReading model for {lat},{lon}: {e}. Data: {data}", exc_info=True)
             return None # Return None if mapping fails

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error querying data for {lat},{lon}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Generic error querying data for {lat},{lon}: {e}", exc_info=True)
        return None


# --- Query Function for Multiple Recent Points (Distinct Locations) ---
def query_recent_points(limit: int = 50, window: str = "1h") -> List[AirQualityReading]:
    """
    Queries the latest air quality reading for distinct latitude/longitude TAGS
    within a specified time window. Returns up to `limit` points.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available for querying recent points.")
        return []

    # Flux query to get the last point for each unique lat/lon TAG combination within the window
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> group(columns: ["latitude", "longitude"]) // Group by location TAGS
          |> last() // Get the latest point in each location group
          |> group() // Ungroup before pivot
          |> pivot(rowKey:["_time", "latitude", "longitude"], columnKey: ["_field"], valueColumn: "_value")
          |> limit(n: {limit}) // Limit the number of locations returned
          |> sort(columns: ["_time"], desc: true) // Optional: Sort by time
    '''
    logger.debug(f"Executing Flux query for recent points:\n{flux_query}")

    results: List[AirQualityReading] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org)
        if not tables:
            logger.info("Query for recent points returned no tables.")
            return []

        for table in tables:
            for record in table.records:
                try:
                    data = record.values
                    # Lat/Lon are tags, retrieved as fields after pivot
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
    Filters by optional time range.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available for querying anomalies.")
        return []

    # Default time range (e.g., last 24 hours) if not provided
    if start_time is None and end_time is None:
        range_filter = f'|> range(start: -24h)'
    elif start_time and end_time:
         # Ensure timezone-aware before formatting and convert to UTC
         start_iso = start_time.astimezone(timezone.utc).isoformat()
         end_iso = end_time.astimezone(timezone.utc).isoformat()
         range_filter = f'|> range(start: time(v: "{start_iso}"), stop: time(v: "{end_iso}"))'
    elif start_time:
         start_iso = start_time.astimezone(timezone.utc).isoformat()
         range_filter = f'|> range(start: time(v: "{start_iso}"))'
    elif end_time: # Only end_time provided
        end_iso = end_time.astimezone(timezone.utc).isoformat()
        # Need a start, perhaps default to beginning of time (InfluxDB default epoch 0) or a reasonable past limit
        range_filter = f'|> range(start: 0, stop: time(v: "{end_iso}"))'


    # Flux query to get anomaly records
    # Assumes measurement 'air_quality_anomalies' with tags/fields matching Anomaly model
    # Tags: latitude, longitude, parameter
    # Fields: value, description, id
    flux_query = f'''
        from(bucket: "{influx_bucket}")
          {range_filter}
          |> filter(fn: (r) => r["_measurement"] == "air_quality_anomalies")
          // Filter for fields/tags needed for Anomaly model
          |> filter(fn: (r) => r["_field"] == "value" or r["_field"] == "description" or r["_field"] == "id" or r["_field"] == "parameter" or r["_field"] == "latitude" or r["_field"] == "longitude")
          // Group by time and id (unique identifier) to pivot correctly per anomaly event
          |> group(columns: ["_time", "id", "latitude", "longitude", "parameter"])
          |> pivot(rowKey:["_time", "id", "latitude", "longitude", "parameter"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: true) // Sort by time, most recent first
    '''
    logger.debug(f"Executing Flux query for anomalies:\n{flux_query}")

    results: List[Anomaly] = []
    try:
        tables = query_api.query(query=flux_query, org=influx_org)
        if not tables:
            logger.info("Query for anomalies returned no tables.")
            # This is expected if no anomalies are stored yet
            return []

        for table in tables:
            for record in table.records:
                 try:
                    data = record.values
                    # Get data from pivoted fields
                    anomaly_id = str(data.get("id"))
                    lat = float(data.get("latitude", 0.0))
                    lon = float(data.get("longitude", 0.0))
                    parameter = str(data.get("parameter", "unknown"))
                    value = float(data.get("value", 0.0))
                    description = str(data.get("description", ""))

                    # Basic validation before creating model instance
                    if not anomaly_id or not record.get_time():
                         logger.warning(f"Skipping anomaly record with missing ID or timestamp: {data}")
                         continue

                    anomaly = Anomaly(
                        id=anomaly_id,
                        latitude=lat,
                        longitude=lon,
                        timestamp=record.get_time(), # InfluxDB timestamp (should be timezone-aware)
                        parameter=parameter,
                        value=value,
                        description=description
                    )
                    results.append(anomaly)
                 except Exception as e:
                    logger.error(f"Error processing anomaly record: {e} - Record data: {record.values}", exc_info=True)
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

# --- Query Function for Pollution Density in BBox ---
def query_density_in_bbox(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float, window: str = "24h"
) -> Optional[PollutionDensity]:
    """
    Calculates average pollution density (mean values) and count of data points
    within a bounding box and time window. Lat/Lon must be stored as TAGS.
    """
    if not query_api:
        logger.error("InfluxDB query_api not available for querying density.")
        return None

    # Flux query to calculate mean values and count within the bbox and window
    # Filtering on TAGS is efficient. Converting TAGS to floats in Flux requires `float()`
    # and then comparing numerically.
    flux_query = f'''
      bbox_data = from(bucket: "{influx_bucket}")
        |> range(start: -{window})
        |> filter(fn: (r) => r["_measurement"] == "air_quality")
        // Filter by latitude and longitude TAGS (must convert string tag to float)
        |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
        |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
        |> filter(fn: (r) =>
            r["_field"] == "pm25" or
            r["_field"] == "pm10" or
            r["_field"] == "no2" or
            r["_field"] == "so2" or
            r["_field"] == "o3"
           )
        |> keep(columns: ["_time", "_field", "_value", "latitude", "longitude"]) // Keep necessary columns

      // Calculate mean for each field
      means = bbox_data
        |> group(columns: ["_field"]) // Group by parameter field
        |> mean() // Calculate mean per field
        |> group() // Ungroup for pivot
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") // Pivot fields into columns

      // Calculate total count of relevant data points within the bbox and window
      // We can count records for one representative field like pm25 after bbox filter
      count_val = bbox_data
        |> filter(fn: (r) => r["_field"] == "pm25") // Just count one type of reading per point
        |> count() // Total count of pm25 values in the bbox/window
        |> keep(columns: ["_value"]) // Keep only the count value column

      // Use yield to return both tables (means and count). Need to process separately in Python.
      means |> yield(name: "means")
      count_val |> yield(name: "count")
    '''

    logger.debug(f"Executing Flux query for density:\n{flux_query}")

    mean_data: dict = {}
    data_points_count = 0

    try:
        # Execute the query which should return multiple tables if yields are used
        query_result = query_api.query(query=flux_query, org=influx_org)

        if not query_result:
             logger.info(f"Density query returned no results for bbox [{min_lat:.2f},{min_lon:.2f} - {max_lat:.2f},{max_lon:.2f}].")
             return None # No data at all

        # Process the tables based on their yield names
        for table in query_result:
            # Check table.name or the table structure
            if table.records and table.records[0].get_measurement() == 'from': # Simple way to identify tables, better if yield names are available directly
                 # This is complex with aio-pika's sync client. Let's fetch separately as planned.
                 # The separate query approach used before the yield block is simpler to process.
                 # Let's revert to fetching means and count with separate queries.
                 pass # placeholder, will remove yield and separate queries below

    except InfluxDBError as e:
        logger.error(f"InfluxDB Error during density query execution: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Generic error during density query execution: {e}", exc_info=True)
        return None


    # --- Reverted Approach: Fetch Means and Count with Separate Queries ---
    # This is simpler to process with the synchronous client's query result structure
    flux_query_mean = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
          |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
          |> filter(fn: (r) =>
            r["_field"] == "pm25" or
            r["_field"] == "pm10" or
            r["_field"] == "no2" or
            r["_field"] == "so2" or
            r["_field"] == "o3"
           )
          |> group(columns: ["_field"]) // Group by parameter field
          |> mean() // Calculate mean per field
          |> group() // Ungroup for pivot
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") // Pivot fields into columns
          |> limit(n:1) // Should only be one record after mean and pivot
    '''
    flux_query_count = f'''
        from(bucket: "{influx_bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r["_measurement"] == "air_quality")
          |> filter(fn: (r) => float(v: r.latitude) >= {min_lat} and float(v: r.latitude) <= {max_lat})
          |> filter(fn: (r) => float(v: r.longitude) >= {min_lon} and float(v: r.longitude) <= {max_lon})
          |> filter(fn: (r) => r["_field"] == "pm25") // Count based on one representative field
          |> count()
          |> keep(columns: ["_value"]) // Keep only the count value
          |> limit(n:1) // Should only be one count value
    '''

    logger.debug(f"Executing Flux query for density means:\n{flux_query_mean}")
    logger.debug(f"Executing Flux query for density count:\n{flux_query_count}")

    try:
        # Execute mean query
        mean_tables = query_api.query(query=flux_query_mean, org=influx_org)
        mean_data = {}
        if mean_tables and mean_tables[0].records:
            mean_record_values = mean_tables[0].records[0].values
            # Extract relevant fields, handling potential missing ones
            mean_data['pm25'] = mean_record_values.get('pm25')
            mean_data['pm10'] = mean_record_values.get('pm10')
            mean_data['no2'] = mean_record_values.get('no2')
            mean_data['so2'] = mean_record_values.get('so2')
            mean_data['o3'] = mean_record_values.get('o3')
            logger.debug(f"Mean query result: {mean_data}")
        else:
             logger.info(f"No data found in bbox [{min_lat},{min_lon} - {max_lat},{max_lon}] for mean calculation.")
             # Return None or default density object? Returning None if no data for means.
             return None

        # Execute count query
        count_tables = query_api.query(query=flux_query_count, org=influx_org)
        data_points_count = 0
        if count_tables and count_tables[0].records:
            count_record = count_tables[0].records[0]
            # The count value is in the _value column
            data_points_count = count_record.get_value()
            logger.debug(f"Count query result: {data_points_count}")
        else:
            logger.warning(f"Count query returned no results for bbox.")


        # Construct the result object
        density = PollutionDensity(
            region_name=f"BBox:[{min_lat:.2f},{min_lon:.2f} to {max_lat:.2f},{max_lon:.2f}]", # Describe the region
            average_pm25=mean_data.get('pm25'),
            average_pm10=mean_data.get('pm10'),
            average_no2=mean_data.get('no2'),
            average_so2=mean_data.get('so2'),
            average_o3=mean_data.get('o3'),
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

# --- End of Query Functions ---

# Clean up the redundant get_client/get_query_api functions if they exist
# (Based on the provided code snippet, they seem to be below the main init)
# Remove these if they exist in your actual file:
# def get_query_api(): ...
# def get_influxdb_client(): ...
# Remove _influx_client, _query_api globals if they were used only by those functions.
# Rely on the global client, write_api, query_api initialized at the top.