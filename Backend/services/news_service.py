"""
Serwis do obsługi wiadomości z Redis z obsługą SSE.
Obsługuje zarówno standardowe jak i krytyczne wiadomości.
"""
from __future__ import annotations

import logging, asyncio, time, orjson
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Callable, Awaitable
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

class NewsService:
    """Serwis do przechowywania i zarządzania wiadomościami w Redis z obsługą SSE."""
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
        logger.info("Inicjalizacja NewsService z Redis...")
        self._initialized = True
        # Redis będzie inicjalizowany asynchronicznie przy pierwszym użyciu
        logger.info("NewsService zainicjalizowany.")

    async def _ensure_redis_initialized(self) -> None:
        """Upewnia się, że Redis jest zainicjalizowany."""
        if self._redis_client is None:
            await self._initialize_redis()
    
    async def _initialize_redis(self) -> None:
        """Inicjalizuje asynchroniczne połączenie z Redis."""
        try:
            settings = get_settings()
            
            if settings.REDIS_URL:
                logger.info(f"Łączenie z Redis przy użyciu URL: {settings.REDIS_URL}")
                self._redis_pool = ConnectionPool.from_url(
                    settings.REDIS_URL,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    retry_on_timeout=True,
                    decode_responses=True
                )
            else:
                logger.info(f"Łączenie z Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}, DB: {settings.REDIS_DB}")
                self._redis_pool = ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    retry_on_timeout=True,
                    decode_responses=True
                )
            
            self._redis_client = redis.Redis(connection_pool=self._redis_pool)
            await self._redis_client.ping()
            logger.info("Pomyślnie połączono z Redis i przetestowano połączenie.")
            
        except Exception as e:
            logger.critical(f"Nie można zainicjalizować połączenia z Redis: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Redis connection: {e}") from e

    async def _get_redis_client(self) -> redis.Redis:
        """Zwraca klienta Redis z obsługą błędów."""
        await self._ensure_redis_initialized()
        if not self._redis_client:
            raise RuntimeError("Redis client nie jest zainicjalizowany")
        return self._redis_client

    async def add_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchroniczna metoda dodająca nową wiadomość standardową do Redis i powiadamiająca subskrybentów."""
        # Validation
        if not all(key in message for key in ["news_id", "title", "time_reported"]):
            logger.warning(f"Otrzymano niepełną wiadomość: {message}")
            return
        
        # Add narrative_impact if missing
        if "analysis_payload" in message and "knowledge_graph_data" in message["analysis_payload"]:
            if "narrative_impact" not in message["analysis_payload"]["knowledge_graph_data"]:
                message["analysis_payload"]["knowledge_graph_data"]["narrative_impact"] = "Unknown"
        
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            
            # Dodaj timestamp dla sortowania
            try:
                if message.get("time_reported"):
                    if isinstance(message["time_reported"], str):
                        try:
                            dt = datetime.fromisoformat(message["time_reported"].replace('Z', '+00:00'))
                            score = dt.timestamp()
                        except (ValueError, TypeError):
                            score = time.time()
                    else:
                        score = float(message["time_reported"])
                else:
                    score = time.time()
            except Exception:
                score = time.time()
            
            # Serializuj wiadomość do JSON
            message_json = orjson.dumps(message, default=str).decode()
            
            # Dodaj do sorted set w Redis
            await redis_client.zadd(settings.NEWS_REDIS_KEY, {message_json: score})
            
            # Ogranicz liczbę wiadomości
            total_messages = await redis_client.zcard(settings.NEWS_REDIS_KEY)
            if total_messages > settings.NEWS_MAX_MESSAGES:
                excess_count = total_messages - settings.NEWS_MAX_MESSAGES
                await redis_client.zremrangebyrank(settings.NEWS_REDIS_KEY, 0, excess_count - 1)
            
            logger.info(f"Dodano nową wiadomość standardową do Redis: {message['news_id']} - {message['title']}")
            
        except Exception as e:
            logger.error(f"Błąd podczas dodawania wiadomości do Redis: {e}", exc_info=True)
            return
        
        # Prepare simplified message dla SSE
        simplified_message = self._simplify_message(message)
        
        # Notify standard subscribers
        await self._notify_subscribers(simplified_message, is_critical=False)
    
    async def add_critical_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchroniczna metoda dodająca krytyczną wiadomość i powiadamiająca dedykowanych subskrybentów."""
        # Validation
        if not all(key in message for key in ["news_id", "title", "time_reported"]):
            logger.warning(f"Otrzymano niepełną wiadomość krytyczną: {message}")
            return
        
        try:
            # Cache the critical message
            self._last_critical_message = message
            self._last_critical_timestamp = time.time()
            
            logger.info(f"Dodano nową wiadomość KRYTYCZNĄ: {message['news_id']} - {message['title']}")
            
            # Prepare critical message dla SSE
            critical_data = self._prepare_critical_message(message)
            
            # Notify critical subscribers
            await self._notify_subscribers(critical_data, is_critical=True)
            
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania krytycznej wiadomości: {e}", exc_info=True)
    
    def _prepare_critical_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Przygotowuje krytyczną wiadomość do wyświetlenia."""
        analysis = message.get("analysis_payload", {})
        
        return {
            "type": "critical",
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "symbol": analysis.get("symbol", ""),
            "signal": analysis.get("signal", "HOLD"),
            "confidence": analysis.get("confidence", 0),
            "timestamp": time.time()
        }
    
    def _simplify_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Upraszcza wiadomość do formatu odpowiedniego dla SSE."""
        narrative_impact = "Unknown"
        interpretation = ""
        interpretation_tags = []
        extracted_entities = []
        sentiment = "Neutral"
        
        if ("analysis_payload" in message and 
            "knowledge_graph_data" in message["analysis_payload"]):
            
            kg_data = message["analysis_payload"]["knowledge_graph_data"]
            
            if "narrative_impact" in kg_data:
                narrative_impact = kg_data["narrative_impact"]
            
            if "interpretation" in kg_data:
                interpretation = kg_data["interpretation"]
            
            if "interpretation_tags" in kg_data:
                interpretation_tags = kg_data["interpretation_tags"]
            
            if "extracted_entities" in kg_data:
                extracted_entities = kg_data["extracted_entities"]

            if "sentiment" in kg_data:
                try:
                    if isinstance(kg_data["sentiment"], dict):
                        sentiment = kg_data["sentiment"].get("label", "Neutral")
                    else:
                        sentiment = str(kg_data["sentiment"])
                except Exception:
                    sentiment = "Neutral"
        
        return {
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "ts": message.get("ts", ""),
            "narrative_impact": narrative_impact,
            "interpretation": interpretation,
            "interpretation_tags": interpretation_tags,
            "extracted_entities": extracted_entities,
            "sentiment": sentiment
        }
    
    async def _notify_subscribers(self, message: Dict[str, Any], is_critical: bool = False) -> None:
        """Powiadamia odpowiednich subskrybentów o nowej wiadomości."""
        subscribers = self._critical_subscribers if is_critical else self._standard_subscribers
        
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
                    logger.warning(f"Błąd podczas powiadamiania subskrybenta {'krytycznego' if is_critical else 'standardowego'}: {e}")
                    expired_subscribers.add(callback)
            
            for expired in expired_subscribers:
                subscribers.remove(expired)

    async def subscribe(self, callback: Callable[[str], Awaitable[None]], is_critical: bool = False) -> None:
        """Dodaje funkcję callback do listy subskrybentów SSE."""
        async with self._sse_lock:
            if is_critical:
                self._critical_subscribers.add(callback)
                logger.info(f"Nowy subskrybent SSE krytyczny. Łącznie: {len(self._critical_subscribers)}")
            else:
                self._standard_subscribers.add(callback)
                logger.info(f"Nowy subskrybent SSE standardowy. Łącznie: {len(self._standard_subscribers)}")
    
    async def unsubscribe(self, callback: Callable[[str], Awaitable[None]], is_critical: bool = False) -> None:
        """Usuwa funkcję callback z listy subskrybentów SSE."""
        async with self._sse_lock:
            subscribers = self._critical_subscribers if is_critical else self._standard_subscribers
            if callback in subscribers:
                subscribers.remove(callback)
                logger.info(f"Subskrybent SSE {'krytyczny' if is_critical else 'standardowy'} odłączony. Pozostało: {len(subscribers)}")

    def get_last_critical_message(self) -> Optional[Dict[str, Any]]:
        """Zwraca ostatnią krytyczną wiadomość jeśli jest aktualna (mniej niż godzina)."""
        if not self._last_critical_message or not self._last_critical_timestamp:
            return None
        
        # Sprawdź czy wiadomość nie jest starsza niż godzina
        if time.time() - self._last_critical_timestamp > 3600:  # 1 godzina
            self._last_critical_message = None
            self._last_critical_timestamp = None
            return None
        
        return self._prepare_critical_message(self._last_critical_message)

    async def get_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Pobiera ostatnie wiadomości standardowe z Redis."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            
            raw_messages = await redis_client.zrevrange(
                settings.NEWS_REDIS_KEY, 
                0, 
                limit - 1,
                withscores=False
            )
            
            messages = []
            for raw_message in raw_messages:
                try:
                    message = orjson.loads(raw_message)
                    messages.append(message)
                except orjson.JSONDecodeError as e:
                    logger.warning(f"Nie można zdekodować wiadomości z Redis: {e}")
                    continue
            
            return messages
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania wiadomości z Redis: {e}", exc_info=True)
            return []

    async def get_messages_count(self) -> int:
        """Zwraca liczbę wiadomości w Redis."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            count = await redis_client.zcard(settings.NEWS_REDIS_KEY)
            return count
        except Exception as e:
            logger.error(f"Błąd podczas pobierania liczby wiadomości z Redis: {e}")
            return 0

    async def clear_all_messages(self) -> bool:
        """Usuwa wszystkie wiadomości z Redis. Używaj ostrożnie!"""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            deleted_count = await redis_client.delete(settings.NEWS_REDIS_KEY)
            logger.warning(f"Usunięto wszystkie wiadomości z Redis. Usuniętych kluczy: {deleted_count}")
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Błąd podczas usuwania wiadomości z Redis: {e}")
            return False

    async def cleanup_old_messages(self, max_age_seconds: int = 86400) -> int:
        """Usuwa wiadomości starsze niż max_age_seconds."""
        try:
            settings = get_settings()
            redis_client = await self._get_redis_client()
            
            cutoff_timestamp = time.time() - max_age_seconds
            
            deleted_count = await redis_client.zremrangebyscore(
                settings.NEWS_REDIS_KEY, 
                0,
                cutoff_timestamp
            )
            
            if deleted_count > 0:
                logger.info(f"Usunięto {deleted_count} starych wiadomości z Redis")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia starych wiadomości: {e}")
            return 0

    async def close_connections(self) -> None:
        """Zamyka połączenia z Redis przy wyłączaniu aplikacji."""
        try:
            if self._redis_client:
                await self._redis_client.close()
                logger.info("Zamknięto połączenie z Redis client")
            
            if self._redis_pool:
                await self._redis_pool.disconnect()
                logger.info("Zamknięto pool połączeń Redis")
                
        except Exception as e:
            logger.warning(f"Błąd podczas zamykania połączeń Redis: {e}")
    
    # Wrapper metoda dla kompatybilności wstecznej z PubSubService
    def add_message(self, message: Dict[str, Any]) -> None:
        """Synchroniczny wrapper dla kompatybilności z PubSubService."""
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
            # Since we're being called from a thread, we should use the main loop
            # This should not happen with the fixed PubSubService, but keeping as safety
            logger.warning("No running event loop in add_message, this shouldn't happen with fixed PubSubService")
            
            # Try to run in a new event loop as last resort
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self.add_critical_message_async(message) if is_critical else self.add_message_async(message))
            finally:
                loop.close()
                