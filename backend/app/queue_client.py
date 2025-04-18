import pika
import logging
import json
import threading
import time
from queue import Queue, Empty
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

RAW_DATA_QUEUE = settings.rabbitmq_queue_raw

# Pool settings
POOL_SIZE = 5
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2  # seconds

class RabbitMQConnectionPool:
    def __init__(self, size):
        self.size = size
        self.pool = Queue(maxsize=size)
        self.lock = threading.Lock()
        for _ in range(size):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)

    def _create_connection(self):
        credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_pass)
        parameters = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            credentials=credentials
        )
        try:
            connection = pika.BlockingConnection(parameters)
            logger.info(f"RabbitMQ connection established to {settings.rabbitmq_host}:{settings.rabbitmq_port}")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}", exc_info=True)
            return None

    def get_connection(self):
        try:
            conn = self.pool.get(timeout=5)
            if not conn or conn.is_closed:
                conn = self._create_connection()
            return conn
        except Empty:
            logger.error("No RabbitMQ connections available in pool.")
            return None

    def return_connection(self, conn):
        if conn and conn.is_open:
            try:
                self.pool.put_nowait(conn)
            except Exception:
                conn.close()
        else:
            if conn:
                conn.close()

    def close_all(self):
        while not self.pool.empty():
            conn = self.pool.get_nowait()
            if conn and conn.is_open:
                conn.close()

# Initialize pool
connection_pool = RabbitMQConnectionPool(POOL_SIZE)

def publish_message(message_body: dict):
    """Publishes a message to the raw data queue with retry and pooling."""
    for attempt in range(RETRY_ATTEMPTS):
        conn = connection_pool.get_connection()
        if not conn:
            time.sleep(RETRY_DELAY)
            continue
        try:
            channel = conn.channel()
            channel.queue_declare(queue=RAW_DATA_QUEUE, durable=True)
            channel.basic_publish(
                exchange='',
                routing_key=RAW_DATA_QUEUE,
                body=json.dumps(message_body),
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                )
            )
            logger.debug(f"Published message to queue '{RAW_DATA_QUEUE}': {message_body}")
            connection_pool.return_connection(conn)
            return True
        except Exception as e:
            logger.error(f"Error publishing message to RabbitMQ: {e}", exc_info=True)
            if conn and conn.is_open:
                conn.close()
            time.sleep(RETRY_DELAY)
    return False