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
    from .config import get_settings # Use .config
    from .models import AirQualityReading, IngestRequest # Use .models
    from . import db_client # Use relative import
    from . import anomaly_detection # Use relative import
except ImportError as e:
     logger.error(f"Failed to import necessary modules. Ensure PYTHONPATH is correct or run from appropriate directory. Error: {e}")
     sys.exit(1) # Exit if imports fail


settings = get_settings()

def process_message(channel, method, properties, body):
    """Callback function to process a message from the queue."""
    # --- START DEBUGGING ---
    logger.info(f"Received message with delivery tag {method.delivery_tag}. Body type: {type(body)}")
    # Log first few bytes to check content
    try:
        logger.debug(f"Raw message body (first 100 bytes): {body[:100]}")
    except Exception as log_err:
        logger.error(f"Error logging raw message body: {log_err}")

    message_str = None # Initialize variable
    data = None        # Initialize variable
    # --- END DEBUGGING ---

    try:
        # --- Step 1: Decode ---
        logger.debug("Attempting to decode message body (utf-8)...")
        try:
            message_str = body.decode('utf-8')
            logger.debug(f"Successfully decoded body.")
        except UnicodeDecodeError as decode_error:
             logger.error(f"UnicodeDecodeError decoding message body: {decode_error}. Body (repr): {body!r}. Discarding message.", exc_info=True)
             channel.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge invalid message
             return # Stop processing this message
        except Exception as decode_err: # Catch other potential decoding errors
             logger.error(f"Unexpected error decoding message body: {decode_err}. Body (repr): {body!r}. Discarding message.", exc_info=True)
             channel.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge invalid message
             return # Stop processing this message

        # --- Step 2: Parse JSON ---
        logger.debug("Attempting to parse JSON...")
        try:
            data = json.loads(message_str)
            logger.debug(f"Successfully parsed JSON. Data: {data}")
        except json.JSONDecodeError as json_error:
            logger.error(f"JSONDecodeError parsing message: {json_error}. String was: '{message_str}'. Discarding message.", exc_info=True)
            channel.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge invalid JSON
            return # Stop processing this message
        except Exception as json_err: # Catch other potential JSON errors
            logger.error(f"Unexpected error parsing JSON: {json_err}. String was: '{message_str}'. Discarding message.", exc_info=True)
            channel.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge invalid JSON
            return # Stop processing this message

        # --- Step 3: Validate with Pydantic (moved validation here) ---
        logger.debug("Attempting to validate data with Pydantic model IngestRequest...")
        try:
            ingest_data = IngestRequest(**data)
            logger.debug("Pydantic validation successful.")
        except Exception as pydantic_error: # Catch Pydantic validation errors more broadly
            logger.error(f"Pydantic validation failed for data: {data}. Error: {pydantic_error}. Discarding message.", exc_info=True)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        # --- Step 4: Process Validated Data ---
        # Now we are confident we have valid ingest_data
        logger.info(f"Processing reading for {ingest_data.latitude},{ingest_data.longitude}...") # MOVED log statement

        # Create the full AirQualityReading with current timestamp
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
        logger.info(f"Constructed AirQualityReading object for {reading.latitude},{reading.longitude} at {reading.timestamp}") # Added detailed log

        # 4.1. Write data to InfluxDB
        logger.debug("Attempting to write reading to InfluxDB...")
        write_success = db_client.write_air_quality_data(reading)
        if not write_success:
            logger.error(f"Failed to write reading to InfluxDB for {reading.latitude},{reading.longitude}. Discarding message.")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        logger.debug("Successfully wrote reading to InfluxDB.")

        # 4.2. Perform Anomaly Detection
        logger.debug("Checking for anomalies...")
        anomaly = anomaly_detection.check_thresholds(reading)
        if anomaly:
            logger.debug(f"Anomaly detected: {anomaly.description}")
            # 4.3. Write Anomaly if detected
            logger.debug("Attempting to write anomaly to InfluxDB...")
            write_anomaly_success = db_client.write_anomaly_data(anomaly)
            if not write_anomaly_success:
                logger.error(f"Failed to write detected anomaly {anomaly.id} to InfluxDB.")
            else:
                logger.debug("Successfully wrote anomaly to InfluxDB.")
        else:
            logger.debug("No threshold anomalies detected.")

        # 4.4. Acknowledge the message was processed successfully
        logger.info(f"Successfully processed message for {reading.latitude},{reading.longitude}. Acknowledging delivery tag {method.delivery_tag}.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        # Generic catch-all for unexpected errors during the main processing steps
        logger.error(f"Unexpected error in process_message after initial parsing. Error: {e}. Delivery Tag: {method.delivery_tag}. Data (if available): {data}. Discarding message.", exc_info=True)
        # Acknowledge the message to prevent requeue loops if the error is persistent
        try:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as ack_err:
             logger.error(f"Failed to acknowledge message after error: {ack_err}")

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