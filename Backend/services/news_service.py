"""
Serwis do obsługi wiadomości z Redis z obsługą SSE.
Zastępuje przechowywanie w pamięci RAM na trwałe przechowywanie w Redis.
"""
from __future__ import annotations

import logging
import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Callable, Awaitable
import redis
from redis.connection import ConnectionPool

from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

class NewsService:
    """Serwis do przechowywania i zarządzania wiadomościami w Redis z obsługą SSE."""
    _instance = None
    _initialized = False
    
    # Redis connection pool
    _redis_pool: Optional[ConnectionPool] = None
    _redis_client: Optional[redis.Redis] = None
    
    # SSE subscribers (nadal w pamięci, bo to tymczasowe połączenia)
    _subscribers: Set[Callable[[str], Awaitable[None]]] = set()
    _sse_lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NewsService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        logger.info("Inicjalizacja NewsService z Redis...")
        self._initialize_redis()
        self._initialized = True
        logger.info("NewsService z Redis zainicjalizowany.")

    def _initialize_redis(self) -> None:
        """Inicjalizuje połączenie z Redis."""
        try:
            settings = get_settings()
            
            # Sprawdź czy jest REDIS_URL (ma priorytet)
            if settings.REDIS_URL:
                logger.info(f"Łączenie z Redis przy użyciu URL: {settings.REDIS_URL}")
                self._redis_pool = ConnectionPool.from_url(
                    settings.REDIS_URL,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    retry_on_timeout=True,
                    decode_responses=True  # Automatyczne dekodowanie UTF-8
                )
            else:
                # Użyj konfiguracji host/port/password
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
                    decode_responses=True  # Automatyczne dekodowanie UTF-8
                )
            
            # Utwórz klienta Redis
            self._redis_client = redis.Redis(connection_pool=self._redis_pool)
            
            # Test połączenia
            self._redis_client.ping()
            logger.info("Pomyślnie połączono z Redis i przetestowano połączenie.")
            
        except Exception as e:
            logger.critical(f"Nie można zainicjalizować połączenia z Redis: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Redis connection: {e}") from e

    def _get_redis_client(self) -> redis.Redis:
        """Zwraca klienta Redis z obsługą błędów."""
        if not self._redis_client:
            raise RuntimeError("Redis client nie jest zainicjalizowany")
        return self._redis_client

    async def add_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchroniczna metoda dodająca nową wiadomość do Redis i powiadamiająca subskrybentów."""
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
            redis_client = self._get_redis_client()
            
            # Dodaj timestamp dla sortowania (używamy time_reported lub aktualny czas)
            try:
                # Spróbuj sparsować time_reported jako timestamp
                if message.get("time_reported"):
                    # Zakładamy że time_reported to string w formacie ISO lub timestamp
                    if isinstance(message["time_reported"], str):
                        try:
                            # Spróbuj sparsować jako ISO datetime
                            dt = datetime.fromisoformat(message["time_reported"].replace('Z', '+00:00'))
                            score = dt.timestamp()
                        except (ValueError, TypeError):
                            # Jeśli nie da się sparsować, użyj aktualnego czasu
                            score = time.time()
                    else:
                        # Jeśli to już liczba, użyj jej
                        score = float(message["time_reported"])
                else:
                    score = time.time()
            except Exception:
                score = time.time()
            
            # Serializuj wiadomość do JSON
            message_json = json.dumps(message, ensure_ascii=False, default=str)
            
            # Dodaj do sorted set w Redis (score = timestamp, value = JSON wiadomości)
            redis_client.zadd(settings.NEWS_REDIS_KEY, {message_json: score})
            
            # Ogranicz liczbę wiadomości (zachowaj tylko najnowsze)
            total_messages = redis_client.zcard(settings.NEWS_REDIS_KEY)
            if total_messages > settings.NEWS_MAX_MESSAGES:
                # Usuń najstarsze wiadomości (najmniejszy score)
                excess_count = total_messages - settings.NEWS_MAX_MESSAGES
                redis_client.zremrangebyrank(settings.NEWS_REDIS_KEY, 0, excess_count - 1)
            
            logger.info(f"Dodano nową wiadomość do Redis: {message['news_id']} - {message['title']}")
            
        except Exception as e:
            logger.error(f"Błąd podczas dodawania wiadomości do Redis: {e}", exc_info=True)
            # Nie przerywamy działania, tylko logujemy błąd
            return
        
        # Prepare simplified message dla SSE
        simplified_message = self._simplify_message(message)
        
        # Notify subscribers
        await self._notify_subscribers(simplified_message)
    
    def add_message(self, message: Dict[str, Any]) -> None:
        """Synchroniczna metoda dodająca wiadomość - tworzy zadanie asyncio."""
        # Generate one-time event loop for synchronous calls
        try:
            # Sprawdź czy jest aktywna pętla zdarzeń
            loop = asyncio.get_running_loop()
            # Jeśli tak, utwórz zadanie
            loop.create_task(self.add_message_async(message))
        except RuntimeError:
            # Nie ma aktywnej pętli, utwórz nową
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self.add_message_async(message))
            finally:
                loop.close()
    
    def _simplify_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Upraszcza wiadomość do formatu odpowiedniego dla SSE."""
        # Domyślne wartości
        narrative_impact = "Unknown"
        interpretation = ""
        interpretation_tags = []
        extracted_entities = []
        
        # Pobierz dane z knowledge_graph_data, jeśli istnieją
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
        
        return {
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "ts": message.get("ts", ""),
            "narrative_impact": narrative_impact,
            "interpretation": interpretation,
            "interpretation_tags": interpretation_tags,
            "extracted_entities": extracted_entities
        }
    
    async def _notify_subscribers(self, message: Dict[str, Any]) -> None:
        """Powiadamia wszystkich subskrybentów o nowej wiadomości."""
        if not self._subscribers:
            return
            
        message_json = json.dumps(message, ensure_ascii=False, default=str)
        message_sse = f"data: {message_json}\n\n"
        
        async with self._sse_lock:
            expired_subscribers = set()
            
            for callback in self._subscribers:
                try:
                    await callback(message_sse)
                except Exception as e:
                    logger.warning(f"Błąd podczas powiadamiania subskrybenta: {e}")
                    expired_subscribers.add(callback)
            
            # Usuń nieaktywnych subskrybentów
            for expired in expired_subscribers:
                self._subscribers.remove(expired)
            
            logger.debug(f"Powiadomiono {len(self._subscribers)} aktywnych subskrybentów o nowej wiadomości.")

    async def subscribe(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Dodaje funkcję callback do listy subskrybentów SSE."""
        async with self._sse_lock:
            self._subscribers.add(callback)
            logger.info(f"Nowy subskrybent SSE. Łącznie: {len(self._subscribers)}")
    
    async def unsubscribe(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Usuwa funkcję callback z listy subskrybentów SSE."""
        async with self._sse_lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
                logger.info(f"Subskrybent SSE odłączony. Pozostało: {len(self._subscribers)}")

    def get_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Pobiera ostatnie wiadomości z Redis."""
        try:
            settings = get_settings()
            redis_client = self._get_redis_client()
            
            # Pobierz najnowsze wiadomości (największy score = najnowsze)
            # ZREVRANGE zwraca od największego do najmniejszego score
            raw_messages = redis_client.zrevrange(
                settings.NEWS_REDIS_KEY, 
                0, 
                limit - 1,  # Redis jest 0-indexed
                withscores=False  # Nie potrzebujemy scores
            )
            
            messages = []
            for raw_message in raw_messages:
                try:
                    # Deserializuj JSON
                    message = json.loads(raw_message)
                    messages.append(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"Nie można zdekodować wiadomości z Redis: {e}")
                    continue
            
            logger.debug(f"Pobrano {len(messages)} wiadomości z Redis (limit: {limit})")
            return messages
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania wiadomości z Redis: {e}", exc_info=True)
            return []  # Zwróć pustą listę w przypadku błędu

    def get_messages_count(self) -> int:
        """Zwraca liczbę wiadomości w Redis."""
        try:
            settings = get_settings()
            redis_client = self._get_redis_client()
            count = redis_client.zcard(settings.NEWS_REDIS_KEY)
            return count
        except Exception as e:
            logger.error(f"Błąd podczas pobierania liczby wiadomości z Redis: {e}")
            return 0

    def clear_all_messages(self) -> bool:
        """Usuwa wszystkie wiadomości z Redis. Używaj ostrożnie!"""
        try:
            settings = get_settings()
            redis_client = self._get_redis_client()
            deleted_count = redis_client.delete(settings.NEWS_REDIS_KEY)
            logger.warning(f"Usunięto wszystkie wiadomości z Redis. Usuniętych kluczy: {deleted_count}")
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Błąd podczas usuwania wiadomości z Redis: {e}")
            return False

    def cleanup_old_messages(self, max_age_seconds: int = 86400) -> int:
        """
        Usuwa wiadomości starsze niż max_age_seconds.
        
        Args:
            max_age_seconds: Maksymalny wiek wiadomości w sekundach (domyślnie 24h)
            
        Returns:
            Liczba usuniętych wiadomości
        """
        try:
            settings = get_settings()
            redis_client = self._get_redis_client()
            
            # Oblicz timestamp graniczny
            cutoff_timestamp = time.time() - max_age_seconds
            
            # Usuń wiadomości ze score mniejszym niż cutoff_timestamp
            deleted_count = redis_client.zremrangebyscore(
                settings.NEWS_REDIS_KEY, 
                0,  # min score
                cutoff_timestamp  # max score
            )
            
            if deleted_count > 0:
                logger.info(f"Usunięto {deleted_count} starych wiadomości z Redis (starsze niż {max_age_seconds}s)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia starych wiadomości: {e}")
            return 0

    def close_connections(self) -> None:
        """Zamyka połączenia z Redis przy wyłączaniu aplikacji."""
        try:
            if self._redis_client:
                self._redis_client.close()
                logger.info("Zamknięto połączenie z Redis client")
            
            if self._redis_pool:
                self._redis_pool.disconnect()
                logger.info("Zamknięto pool połączeń Redis")
                
        except Exception as e:
            logger.warning(f"Błąd podczas zamykania połączeń Redis: {e}")
            