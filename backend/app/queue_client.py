# backend/app/queue_client.py
import asyncio
import aio_pika
import logging
import json
from contextlib import asynccontextmanager, AbstractAsyncContextManager
from .config import get_settings
from typing import AsyncGenerator

logger = logging.getLogger(__name__)
settings = get_settings()

RAW_DATA_QUEUE = settings.rabbitmq_queue_raw
RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
POOL_MAX_SIZE = 15  # Max number of connections in the pool (tune as needed)
CONNECTION_TIMEOUT = 10 # Seconds to wait for acquiring a connection

class AioPikaConnectionPool:
    def __init__(self, url: str, max_size: int = 10):
        self._url = url
        self._max_size = max_size
        self._pool: asyncio.Queue[aio_pika.Connection] = asyncio.Queue(maxsize=max_size)
        self._connections_created = 0
        self._lock = asyncio.Lock() # To protect connections_created count

    async def _create_connection(self) -> aio_pika.Connection | None:
        """Creates a single robust connection."""
        try:
            connection = await aio_pika.connect_robust(self._url, timeout=15)
            logger.info(f"Successfully created a new aio-pika connection ({self._pool.qsize() + 1}/{self._max_size})")
            # Optional: Add close/reconnect callbacks if needed for monitoring
            # connection.add_close_callback(...)
            return connection
        except Exception as e:
            logger.error(f"Failed to create aio-pika connection: {e}", exc_info=True)
            return None

    async def initialize(self):
        """Fills the pool with initial connections."""
        async with self._lock:
            # Calculate how many connections to create initially
            to_create = self._max_size - self._pool.qsize() # Start by filling up
            if to_create <= 0 :
                return # Pool already full or oversized?

            logger.info(f"Initializing connection pool - creating up to {to_create} connections...")
            tasks = [self._create_connection() for _ in range(to_create)]
            results = await asyncio.gather(*tasks)
            for conn in results:
                if conn:
                    await self._pool.put(conn)
            logger.info(f"Connection pool initialized with {self._pool.qsize()} connections.")

    @asynccontextmanager

    async def acquire(self) -> AsyncGenerator[aio_pika.Connection, None]:
        """Acquires a connection from the pool, waits if pool is empty."""
        conn = None
        try:
            # Wait for a connection to become available
            logger.debug(f"Acquiring connection from pool (current size: {self._pool.qsize()})...")
            conn = await asyncio.wait_for(self._pool.get(), timeout=CONNECTION_TIMEOUT)
            logger.debug("Connection acquired from pool.")

            # Check if the connection is still alive, if not, try to replace it
            if conn.is_closed:
                logger.warning("Acquired a closed connection from pool. Attempting to replace...")
                self._pool.task_done() # Mark the bad one as processed
                async with self._lock: # Ensure only one replacement attempt at a time
                    # Try creating a new one if needed
                    new_conn = await self._create_connection()
                    if new_conn:
                        conn = new_conn # Use the new connection
                    else:
                        # Failed to replace, re-raise or handle error
                         raise ConnectionError("Failed to acquire a valid connection: replacement failed.")
            # Yield the valid connection
            yield conn

        except asyncio.TimeoutError:
            logger.error(f"Timeout ({CONNECTION_TIMEOUT}s) waiting for connection from pool.")
            raise ConnectionError(f"Timeout acquiring connection from pool (size: {self._pool.qsize()})")
        except Exception as e:
             logger.error(f"Error during connection acquisition: {e}", exc_info=True)
             # If we got a connection but failed before yielding, try to put it back? Or close it?
             # If an error happens within the 'with' block, 'finally' handles return.
             if conn:
                 # Decide: return potentially problematic conn or close it? Let's close it.
                 await self.close_connection(conn)
                 conn = None # Ensure it's not returned in finally
             raise # Re-raise the exception
        finally:
            if conn:
                # This block runs whether the 'yield' block succeeded or failed
                self._pool.task_done() # Signal that the acquired item processing is done
                if conn.is_closed:
                    logger.debug("Connection closed during use, not returning to pool.")
                    # Optional: Trigger a background task to replenish the pool?
                else:
                    try:
                        # Put the connection back into the queue
                        await self._pool.put(conn)
                        logger.debug("Connection returned to pool.")
                    except asyncio.QueueFull:
                         logger.warning("Failed to return connection to pool (pool full?), closing connection.")
                         await self.close_connection(conn)

    async def close_connection(self, conn: aio_pika.Connection):
        """Safely closes a single connection."""
        if conn and not conn.is_closed:
            try:
                await conn.close()
                logger.debug("Closed a single connection.")
            except Exception as e:
                logger.error(f"Error closing single connection: {e}", exc_info=True)

    async def close(self):
        """Closes all connections in the pool."""
        logger.info(f"Closing connection pool (size: {self._pool.qsize()})...")
        closed_count = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await self.close_connection(conn)
                closed_count += 1
                self._pool.task_done()
            except asyncio.QueueEmpty:
                break # Pool is empty
            except Exception as e:
                 logger.error(f"Error getting/closing connection during pool shutdown: {e}", exc_info=True)
                 # Mark task done even if closing failed to avoid hang
                 try: self._pool.task_done()
                 except ValueError: pass
        # Wait for all tasks to be marked done
        # await self._pool.join() # This might hang if tasks weren't done correctly
        logger.info(f"Connection pool closed. {closed_count} connections terminated.")


# --- Global Pool Instance ---
# Create the pool instance that will be used by the application
connection_pool = AioPikaConnectionPool(url=RABBITMQ_URL, max_size=POOL_MAX_SIZE)


# --- Publish Function (using the pool) ---
async def publish_message_async(message_body: dict):
    """Publishes a message asynchronously using the aio-pika connection pool."""
    retries = 2 # Number of attempts to acquire connection and publish
    last_exception = None

    for attempt in range(retries):
        try:
            # Acquire connection using the async context manager
            async with connection_pool.acquire() as connection:
                # Create a channel for this specific publish operation
                try:
                    channel = await connection.channel()
                    logger.debug(f"Channel created (id: {channel.number})")
                except Exception as channel_error:
                    logger.error(f"Failed to create channel on acquired connection: {channel_error}", exc_info=True)
                    last_exception = channel_error
                    continue # Try acquiring a new connection

                # Ensure queue exists (optional, but safer)
                try:
                     await channel.declare_queue(RAW_DATA_QUEUE, durable=True)
                except Exception as declare_error:
                     logger.error(f"Failed to declare queue '{RAW_DATA_QUEUE}' on channel {channel.number}: {declare_error}", exc_info=True)
                     last_exception = declare_error
                     await channel.close() # Close channel on error
                     continue # Try acquiring a new connection

                # Publish the message
                try:
                    message = aio_pika.Message(
                        body=json.dumps(message_body).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    )
                    await channel.default_exchange.publish(
                        message,
                        routing_key=RAW_DATA_QUEUE
                    )
                    logger.debug(f"Published async message via pool to queue '{RAW_DATA_QUEUE}' on channel {channel.number}")
                    await channel.close() # Close the channel after successful publish
                    return True # Success, exit function

                except Exception as publish_error:
                    logger.error(f"Error publishing async message on channel {channel.number}: {publish_error}", exc_info=True)
                    last_exception = publish_error
                    # Don't automatically close connection here, context manager handles return/close
                    await channel.close() # Close channel on error
                    # Fall through to retry logic below if connection itself is suspected

        except ConnectionError as conn_err: # Catch errors acquiring connection from pool
            logger.error(f"Attempt {attempt + 1}/{retries}: Failed to acquire connection: {conn_err}")
            last_exception = conn_err
        except Exception as e: # Catch other unexpected errors
             logger.error(f"Attempt {attempt + 1}/{retries}: Unexpected error during publish cycle: {e}", exc_info=True)
             last_exception = e

        # If we reached here, it means failure, wait before retrying
        if attempt < retries - 1:
            wait_time = 1 * (attempt + 1) # Simple backoff
            logger.info(f"Retrying publish in {wait_time}s...")
            await asyncio.sleep(wait_time)

    # If all retries failed
    logger.error(f"Failed to publish message after {retries} attempts. Last error: {last_exception}")
    return False

# --- Lifespan Integration Functions ---
async def initialize_rabbitmq_pool():
    """Called during FastAPI startup."""
    await connection_pool.initialize()

async def close_rabbitmq_pool():
    """Called during FastAPI shutdown."""
    await connection_pool.close()