# backend/app/queue_client.py
import asyncio
import aio_pika
import logging
import json
from contextlib import asynccontextmanager, AbstractAsyncContextManager
from .config import get_settings # Use get_settings() here
from typing import AsyncGenerator, Optional # Import Optional

logger = logging.getLogger(__name__)
settings = get_settings() # Get settings

RAW_DATA_QUEUE = settings.rabbitmq_queue_raw
RABBITMQ_URL = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_pass}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
POOL_MAX_SIZE = 15  # Max number of connections in the pool (tune as needed)
CONNECTION_TIMEOUT = 10 # Seconds to wait for acquiring a connection
CHANNEL_TIMEOUT = 5 # Seconds to wait for creating a channel

class AioPikaConnectionPool:
    def __init__(self, url: str, max_size: int = 10):
        self._url = url
        self._max_size = max_size
        # Use asyncio.LifoQueue for LIFO behavior - recently used connections are likely still warm
        self._pool: asyncio.Queue[aio_pika.Connection] = asyncio.LifoQueue(maxsize=max_size)
        self._connections_created = 0
        self._lock = asyncio.Lock() # To protect connections_created count/pool initialization

    async def _create_connection(self) -> Optional[aio_pika.Connection]:
        """Creates a single robust connection."""
        try:
            # Use a reasonable timeout for the initial connection attempt
            connection = await asyncio.wait_for(
                aio_pika.connect_robust(self._url, loop=asyncio.get_running_loop()),
                timeout=15 # Connection attempt timeout
            )
            logger.info(f"Successfully created a new aio-pika connection (pool size before put: {self._pool.qsize()})")
            # Optional: Add close/reconnect callbacks if needed for monitoring/replenishing
            # connection.add_close_callback(...)
            return connection
        except asyncio.TimeoutError:
             logger.error(f"Timeout creating aio-pika connection after 15s.")
             return None
        except Exception as e:
            logger.error(f"Failed to create aio-pika connection: {e}", exc_info=True)
            return None

    async def initialize(self):
        """Fills the pool with initial connections up to max_size."""
        async with self._lock:
            # Only initialize if pool is currently empty or needs filling
            current_size = self._pool.qsize()
            to_create = self._max_size - current_size
            if to_create <= 0 :
                logger.info(f"Connection pool already has {current_size} connections, no initial creation needed.")
                return # Pool already full or sufficient

            logger.info(f"Initializing connection pool - creating up to {to_create} connections...")
            # Create tasks for initial connections
            tasks = [self._create_connection() for _ in range(to_create)]
            results = await asyncio.gather(*tasks)
            successful_count = 0
            for conn in results:
                if conn:
                    await self._pool.put(conn)
                    successful_count += 1
            logger.info(f"Connection pool initialized. Successfully created {successful_count}/{to_create} connections. Pool size: {self._pool.qsize()}.")
            if successful_count == 0 and self._max_size > 0:
                 logger.error("Failed to create any initial connections for the RabbitMQ pool.")
                 # Depending on criticality, you might want to raise an exception here
                 # raise ConnectionError("Failed to initialize RabbitMQ connection pool")


    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[aio_pika.Connection, None]:
        """Acquires a connection from the pool, waits if pool is empty."""
        conn = None
        try:
            # Wait for a connection to become available
            logger.debug(f"Acquiring connection from pool (current size: {self._pool.qsize()})...")
            conn = await asyncio.wait_for(self._pool.get(), timeout=CONNECTION_TIMEOUT)
            logger.debug("Connection acquired from pool.")

            # Basic check: if the connection is closed, discard it and try to get/create another
            if conn.is_closed:
                logger.warning("Acquired a closed connection from pool. Discarding.")
                self._pool.task_done() # Mark the bad one as processed from the queue
                # Try acquiring again - this might get another existing good one or wait/timeout
                # Recursive call (be careful not to overflow stack on persistent failure)
                # Or, a better approach: try creating a replacement in the background?
                # For simplicity here, let's just raise and let the retry logic in publish handle it.
                raise ConnectionError("Acquired a closed connection from the pool.")

            # Yield the valid connection
            yield conn

        except asyncio.TimeoutError:
            logger.error(f"Timeout ({CONNECTION_TIMEOUT}s) waiting for connection from pool (size: {self._pool.qsize()}).")
            # If a connection was briefly acquired before timeout, it might be stuck.
            # The `_pool.get()` call is the one that times out, so `conn` should be None.
            # If `conn` is not None here, it means the timeout happened *inside* the `with` block,
            # which implies the yield block or finally block is taking too long.
            raise ConnectionError(f"Timeout acquiring connection from pool (size: {self._pool.qsize()})")
        except Exception as e:
             logger.error(f"Error during connection acquisition: {e}", exc_info=True)
             # If conn is not None here, it means an error occurred *after* acquiring but *before* finally
             if conn and not conn.is_closed:
                  # If the connection is still usable, try returning it.
                  # If the error is fatal to the connection, let finally try closing it.
                  pass # Let finally block handle putting back or closing

             raise # Re-raise the exception
        finally:
            # This block runs whether the 'yield' block succeeded or failed or an exception occurred *before* yield
            if conn and not conn.is_closed:
                try:
                    # Attempt to return the connection to the pool only if it's still open
                    # Use put_nowait if pool might become full, otherwise put might block forever
                    self._pool.put_nowait(conn) # Put back immediately
                    logger.debug("Connection returned to pool.")
                except asyncio.QueueFull:
                     logger.warning("Failed to return connection to pool (pool full?), closing connection.")
                     # If pool is full, close the connection rather than leaking it or blocking put.
                     await self.close_connection(conn)
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}", exc_info=True)
                    # If returning fails, try closing it
                    await self.close_connection(conn)
            elif conn: # If conn was acquired but was closed
                 logger.debug("Acquired connection was closed, not returning to pool.")
                 # No need to call close_connection if is_closed is true
            # Always mark task done for the item taken from the queue
            try:
                 self._pool.task_done()
            except ValueError:
                 # This happens if task_done is called without a corresponding get_nowait/get
                 # (e.g., if an exception occurred before _pool.get() completed)
                 pass # Ignore, it's likely fine


    async def close_connection(self, conn: Optional[aio_pika.Connection]):
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
        # Get all connections out of the queue
        connections_to_close = []
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                connections_to_close.append(conn)
                self._pool.task_done() # Mark as processed
            except asyncio.QueueEmpty:
                break # Pool is empty
            except Exception as e:
                 logger.error(f"Error getting connection from pool during shutdown: {e}", exc_info=True)
                 try: self._pool.task_done() # Still try to mark done
                 except ValueError: pass

        # Now close them all
        tasks = [self.close_connection(conn) for conn in connections_to_close]
        await asyncio.gather(*tasks, return_exceptions=True) # Close concurrently
        closed_count = len([t for t in tasks if not isinstance(t, Exception)]) # Count successful closes

        # Ensure any tasks waiting on the queue are cancelled
        # await self._pool.join() # This waits for *all* tasks ever taken to be done. Might hang.
        logger.info(f"Connection pool closed. {closed_count} connections terminated.")


# --- Global Pool Instance ---
# Create the pool instance that will be used by the application
# It will be initialized during the FastAPI lifespan startup event
connection_pool: Optional[AioPikaConnectionPool] = None


# --- Lifespan Integration Functions ---
async def initialize_rabbitmq_pool():
    """Called during FastAPI startup to initialize the global connection pool."""
    global connection_pool
    if connection_pool is None:
        logger.info("Initializing RabbitMQ connection pool...")
        connection_pool = AioPikaConnectionPool(url=RABBITMQ_URL, max_size=POOL_MAX_SIZE)
        await connection_pool.initialize()
    else:
        logger.info("RabbitMQ connection pool already initialized.")


async def close_rabbitmq_pool():
    """Called during FastAPI shutdown to close the global connection pool."""
    global connection_pool
    if connection_pool:
        logger.info("Closing RabbitMQ connection pool...")
        await connection_pool.close()
        connection_pool = None # Dereference the pool instance


# --- Publish Function (using the pool) ---
async def publish_message_async(message_body: dict):
    """Publishes a message asynchronously using the aio-pika connection pool."""
    if connection_pool is None:
         logger.error("RabbitMQ connection pool is not initialized.")
         return False

    retries = 3 # Number of attempts to acquire connection/channel and publish
    last_exception: Optional[Exception] = None

    for attempt in range(retries):
        try:
            # Acquire connection using the async context manager from the pool
            async with connection_pool.acquire() as connection:
                logger.debug(f"Attempt {attempt + 1}/{retries}: Connection acquired.")
                # Create a channel for this specific publish operation
                # Channels are not thread-safe but can be reused per async task.
                # Creating a new one per publish ensures isolation.
                try:
                    channel = await asyncio.wait_for(connection.channel(), timeout=CHANNEL_TIMEOUT)
                    logger.debug(f"Attempt {attempt + 1}/{retries}: Channel created (id: {channel.number})")
                except asyncio.TimeoutError:
                     logger.error(f"Attempt {attempt + 1}/{retries}: Timeout creating channel after {CHANNEL_TIMEOUT}s.")
                     last_exception = asyncio.TimeoutError(f"Channel creation timeout after {CHANNEL_TIMEOUT}s")
                     # Continue to next retry attempt, acquire() will try a different connection
                     continue
                except Exception as channel_error:
                    logger.error(f"Attempt {attempt + 1}/{retries}: Failed to create channel on acquired connection: {channel_error}", exc_info=True)
                    last_exception = channel_error
                    # Continue to next retry attempt, acquire() will try a different connection
                    continue

                # Ensure queue exists (optional, but safer on first run or if worker isn't running)
                # This is a blocking network call within the channel scope.
                try:
                     await channel.declare_queue(RAW_DATA_QUEUE, durable=True)
                     logger.debug(f"Attempt {attempt + 1}/{retries}: Queue '{RAW_DATA_QUEUE}' declared.")
                except Exception as declare_error:
                     logger.error(f"Attempt {attempt + 1}/{retries}: Failed to declare queue '{RAW_DATA_QUEUE}' on channel {channel.number}: {declare_error}", exc_info=True)
                     last_exception = declare_error
                     await channel.close() # Close channel on error
                     continue # Try acquiring a new connection/channel

                # Publish the message
                try:
                    message = aio_pika.Message(
                        body=json.dumps(message_body).encode('utf-8'), # Ensure UTF-8 encoding
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT # Make message durable
                    )
                    # Use default exchange to publish to the queue by routing key matching queue name
                    await channel.default_exchange.publish(
                        message,
                        routing_key=RAW_DATA_QUEUE,
                        # Optional: add a timeout for the publish operation itself if supported/needed
                        # timeout=5 # Example: 5 seconds for publish confirmation
                    )
                    logger.debug(f"Attempt {attempt + 1}/{retries}: Published message via pool to queue '{RAW_DATA_QUEUE}' on channel {channel.number}")
                    await channel.close() # Close the channel after successful publish (channels are cheap to create/close)
                    logger.debug(f"Attempt {attempt + 1}/{retries}: Channel {channel.number} closed after publish.")
                    return True # Success, exit function

                except Exception as publish_error:
                    logger.error(f"Attempt {attempt + 1}/{retries}: Error publishing message on channel {channel.number}: {publish_error}", exc_info=True)
                    last_exception = publish_error
                    # Don't automatically close connection here, acquire context manager handles return/close
                    # Close the specific channel that failed
                    if channel and not channel.is_closed:
                        try: await channel.close()
                        except Exception as ce: logger.error(f"Error closing channel {channel.number} after publish error: {ce}")
                    # Fall through to retry logic below if connection itself is suspected

        except ConnectionError as conn_err: # Catch errors acquiring connection from pool (including timeout)
            logger.error(f"Attempt {attempt + 1}/{retries}: Failed to acquire or use connection from pool: {conn_err}")
            last_exception = conn_err
            # The `acquire` context manager should handle cleaning up the specific connection it failed on.
        except Exception as e: # Catch other unexpected errors
             logger.error(f"Attempt {attempt + 1}/{retries}: Unexpected error during publish cycle: {e}", exc_info=True)
             last_exception = e
             # No specific cleanup needed here, rely on context managers/finally blocks

        # If we reached here, it means failure, wait before retrying
        if attempt < retries - 1:
            wait_time = 0.5 * (attempt + 1) # Simple backoff: 0.5s, 1s, 1.5s...
            logger.info(f"Publish failed, retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)

    # If all retries failed
    logger.error(f"Failed to publish message after {retries} attempts. Last error: {last_exception}")
    return False