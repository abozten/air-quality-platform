# backend/app/worker.py
import asyncio # Use asyncio
import aio_pika # Use aio-pika
import json
import logging
import sys
import signal # For graceful shutdown
from datetime import datetime, timezone

# Configure logging early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Use relative imports
try:
    from .config import get_settings # Use get_settings() here
    from .models import AirQualityReading, IngestRequest, Anomaly
    from . import db_client # Keep sync DB client for now
    from . import anomaly_detection # Keep sync anomaly detection
except ImportError as e:
     logger.error(f"Failed to import necessary modules. Ensure structure is correct. Error: {e}")
     sys.exit(1)

settings = get_settings() # Get settings
RAW_DATA_QUEUE = settings.rabbitmq_queue_raw
RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
PREFETCH_COUNT = 10 # How many messages the worker can process concurrently (tune as needed)

async def process_message(message: aio_pika.IncomingMessage):
    """Async callback function to process a message from the queue."""
    # Use the context manager for automatic ACK/NACK based on exceptions
    # Requeue=False means messages causing processing errors are discarded
    async with message.process(requeue=False, ignore_processed=True):
        logger.info(f"WORKER: Received message. Delivery tag: {message.delivery_tag}")
        data = None
        try:
            # 1. Decode body
            logger.debug("WORKER: Attempting to decode message body...")
            body_str = message.body.decode('utf-8')
            logger.debug("WORKER: Body decoded.")

            # 2. Parse JSON
            logger.debug("WORKER: Attempting to parse JSON...")
            data = json.loads(body_str)
            logger.debug(f"WORKER: JSON parsed.") # Avoid logging full data unless necessary

            # 3. Validate with Pydantic (using IngestRequest model from API)
            logger.debug("WORKER: Attempting Pydantic validation...")
            try:
                ingest_data = IngestRequest(**data)
                logger.debug("WORKER: Pydantic validation successful.")
            except Exception as pydantic_error:
                logger.error(f"WORKER: Pydantic validation failed for incoming data. Error: {pydantic_error}. Discarding message (Delivery tag: {message.delivery_tag}).", exc_info=True)
                return # Stop processing this message

            # 4. Process Validated Data
            logger.info(f"WORKER: Processing reading for {ingest_data.latitude},{ingest_data.longitude} (Delivery tag: {message.delivery_tag})...")
            # Create the AirQualityReading object, adding the timestamp from the worker's perspective
            reading = AirQualityReading(
                latitude=ingest_data.latitude,
                longitude=ingest_data.longitude,
                timestamp=datetime.now(timezone.utc), # Worker adds the timestamp (UTC)
                pm25=ingest_data.pm25,
                pm10=ingest_data.pm10,
                no2=ingest_data.no2,
                so2=ingest_data.so2,
                o3=ingest_data.o3
            )
            logger.debug(f"WORKER: Constructed AirQualityReading object for {reading.latitude},{reading.longitude} at {reading.timestamp.isoformat()}")

            # --- Synchronous DB/Anomaly Logic ---
            # NOTE: These are blocking calls within an async function.
            # For true async performance, use async DB clients and potentially run checks concurrently.
            # Using loop.run_in_executor is the standard way to run sync code in async:

            loop = asyncio.get_running_loop()

            # 4.1. Write data to InfluxDB (Run sync call in executor)
            logger.debug("WORKER: Attempting sync write to InfluxDB via executor...")
            try:
                write_success = await loop.run_in_executor(None, db_client.write_air_quality_data, reading)
                if not write_success:
                    logger.error(f"WORKER: Failed sync write to InfluxDB for {reading.latitude},{reading.longitude}. Discarding message (Delivery tag: {message.delivery_tag}).")
                    # Context manager will NACK because of the raised exception below
                    raise RuntimeError("Failed to write data to InfluxDB") # Raise to trigger NACK
                logger.debug("WORKER: Sync write to InfluxDB successful.")
            except Exception as write_ex:
                 logger.error(f"WORKER: Exception during sync write execution for {reading.latitude},{reading.longitude}: {write_ex}", exc_info=True)
                 # Let context manager handle NACK (it will NACK because of this exception)
                 raise write_ex # Re-raise to ensure NACK

            # 4.2. Perform Anomaly Detection (Run sync call in executor)
            logger.debug("WORKER: Checking sync for anomalies via executor...")
            anomaly = None # Initialize anomaly variable
            try:
                anomaly = await loop.run_in_executor(None, anomaly_detection.check_thresholds, reading)
                if anomaly:
                    logger.info(f"WORKER: Anomaly detected: {anomaly.description} (Delivery tag: {message.delivery_tag}).") # Changed level to INFO
            except Exception as anomaly_ex:
                logger.error(f"WORKER: Exception during sync anomaly check for {reading.latitude},{reading.longitude}: {anomaly_ex}", exc_info=True)
                # Anomaly check failure is NOT a reason to NACK the message; the data was written.
                # Log and continue.

            # 4.3. Write Anomaly if detected (Run sync call in executor)
            if anomaly:
                logger.debug("WORKER: Attempting sync anomaly write via executor...")
                try:
                    write_anomaly_success = await loop.run_in_executor(None, db_client.write_anomaly_data, anomaly)
                    if not write_anomaly_success:
                        logger.error(f"WORKER: Failed sync write for detected anomaly {anomaly.id}. (Delivery tag: {message.delivery_tag}).")
                        # Anomaly write failure is NOT a reason to NACK the original data message. Log and continue.
                    else:
                         logger.debug("WORKER: Sync anomaly write successful.")
                except Exception as write_anomaly_ex:
                    logger.error(f"WORKER: Exception during sync anomaly write execution for {anomaly.id}: {write_anomaly_ex}", exc_info=True)
                    # Anomaly write failure is NOT a reason to NACK the original data message. Log and continue.

            # --- End Synchronous Block via Executor ---

            # If we reach here without unhandled exceptions, the context manager will ACK the message.
            logger.info(f"WORKER: Successfully processed message for {reading.latitude},{reading.longitude}. Message ACKed. (Delivery tag: {message.delivery_tag})")

        except json.JSONDecodeError:
            logger.error(f"WORKER: JSONDecodeError. Body (start): {message.body[:100]}... Discarding message (Delivery tag: {message.delivery_tag}).", exc_info=True)
        except UnicodeDecodeError:
            logger.error(f"WORKER: UnicodeDecodeError. Body (repr): {message.body!r}. Discarding message (Delivery tag: {message.delivery_tag}).", exc_info=True)
        except Exception as e:
            # Catch-all for unexpected errors during processing before explicit NACK/ACK points
            # Note: Errors in steps 3, 4.1, 4.2, 4.3 might be caught here if not explicitly handled.
            # The `message.process` context manager should handle exceptions raised within it.
            # This catch-all is a safety net but indicates potential issues with finer-grained error handling.
            logger.error(f"WORKER: Unexpected error processing message: {e}. Data (if parsed): {data}. Discarding message (Delivery tag: {message.delivery_tag}).", exc_info=True)
            # The `message.process` context manager will NACK on unhandled exceptions.

async def start_consuming(loop):
    """Connects to RabbitMQ and starts consuming messages asynchronously."""
    connection = None
    channel = None
    consumer_tag = None # To hold the tag for stopping the consumer
    try:
        while True: # Keep trying to connect
            try:
                logger.info("WORKER: Attempting async connection to RabbitMQ...")
                # Use robust connection which handles reconnects
                connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop, timeout=15)
                logger.info("WORKER: Async connection established.")

                # Creating a channel
                channel = await connection.channel()
                logger.info("WORKER: Channel created.")

                # Set Quality of Service - limits the number of unacknowledged messages
                await channel.set_qos(prefetch_count=PREFETCH_COUNT)
                logger.info(f"WORKER: QoS set to {PREFETCH_COUNT}")

                # Declare the queue ( idempotent - safe to call on startup)
                queue = await channel.declare_queue(RAW_DATA_QUEUE, durable=True)
                logger.info(f"WORKER: Queue '{RAW_DATA_QUEUE}' declared.")

                # Start consuming messages
                # Pass the async callback to queue.consume
                # store consumer_tag to allow cancellation
                consumer_tag = await queue.consume(process_message)
                logger.info(f"WORKER: Consumer started with tag '{consumer_tag}'. Waiting for messages...")

                # This future will complete if the connection is closed or an exception occurs
                await connection.channel(0).wait_closed() # Wait for the connection channel to close

            except (aio_pika.exceptions.AMQPConnectionError, ConnectionError, OSError) as e:
                logger.error(f"WORKER: Connection/AMQP error: {e}. Retrying connection in 5 seconds...", exc_info=True)
                # Close connection/channel if they exist but aren't closed robustly
                if channel and not channel.is_closed:
                    try: await channel.close()
                    except Exception: pass
                if connection and not connection.is_closed:
                    try: await connection.close()
                    except Exception: pass
                await asyncio.sleep(5) # Wait before next retry
            except asyncio.CancelledError:
                logger.info("WORKER: Task cancelled, likely during shutdown.")
                break # Exit retry loop on explicit cancellation
            except Exception as e:
                logger.error(f"WORKER: An unexpected error occurred in consumer loop: {e}", exc_info=True)
                # Decide if this kind of error warrants a retry or a full shutdown
                # For now, log and retry connection
                if channel and not channel.is_closed:
                    try: await channel.close()
                    except Exception: pass
                if connection and not connection.is_closed:
                    try: await connection.close()
                    except Exception: pass
                logger.info("WORKER: Restarting consumer loop after 10 seconds due to unexpected error...")
                await asyncio.sleep(10)

    finally:
         logger.info("WORKER: Exiting start_consuming loop.")
         # Attempt to close resources during final exit
         if channel and not channel.is_closed:
             try: await channel.close()
             except Exception as e: logger.error(f"Error closing channel in finally: {e}")
         if connection and not connection.is_closed:
             try: await connection.close()
             except Exception as e: logger.error(f"Error closing connection in finally: {e}")


async def main():
    """Main async function to start the consumer."""
    loop = asyncio.get_event_loop() # Use get_event_loop for compatibility, or get_running_loop if guaranteed context
    # Set up signal handlers for graceful shutdown
    stop_event = asyncio.Event()
    def signal_handler():
        logger.info("WORKER: Shutdown signal received (SIGINT/SIGTERM), setting stop event.")
        stop_event.set()
    try:
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
        logger.info("WORKER: Signal handlers added for SIGINT/SIGTERM.")
    except NotImplementedError:
        logger.warning("WORKER: Signal handlers not supported on this platform (e.g., Windows), graceful shutdown with CTRL+C might not work.")


    # Initialize the InfluxDB client synchronously before starting the consumer loop
    # This ensures it's ready when process_message is called.
    logger.info("WORKER: Initializing InfluxDB client (sync)...")
    db_client.initialize_influxdb_client()
    logger.info("WORKER: InfluxDB client initialization finished.")


    # Start the consuming task
    consumer_task = loop.create_task(start_consuming(loop))

    # Wait until stop_event is set or consumer task finishes (e.g., due to connection failure)
    logger.info("WORKER: Waiting for stop event or consumer task completion...")
    await asyncio.gather(consumer_task, stop_event.wait()) # Wait for either

    logger.info("WORKER: Stop event set or consumer task finished. Beginning shutdown...")

    # Consumer task might still be running, try to cancel it gracefully
    if not consumer_task.done():
        logger.info("WORKER: Cancelling consumer task...")
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            logger.info("WORKER: Consumer task cancelled successfully.")
        except Exception as e:
            logger.error(f"WORKER: Exception awaiting cancelled consumer task: {e}", exc_info=True)

    logger.info("WORKER: Async worker main function finished.")

if __name__ == "__main__":
    logger.info("Starting Async Air Quality Worker...")
    try:
        # asyncio.run() is suitable for top-level script execution
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("WORKER: KeyboardInterrupt caught in __main__.")
        # asyncio.run should handle signal, but this ensures message if it doesn't
    finally:
        logger.info("WORKER: Cleaning up resources...")
        # Close InfluxDB connection (still synchronous)
        db_client.close_influx_client()
        logger.info("WORKER: Async Air Quality Worker finished execution.")