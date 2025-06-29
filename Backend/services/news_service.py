"""
Service for handling messages from Redis with SSE support.
Handles both standard and critical messages.
"""

from __future__ import annotations

import logging, asyncio, time, orjson
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Callable, Awaitable
import redis.asyncio as redis
from redis.asyncio.connection import BlockingConnectionPool, ConnectionPool

from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class NewsService:
    """Service for storing and managing messages in Redis with SSE support."""

    _instance = None
    _initialized = False

    # Redis async connection pool
    _redis_pool: Optional[ConnectionPool] = None
    _redis_client: Optional[redis.Redis] = None

    # SSE subscribers (separate for standard and critical)
    _standard_subscribers: Set[Callable[[str], Awaitable[None]]] = set()
    _critical_subscribers: Set[Callable[[str], Awaitable[None]]] = set()
    _sse_lock = asyncio.Lock()

    # Last critical message cache
    _last_critical_message: Optional[Dict[str, Any]] = None
    _last_critical_timestamp: Optional[float] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NewsService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        logger.info("Initializing NewsService with Redis...")
        self._initialized = True
        logger.info("NewsService initialized.")

    async def _ensure_redis_initialized(self) -> None:
        """Ensure Redis is initialized."""
        if self._redis_client is None:
            await self._initialize_redis()

    async def _initialize_redis(self) -> None:
        """Initialize asynchronous Redis connection."""
        try:
            settings = get_settings()

            pool_cls = BlockingConnectionPool

            if settings.REDIS_URL:
                logger.info(f"Connecting to Redis using URL: {settings.REDIS_URL}")
                self._redis_pool = pool_cls.from_url(
                    settings.REDIS_URL,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    timeout=settings.REDIS_POOL_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    retry_on_timeout=True,
                    decode_responses=True,
                )
            else:
                logger.info(
                    f"Connecting to Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}, DB: {settings.REDIS_DB}"
                )
                self._redis_pool = pool_cls(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    timeout=settings.REDIS_POOL_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    retry_on_timeout=True,
                    decode_responses=True,
                )

            self._redis_client = redis.Redis(connection_pool=self._redis_pool)
            await self._redis_client.ping()
            logger.info("Successfully connected to Redis and tested connection.")

        except Exception as e:
            logger.critical(f"Cannot initialize Redis connection: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Redis connection: {e}") from e

    async def _get_redis_client(self) -> redis.Redis:
        """Returns Redis client with error handling."""
        await self._ensure_redis_initialized()
        if not self._redis_client:
            raise RuntimeError("Redis client not initialized")
        return self._redis_client

    async def add_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchronous method to add new standard message to Redis and notify subscribers."""
        # Validation
        if not all(key in message for key in ["news_id", "title", "time_reported"]):
            logger.warning(f"Received incomplete message: {message}")
            return

        # Ensure narrative_impact exists (for compatibility)
        if (
            "analysis_payload" in message
            and "knowledge_graph_data" in message["analysis_payload"]
        ):
            if (
                "narrative_impact"
                not in message["analysis_payload"]["knowledge_graph_data"]
            ):
                message["analysis_payload"]["knowledge_graph_data"][
                    "narrative_impact"
                ] = "Unknown"

        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()

            # Add timestamp for sorting
            try:
                if message.get("time_reported"):
                    if isinstance(message["time_reported"], str):
                        try:
                            dt = datetime.fromisoformat(
                                message["time_reported"].replace("Z", "+00:00")
                            )
                            score = dt.timestamp()
                        except (ValueError, TypeError):
                            score = time.time()
                    else:
                        score = float(message["time_reported"])
                else:
                    score = time.time()
            except Exception:
                score = time.time()

            # Serialize message to JSON
            message_json = orjson.dumps(message, default=str).decode()

            # Add to sorted set in Redis
            await redis_client.zadd(settings.NEWS_REDIS_KEY, {message_json: score})

            # Limit number of messages
            total_messages = await redis_client.zcard(settings.NEWS_REDIS_KEY)
            if total_messages > settings.NEWS_MAX_MESSAGES:
                excess_count = total_messages - settings.NEWS_MAX_MESSAGES
                await redis_client.zremrangebyrank(
                    settings.NEWS_REDIS_KEY, 0, excess_count - 1
                )

            logger.info(
                f"Added new standard message to Redis: {message['news_id']} - {message['title']}"
            )

        except Exception as e:
            logger.error(f"Error adding message to Redis: {e}", exc_info=True)
            return

        # Prepare simplified message for SSE
        simplified_message = self._simplify_message(message)

        # Notify standard subscribers
        await self._notify_subscribers(simplified_message, is_critical=False)

    async def add_critical_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchronous method to add critical message and notify dedicated subscribers."""
        # Validation
        if not all(key in message for key in ["news_id", "title", "time_reported"]):
            logger.warning(f"Received incomplete critical message: {message}")
            return

        try:
            # Cache the critical message
            self._last_critical_message = message
            self._last_critical_timestamp = time.time()

            logger.info(
                f"Added new CRITICAL message: {message['news_id']} - {message['title']}"
            )

            # Prepare critical message for SSE
            critical_data = self._prepare_critical_message(message)

            # Notify critical subscribers
            await self._notify_subscribers(critical_data, is_critical=True)

        except Exception as e:
            logger.error(f"Error processing critical message: {e}", exc_info=True)

    def _prepare_critical_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Prepares critical message for display."""
        analysis = message.get("analysis_payload", {})

        return {
            "type": "critical",
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "symbol": analysis.get("symbol", ""),
            "signal": analysis.get("signal", "HOLD"),
            "confidence": analysis.get("confidence", 0),
            "timestamp": time.time(),
        }

    def _simplify_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Simplifies message to format suitable for SSE."""
        narrative_impact = "Unknown"
        interpretation = ""
        interpretation_tags = []
        extracted_entities = []
        sentiment = "Neutral"

        # Extract from knowledge graph data
        if (
            "analysis_payload" in message
            and "knowledge_graph_data" in message["analysis_payload"]
        ):

            kg_data = message["analysis_payload"]["knowledge_graph_data"]

            narrative_impact = kg_data.get("narrative_impact", "Unknown")
            interpretation = kg_data.get("interpretation", "")
            interpretation_tags = kg_data.get("interpretation_tags", [])
            extracted_entities = kg_data.get("extracted_entities", [])

            if "sentiment" in kg_data:
                try:
                    if isinstance(kg_data["sentiment"], dict):
                        sentiment = kg_data["sentiment"].get("label", "Neutral")
                    else:
                        sentiment = str(kg_data["sentiment"])
                except Exception:
                    sentiment = "Neutral"

        # Also check for whirlpool_analysis structure (from regular topic)
        if (
            "analysis_payload" in message
            and "whirlpool_analysis" in message["analysis_payload"]
        ):

            wp_data = message["analysis_payload"]["whirlpool_analysis"]

            # Extract from suggested_labels as tags
            if "suggested_labels" in wp_data and not interpretation_tags:
                interpretation_tags = wp_data.get("suggested_labels", [])

            # Extract entities from whirlpool analysis
            if "extracted_entities" in wp_data and not extracted_entities:
                entities_data = wp_data["extracted_entities"]
                extracted_entities = []

                # Convert whirlpool entities to standard format
                for org in entities_data.get("organizations", []):
                    if isinstance(org, dict) and "name" in org:
                        extracted_entities.append(
                            {
                                "text": org["name"],
                                "normalized_name": org["name"],
                                "type": "ORG",
                            }
                        )

                for person in entities_data.get("individuals", []):
                    if isinstance(person, dict) and "name" in person:
                        extracted_entities.append(
                            {
                                "text": person["name"],
                                "normalized_name": person["name"],
                                "type": "PERSON",
                            }
                        )

                for location in entities_data.get("locations", []):
                    if isinstance(location, dict) and "name" in location:
                        extracted_entities.append(
                            {
                                "text": location["name"],
                                "normalized_name": location["name"],
                                "type": "LOC",
                            }
                        )

            # Extract sentiment from whirlpool
            if "sentiment_analysis" in wp_data and sentiment == "Neutral":
                overall_sentiment = wp_data["sentiment_analysis"].get(
                    "overall_sentiment", {}
                )
                if isinstance(overall_sentiment, dict):
                    sentiment = overall_sentiment.get("label", "Neutral")

            # Use summary as interpretation if not already set
            if "summary" in wp_data and not interpretation:
                interpretation = wp_data["summary"]

        return {
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "ts": message.get("ts", ""),
            "narrative_impact": narrative_impact,
            "interpretation": interpretation,
            "interpretation_tags": interpretation_tags,
            "extracted_entities": extracted_entities,
            "sentiment": sentiment,
        }

    async def _notify_subscribers(
        self, message: Dict[str, Any], is_critical: bool = False
    ) -> None:
        """Notifies relevant subscribers about new message."""
        subscribers = (
            self._critical_subscribers if is_critical else self._standard_subscribers
        )

        if not subscribers:
            return

        message_json = orjson.dumps(message, default=str).decode()
        message_sse = f"data: {message_json}\n\n"

        async with self._sse_lock:
            expired_subscribers = set()

            for callback in subscribers:
                try:
                    await callback(message_sse)
                except Exception as e:
                    logger.warning(
                        f"Error notifying {'critical' if is_critical else 'standard'} subscriber: {e}"
                    )
                    expired_subscribers.add(callback)

            for expired in expired_subscribers:
                subscribers.remove(expired)

    async def subscribe(
        self, callback: Callable[[str], Awaitable[None]], is_critical: bool = False
    ) -> None:
        """Adds callback function to SSE subscribers list with limit."""
        async with self._sse_lock:
            settings = get_settings()
            subscribers = (
                self._critical_subscribers
                if is_critical
                else self._standard_subscribers
            )

            if len(subscribers) >= settings.MAX_SSE_SUBSCRIBERS:
                logger.warning(
                    f"Reached limit of {settings.MAX_SSE_SUBSCRIBERS} SSE subscribers. Rejecting new connection."
                )
                raise RuntimeError("Too many SSE subscribers")

            subscribers.add(callback)
            sub_type = "critical" if is_critical else "standard"
            logger.info(f"New {sub_type} SSE subscriber. Total: {len(subscribers)}")

    async def unsubscribe(
        self, callback: Callable[[str], Awaitable[None]], is_critical: bool = False
    ) -> None:
        """Removes callback function from SSE subscribers list."""
        async with self._sse_lock:
            subscribers = (
                self._critical_subscribers
                if is_critical
                else self._standard_subscribers
            )
            if callback in subscribers:
                subscribers.remove(callback)
                logger.info(
                    f"{'Critical' if is_critical else 'Standard'} SSE subscriber disconnected. Remaining: {len(subscribers)}"
                )

    def get_last_critical_message(self) -> Optional[Dict[str, Any]]:
        """Returns last critical message if current (less than 1 hour old)."""
        if not self._last_critical_message or not self._last_critical_timestamp:
            return None

        # Check if message is older than 1 hour
        if time.time() - self._last_critical_timestamp > 3600:
            self._last_critical_message = None
            self._last_critical_timestamp = None
            return None

        return self._prepare_critical_message(self._last_critical_message)

    async def get_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetches latest standard messages from Redis."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()

            raw_messages = await redis_client.zrevrange(
                settings.NEWS_REDIS_KEY, 0, limit - 1, withscores=False
            )

            messages = []
            for raw_message in raw_messages:
                try:
                    message = orjson.loads(raw_message)
                    messages.append(message)
                except orjson.JSONDecodeError as e:
                    logger.warning(f"Cannot decode message from Redis: {e}")
                    continue

            return messages

        except Exception as e:
            logger.error(f"Error fetching messages from Redis: {e}", exc_info=True)
            return []

    async def get_messages_count(self) -> int:
        """Returns number of messages in Redis."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            count = await redis_client.zcard(settings.NEWS_REDIS_KEY)
            return count
        except Exception as e:
            logger.error(f"Error getting message count from Redis: {e}")
            return 0

    async def clear_all_messages(self) -> bool:
        """Deletes all messages from Redis. Use with caution!"""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            deleted_count = await redis_client.delete(settings.NEWS_REDIS_KEY)
            logger.warning(
                f"Deleted all messages from Redis. Keys deleted: {deleted_count}"
            )
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting messages from Redis: {e}")
            return False

    async def cleanup_old_messages(self, max_age_seconds: int = 86400) -> int:
        """Deletes messages older than max_age_seconds."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()

            cutoff_timestamp = time.time() - max_age_seconds

            deleted_count = await redis_client.zremrangebyscore(
                settings.NEWS_REDIS_KEY, 0, cutoff_timestamp
            )

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old messages from Redis")

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning old messages: {e}")
            return 0

    async def close_connections(self) -> None:
        """Closes Redis connections at application shutdown."""
        try:
            if self._redis_client:
                await self._redis_client.close()
                logger.info("Closed Redis client connection")

            if self._redis_pool:
                await self._redis_pool.disconnect()
                logger.info("Closed Redis connection pool")

        except Exception as e:
            logger.warning(f"Error closing Redis connections: {e}")

    # Wrapper method for backward compatibility with PubSubService
    def add_message(self, message: Dict[str, Any]) -> None:
        """Synchronous wrapper for compatibility with PubSubService."""
        is_critical = message.get("is_critical", False)

        # Get the main event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, create a task
            if is_critical:
                loop.create_task(self.add_critical_message_async(message))
            else:
                loop.create_task(self.add_message_async(message))
        except RuntimeError:
            # No running event loop, we need to handle this differently
            logger.warning(
                "No running event loop in add_message, this shouldn't happen with fixed PubSubService"
            )

            # Try to run in a new event loop as last resort
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self.add_critical_message_async(message)
                    if is_critical
                    else self.add_message_async(message)
                )
            finally:
                loop.close()
