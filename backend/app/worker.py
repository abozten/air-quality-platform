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
    # Remove direct import of websocket_manager, worker no longer broadcasts directly
    # from . import websocket_manager
    # Import the specific publish function needed
    from .queue_client import publish_broadcast_message_async, connection_pool, initialize_rabbitmq_pool, close_rabbitmq_pool
except ImportError as e:
     logger.error(f"Failed to import necessary modules. Ensure structure is correct. Error: {e}")
     sys.exit(1)

settings = get_settings()
RAW_DATA_QUEUE = settings.rabbitmq_queue_raw
RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
PREFETCH_COUNT = 10 # How many messages the worker can process concurrently (tune as needed)

async def process_message(message: aio_pika.IncomingMessage):
    """Async callback function to process a message from the queue."""
    # Get the current running loop to schedule executor tasks
    loop = asyncio.get_running_loop()
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
                # Context manager handles NACK on exception
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

            # --- Execute Blocking DB/Anomaly Logic in Thread Pool Executor ---

            # 4.1. Write data to InfluxDB (Offloaded)
            logger.debug("WORKER: Attempting non-blocking write to InfluxDB...")
            write_success = await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                db_client.write_air_quality_data,
                reading
            )
            if not write_success:
                # Log the error, but context manager will NACK automatically on exit if needed
                logger.error(f"WORKER: Failed write to InfluxDB for {reading.latitude},{reading.longitude}. Discarding (NACKing).")
                # We still raise an exception here to ensure the context manager NACKs
                raise IOError("Failed to write data to InfluxDB")
            logger.debug("WORKER: Write to InfluxDB successful (offloaded).")

            # 4.2. Perform Anomaly Detection (Offloaded)
            logger.debug("WORKER: Checking non-blocking for anomalies...")
            anomaly = await loop.run_in_executor(
                None,
                anomaly_detection.check_thresholds,
                reading
            )
            if anomaly:
                logger.info(f"WORKER: Anomaly detected (non-blocking check): {anomaly.description}") # Changed level to INFO
                # 4.3. Write Anomaly if detected (Offloaded)
                logger.debug("WORKER: Attempting non-blocking anomaly write...")
                write_anomaly_success = await loop.run_in_executor(
                    None,
                    db_client.write_anomaly_data,
                    anomaly
                )
                if not write_anomaly_success:
                    # Log error but don't fail the original message processing just for this
                    logger.error(f"WORKER: Failed write for detected anomaly {anomaly.id} (non-blocking).")
                else:
                    logger.debug("WORKER: Non-blocking anomaly write successful.")

                # 4.4. Publish anomaly to RabbitMQ Fanout Exchange for broadcasting
                logger.debug("WORKER: Publishing anomaly to broadcast exchange...")
                try:
                    # Use the new publish function for the fanout exchange
                    broadcast_success = await publish_broadcast_message_async(anomaly.model_dump(mode='json'))
                    if broadcast_success:
                        logger.info(f"WORKER: Anomaly {anomaly.id} published to broadcast exchange successfully.")
                    else:
                        # Log error but don't fail processing just for broadcast failure
                        logger.error(f"WORKER: Failed to publish anomaly {anomaly.id} to broadcast exchange.")
                except Exception as pub_error:
                    logger.error(f"WORKER: Error publishing anomaly {anomaly.id} to broadcast exchange: {pub_error}", exc_info=True)
            else:
                logger.debug("WORKER: No threshold anomalies detected (non-blocking check).")

            # --- End Offloaded Block ---

            # If we reach here without exceptions, the context manager will ACK the message.
            logger.info(f"WORKER: Successfully processed message for {reading.latitude},{reading.longitude}. (Delivery tag: {message.delivery_tag}) - Message will be ACKed.")

        except json.JSONDecodeError:
            logger.error(f"WORKER: JSONDecodeError. Body (start): {message.body[:100]}... Discarding (NACKing).", exc_info=True)
            # Context manager handles NACK
        except UnicodeDecodeError:
            logger.error(f"WORKER: UnicodeDecodeError. Body (repr): {message.body!r}. Discarding (NACKing).", exc_info=True)
            # Context manager handles NACK
        except Exception as e:
            # Catch-all for unexpected errors during processing, including the IOError raised above
            logger.error(f"WORKER: Unexpected error processing message: {e}. Data (if parsed): {data}. Discarding (NACKing).", exc_info=True)
            # Context manager handles NACK


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
            logger.error(f"WORKER: Connection/AMQP error: {e}. Retrying in 5 seconds...", exc_info=False) # Reduced noise for common errors
            if connection and not connection.is_closed:
                 try: await connection.close()
                 except Exception: pass # Ignore errors during close on error path
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("WORKER: Task cancelled, likely during shutdown.")
            break
        except Exception as e:
            logger.error(f"WORKER: An unexpected error occurred in consumer loop: {e}", exc_info=True)
            if connection and not connection.is_closed:
                 try: await connection.close()
                 except Exception: pass
            logger.info("WORKER: Restarting consumer loop after 10 seconds...")
            await asyncio.sleep(10)
        finally:
             if connection and not connection.is_closed:
                 logger.info("WORKER: Closing connection in finally block.")
                 await connection.close()


async def main():
    """Main async function to start the consumer."""
    logger.info("WORKER: Initializing RabbitMQ connection pool...")
    await initialize_rabbitmq_pool() # Initialize the pool for the worker
    logger.info("WORKER: RabbitMQ connection pool initialized.")

    loop = asyncio.get_running_loop()
    consumer_task = loop.create_task(start_consuming(loop))

    # Handle graceful shutdown for the main task as well
    stop_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    # Create a task for the stop event wait coroutine
    stop_wait_task = asyncio.create_task(stop_event.wait())

    # Wait for either the consumer task to finish naturally (unlikely)
    # or for the shutdown signal to be received
    done, pending = await asyncio.wait(
        [consumer_task, stop_wait_task], # Pass tasks, not coroutines
        return_when=asyncio.FIRST_COMPLETED
    )

    # If the stop event finished first, cancel the consumer task
    if stop_wait_task in done: # Check if the stop task completed
        logger.info("WORKER: Main loop received shutdown signal, cancelling consumer task...")
        consumer_task.cancel()
        # Wait for the consumer task to actually cancel
        await asyncio.gather(consumer_task, return_exceptions=True)
    # Clean up the stop_wait_task if it's still pending (consumer_task finished first)
    elif stop_wait_task in pending:
        stop_wait_task.cancel()
        await asyncio.gather(stop_wait_task, return_exceptions=True)

if __name__ == "__main__":
    logger.info("Starting Async Air Quality Worker...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("WORKER: KeyboardInterrupt received in main.")
    finally:
        logger.info("WORKER: Cleaning up resources...")
        # Close RabbitMQ pool connections
        logger.info("WORKER: Closing RabbitMQ connection pool...")
        # Run the async close function in a new event loop if the main one is stopped
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.run_until_complete(close_rabbitmq_pool())
            else:
                asyncio.run(close_rabbitmq_pool())
            logger.info("WORKER: RabbitMQ connection pool closed.")
        except Exception as e:
            logger.error(f"WORKER: Error closing RabbitMQ pool: {e}", exc_info=True)

        # Close InfluxDB connection (still synchronous, called after event loop stops)
        db_client.close_influx_client()
        logger.info("WORKER: Async Air Quality Worker finished.")