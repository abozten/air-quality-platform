# backend/app/database.py
import os
import asyncpg
from asyncpg.pool import Pool
from dotenv import load_dotenv
import logging

# Load environment variables from .env file if it exists (for local development)
load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Global variable to hold the pool
db_pool: Pool | None = None

async def connect_to_db():
    """Establishes the database connection pool."""
    global db_pool
    try:
        logger.info(f"Attempting to connect to database...")
        # Extract dbname for logging, mask password
        dsn_parts = asyncpg.connect_utils._parse_connect_dsn(DATABASE_URL)
        masked_dsn = {k: ('*****' if k == 'password' else v) for k, v in dsn_parts[1].items()}
        logger.info(f"Connection DSN parts (masked): {masked_dsn}")

        db_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,  # Minimum number of connections in the pool
            max_size=10, # Maximum number of connections in the pool
            # command_timeout=60 # Example: set command timeout
        )
        logger.info("Database connection pool established successfully.")
        # You might want to run initialization logic here (e.g., check extension)
        await initialize_timescaledb(db_pool)

    except Exception as e:
        logger.exception(f"Failed to connect to database: {e}")
        # Depending on your app's needs, you might want to exit or handle this differently
        db_pool = None # Ensure pool is None if connection failed

async def close_db_connection():
    """Closes the database connection pool."""
    global db_pool
    if db_pool:
        logger.info("Closing database connection pool...")
        await db_pool.close()
        logger.info("Database connection pool closed.")
        db_pool = None

async def get_db_pool() -> Pool:
    """Returns the active database pool."""
    if db_pool is None:
         # This case should ideally not happen if connect_to_db is called at startup
         # Maybe raise an error or attempt to reconnect?
         logger.error("Database pool is not initialized!")
         raise RuntimeError("Database pool not available. Ensure connect_to_db() was called.")
    return db_pool

async def initialize_timescaledb(pool: Pool):
    """Checks if the timescaledb extension is enabled and creates it if not."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            try:
                # Check if extension exists
                exists = await connection.fetchval("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'timescaledb');")
                if not exists:
                    logger.info("TimescaleDB extension not found. Attempting to create...")
                    await connection.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
                    logger.info("TimescaleDB extension created successfully.")
                else:
                    logger.info("TimescaleDB extension already enabled.")

                # --- Create initial tables/hypertables here or use migrations ---
                await create_initial_schema(connection)

            except Exception as e:
                logger.exception(f"Error during TimescaleDB initialization: {e}")
                # Decide how to handle this - maybe raise the exception?

async def create_initial_schema(connection):
    """Creates the initial air_quality_readings table and hypertable."""
    logger.info("Checking/Creating air_quality_readings table...")
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS air_quality_readings (
            timestamp TIMESTAMPTZ NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            pm25 REAL,
            pm10 REAL,
            no2 REAL,
            so2 REAL,
            o3 REAL,
            -- Optional: Add metadata columns like sensor_id, source, etc.
            -- sensor_id VARCHAR(50),
            -- source VARCHAR(50) DEFAULT 'manual',
            -- Add constraints if needed
            CONSTRAINT check_lat CHECK (latitude >= -90 AND latitude <= 90),
            CONSTRAINT check_lon CHECK (longitude >= -180 AND longitude <= 180)
        );
    """)
    logger.info("air_quality_readings table ensured.")

    # Check if it's already a hypertable before trying to create it
    is_hypertable = await connection.fetchval("""
        SELECT EXISTS (
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'air_quality_readings'
        );
    """)

    if not is_hypertable:
        logger.info("Converting air_quality_readings to hypertable...")
        # Convert the table to a TimescaleDB hypertable, partitioned by time
        # Choose chunk_time_interval based on expected data volume and query patterns
        # E.g., '1 day' or '7 days' are common starting points
        await connection.execute("""
            SELECT create_hypertable(
                'air_quality_readings',
                'timestamp',
                chunk_time_interval => INTERVAL '1 day',
                if_not_exists => TRUE
            );
        """)
        # Optional: Add space partitioning (e.g., on latitude/longitude or a geohash)
        # Requires enterprise license or TimescaleDB Cloud/HA image for partitioning on >1 dimension beyond time.
        # await connection.execute("SELECT add_dimension('air_quality_readings', 'latitude', number_partitions => 4, if_not_exists => TRUE);")
        # await connection.execute("SELECT add_dimension('air_quality_readings', 'longitude', number_partitions => 4, if_not_exists => TRUE);")

        # Optional: Setup compression policy (Available in Apache 2.0 licensed TimescaleDB >= 2.0)
        logger.info("Setting up compression policy for air_quality_readings...")
        await connection.execute("""
            ALTER TABLE air_quality_readings SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'latitude, longitude' -- Optional: Segment compression by location
            );
        """)
        await connection.execute("""
            SELECT add_compression_policy('air_quality_readings', compress_after => INTERVAL '7 days', if_not_exists => TRUE);
        """)

        # Optional: Setup data retention policy (drop data older than, e.g., 1 year)
        # logger.info("Setting up data retention policy...")
        # await connection.execute("""
        #     SELECT add_retention_policy('air_quality_readings', drop_after => INTERVAL '1 year', if_not_exists => TRUE);
        # """)

        logger.info("Hypertable setup complete for air_quality_readings.")
    else:
         logger.info("air_quality_readings is already a hypertable.")