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

# Use relative imports as configured before
try:
    from .config import get_settings
    from .models import AirQualityReading, IngestRequest, Anomaly
    from . import db_client # Keep sync DB client for now
    from . import anomaly_detection # Keep sync anomaly detection
except ImportError as e:
     logger.error(f"Failed to import necessary modules. Ensure structure is correct. Error: {e}")
     sys.exit(1)

settings = get_settings()
RAW_DATA_QUEUE = settings.rabbitmq_queue_raw
RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
PREFETCH_COUNT = 10 # How many messages the worker can process concurrently (tune as needed)

async def process_message(message: aio_pika.IncomingMessage):
    """Async callback function to process a message from the queue."""
    async with message.process(requeue=False, ignore_processed=True): # Context manager handles ack/nack based on exceptions
        logger.info(f"WORKER: Received message. Routing key: {message.routing_key}, Delivery tag: {message.delivery_tag}")
        data = None
        try:
            # 1. Decode body
            logger.debug("WORKER: Attempting to decode message body...")
            body_str = message.body.decode('utf-8')
            logger.debug("WORKER: Body decoded.")

            # 2. Parse JSON
            logger.debug("WORKER: Attempting to parse JSON...")
            data = json.loads(body_str)
            logger.debug(f"WORKER: JSON parsed. Data: {data}")

            # 3. Validate with Pydantic
            logger.debug("WORKER: Attempting Pydantic validation...")
            try:
                ingest_data = IngestRequest(**data)
                logger.debug("WORKER: Pydantic validation successful.")
            except Exception as pydantic_error:
                logger.error(f"WORKER: Pydantic validation failed for data: {data}. Error: {pydantic_error}. Discarding (NACKing) message.", exc_info=True)
                # No need to explicitly NACK, context manager does it on exception
                # await message.nack(requeue=False) # Requeue=False to discard
                return # Stop processing

            # 4. Process Validated Data
            logger.info(f"WORKER: Processing reading for {ingest_data.latitude},{ingest_data.longitude}...")
            current_time_utc = datetime.now(timezone.utc)
            reading = AirQualityReading(
                latitude=ingest_data.latitude,
                longitude=ingest_data.longitude,
                timestamp=current_time_utc,
                pm25=ingest_data.pm25,
                pm10=ingest_data.pm10,
                no2=ingest_data.no2,
                so2=ingest_data.so2,
                o3=ingest_data.o3
            )
            logger.info(f"WORKER: Constructed AirQualityReading object for {reading.latitude},{reading.longitude} at {reading.timestamp}")

            # --- Synchronous DB/Anomaly Logic ---
            # NOTE: These are blocking calls within an async function.
            # For peak performance, these should ideally become async calls
            # using an async DB client and potentially running checks concurrently.
            # However, this structure works and unblocks the RabbitMQ consumption part.

            # 4.1. Write data to InfluxDB (Sync call)
            logger.debug("WORKER: Attempting sync write to InfluxDB...")
            # Potential improvement: Run sync code in an executor
            # loop = asyncio.get_running_loop()
            # write_success = await loop.run_in_executor(None, db_client.write_air_quality_data, reading)
            write_success = db_client.write_air_quality_data(reading) # Direct sync call
            if not write_success:
                logger.error(f"WORKER: Failed sync write to InfluxDB for {reading.latitude},{reading.longitude}. Discarding (NACKing).")
                # await message.nack(requeue=False)
                return # Stop processing
            logger.debug("WORKER: Sync write to InfluxDB successful.")

            # 4.2. Perform Anomaly Detection (Sync call)
            logger.debug("WORKER: Checking sync for anomalies...")
            anomaly = anomaly_detection.check_thresholds(reading)
            if anomaly:
                logger.info(f"WORKER: Anomaly detected (sync check): {anomaly.description}") # Changed level to INFO
                # 4.3. Write Anomaly if detected (Sync call)
                logger.debug("WORKER: Attempting sync anomaly write...")
                write_anomaly_success = db_client.write_anomaly_data(anomaly)
                if not write_anomaly_success:
                    logger.error(f"WORKER: Failed sync write for detected anomaly {anomaly.id}.")
                    # Continue processing original message even if anomaly write fails
                else:
                     logger.debug("WORKER: Sync anomaly write successful.")
            else:
                logger.debug("WORKER: No threshold anomalies detected (sync check).")

            # --- End Synchronous Block ---

            # If we reach here without exceptions, the context manager will ACK the message.
            logger.info(f"WORKER: Successfully processed message for {reading.latitude},{reading.longitude}. (Delivery tag: {message.delivery_tag}) - Message will be ACKed.")

        except json.JSONDecodeError:
            logger.error(f"WORKER: JSONDecodeError. Body (start): {message.body[:100]}... Discarding (NACKing).", exc_info=True)
            # await message.nack(requeue=False)
        except UnicodeDecodeError:
            logger.error(f"WORKER: UnicodeDecodeError. Body (repr): {message.body!r}. Discarding (NACKing).", exc_info=True)
            # await message.nack(requeue=False)
        except Exception as e:
            # Catch-all for unexpected errors during processing
            logger.error(f"WORKER: Unexpected error processing message: {e}. Data (if parsed): {data}. Discarding (NACKing).", exc_info=True)
            # await message.nack(requeue=False) # Discard on unknown errors to prevent loops


async def start_consuming(loop):
    """Connects to RabbitMQ and starts consuming messages asynchronously."""
    connection = None
    while True: # Keep trying to connect
        try:
            logger.info("WORKER: Attempting async connection to RabbitMQ...")
            connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop, timeout=15)
            logger.info("WORKER: Async connection established.")

            # Creating a channel
            channel = await connection.channel()
            logger.info("WORKER: Channel created.")

            # Set Quality of Service
            await channel.set_qos(prefetch_count=PREFETCH_COUNT)
            logger.info(f"WORKER: QoS set to {PREFETCH_COUNT}")

            # Declare the queue
            queue = await channel.declare_queue(RAW_DATA_QUEUE, durable=True)
            logger.info(f"WORKER: Queue '{RAW_DATA_QUEUE}' declared. Waiting for messages...")

            # Start consuming messages
            await queue.consume(process_message) # Pass the async callback

            # Keep consuming indefinitely until connection breaks or shutdown signal
            # Adding a future that completes on shutdown signal
            stop_event = asyncio.Event()
            loop.add_signal_handler(signal.SIGINT, stop_event.set)
            loop.add_signal_handler(signal.SIGTERM, stop_event.set)
            logger.info("WORKER: Consumer started. Press CTRL+C to exit.")
            await stop_event.wait() # Wait until SIGINT/SIGTERM

            # Graceful shutdown requested
            logger.info("WORKER: Shutdown signal received, stopping consumer...")
            break # Exit the while loop

        except (aio_pika.exceptions.AMQPConnectionError, ConnectionError, OSError) as e:
            logger.error(f"WORKER: Connection/AMQP error: {e}. Retrying in 5 seconds...", exc_info=True)
            if connection and not connection.is_closed:
                await connection.close()
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("WORKER: Task cancelled, likely during shutdown.")
            break
        except Exception as e:
            logger.error(f"WORKER: An unexpected error occurred in consumer loop: {e}", exc_info=True)
            if connection and not connection.is_closed:
                await connection.close()
            logger.info("WORKER: Restarting consumer loop after 10 seconds...")
            await asyncio.sleep(10)
        finally:
             if connection and not connection.is_closed:
                 logger.info("WORKER: Closing connection in finally block.")
                 await connection.close()


async def main():
    """Main async function to start the consumer."""
    loop = asyncio.get_running_loop()
    consumer_task = loop.create_task(start_consuming(loop))
    await consumer_task # Wait for the consumer task to finish (e.g., on shutdown)

if __name__ == "__main__":
    logger.info("Starting Async Air Quality Worker...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("WORKER: KeyboardInterrupt received in main.")
    finally:
        logger.info("WORKER: Cleaning up resources...")
        # Close InfluxDB connection (still synchronous)
        db_client.close_influx_client()
        logger.info("WORKER: Async Air Quality Worker finished.")