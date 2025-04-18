# backend/app/worker.py
import pika
import json
import logging
import time
import sys
from datetime import datetime, timezone

# Configure logging early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# It's better to import modules after potential path setup if needed,
# but for simple structure this is usually fine.
try:
    from config import get_settings
    from models import AirQualityReading, IngestRequest # Use IngestRequest structure from queue
    import db_client
    import anomaly_detection
except ImportError as e:
     logger.error(f"Failed to import necessary modules. Ensure PYTHONPATH is correct or run from appropriate directory. Error: {e}")
     sys.exit(1) # Exit if imports fail


settings = get_settings()

def process_message(channel, method, properties, body):
    """Callback function to process a message from the queue."""
    logger.info(f"Received message with delivery tag {method.delivery_tag}")
    try:
        # Decode message body from bytes to string, then parse JSON
        message_str = body.decode('utf-8')
        data = json.loads(message_str)
        logger.debug(f"Message body: {data}")

        # Validate data against IngestRequest model (optional but good practice)
        try:
            ingest_data = IngestRequest(**data)
        except Exception as pydantic_error: # Catch Pydantic validation errors
            logger.error(f"Invalid message format received: {pydantic_error}. Discarding message: {message_str}", exc_info=True)
            # Acknowledge message so it's removed from queue
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Create the full AirQualityReading with current timestamp
        # Use timezone.utc for consistency
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
        logger.info(f"Processing reading for {reading.latitude},{reading.longitude} at {reading.timestamp}")

        # 1. Write data to InfluxDB
        write_success = db_client.write_air_quality_data(reading)
        if not write_success:
            # Decide on error handling: re-queue, dead-letter, or discard?
            # For now, log error and discard (by acknowledging)
            logger.error(f"Failed to write reading to InfluxDB for {reading.latitude},{reading.longitude}. Discarding message.")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2. Perform Anomaly Detection (Threshold check first)
        anomaly = anomaly_detection.check_thresholds(reading)

        # --- Add calls to other anomaly checks here later ---
        # if not anomaly:
        #     anomaly = anomaly_detection.check_percentage_increase(reading)
        # if not anomaly:
        #     anomaly = anomaly_detection.check_spatial_difference(reading)

        # 3. Write Anomaly if detected
        if anomaly:
            write_anomaly_success = db_client.write_anomaly_data(anomaly)
            if not write_anomaly_success:
                # Log error, but likely still ack the original message
                logger.error(f"Failed to write detected anomaly {anomaly.id} to InfluxDB.")
                # Decide if failure to write anomaly should prevent acking main message? Usually no.

        # 4. Acknowledge the message was processed successfully
        logger.info(f"Successfully processed message for {reading.latitude},{reading.longitude}. Acknowledging.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON message: {e}. Body: {body[:100]}... Discarding.", exc_info=True)
        channel.basic_ack(delivery_tag=method.delivery_tag) # Discard invalid JSON
    except Exception as e:
        logger.error(f"Unexpected error processing message: {e}. Delivery Tag: {method.delivery_tag}. Body: {body[:100]}...", exc_info=True)
        # Consider requeueing with basic_nack(delivery_tag=method.delivery_tag, requeue=True/False)
        # For now, discard to avoid infinite loops on persistent errors
        channel.basic_ack(delivery_tag=method.delivery_tag)


def start_consuming():
    """Connects to RabbitMQ and starts consuming messages."""
    while True: # Keep trying to connect
        connection = None
        try:
            logger.info("Attempting to connect worker to RabbitMQ...")
            credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_pass)
            parameters = pika.ConnectionParameters(
                host=settings.rabbitmq_host,
                port=settings.rabbitmq_port,
                credentials=credentials,
                heartbeat=600, # Keep connection alive
                blocked_connection_timeout=300
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            # Declare queue again (important for worker startup)
            channel.queue_declare(queue=settings.rabbitmq_queue_raw, durable=True)
            logger.info(f"Worker connected. Waiting for messages in queue '{settings.rabbitmq_queue_raw}'. To exit press CTRL+C")

            # Fair dispatch: Don't give more than one message to a worker at a time
            channel.basic_qos(prefetch_count=1)

            # Set up consumer
            channel.basic_consume(
                queue=settings.rabbitmq_queue_raw,
                on_message_callback=process_message
                # auto_ack=False by default - we ack manually in process_message
            )

            # Start consuming
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection failed: {e}. Retrying in 5 seconds...")
            if connection and connection.is_open:
                connection.close()
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker stopped manually.")
            if connection and connection.is_open:
                connection.close()
            break # Exit the while loop
        except Exception as e:
            logger.error(f"An unexpected error occurred in worker main loop: {e}", exc_info=True)
            if connection and connection.is_open:
                connection.close()
            logger.info("Restarting worker loop after 10 seconds...")
            time.sleep(10) # Wait before retrying on unexpected errors


if __name__ == "__main__":
    logger.info("Starting Air Quality Worker...")
    start_consuming()
    logger.info("Air Quality Worker finished.")
    # Ensure InfluxDB client is closed on worker shutdown
    db_client.close_influx_client()