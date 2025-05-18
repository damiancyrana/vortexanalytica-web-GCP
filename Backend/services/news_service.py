"""
Serwis do obsługi wiadomości z PubSub z obsługą SSE.
"""
from __future__ import annotations

import logging
import threading
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Callable, Awaitable
from collections import deque

logger = logging.getLogger(__name__)

class NewsService:
    """Serwis do przechowywania i zarządzania wiadomościami z PubSub z obsługą SSE."""
    _instance = None
    _initialized = False
    _max_news_count = 50
    _messages = deque(maxlen=_max_news_count)
    _lock = threading.Lock()
    
    # SSE subscribers
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
        logger.info("Inicjalizacja NewsService...")
        self._initialized = True
        logger.info("NewsService zainicjalizowany.")

    async def add_message_async(self, message: Dict[str, Any]) -> None:
        """Asynchroniczna metoda dodająca nową wiadomość i powiadamiająca subskrybentów."""
        with self._lock:
            # Validation
            if not all(key in message for key in ["news_id", "title", "time_reported"]):
                logger.warning(f"Otrzymano niepełną wiadomość: {message}")
                return
            
            # Add narrative_impact if missing
            if "analysis_payload" in message and "knowledge_graph_data" in message["analysis_payload"]:
                if "narrative_impact" not in message["analysis_payload"]["knowledge_graph_data"]:
                    message["analysis_payload"]["knowledge_graph_data"]["narrative_impact"] = "Unknown"
            
            # Add to local collection
            self._messages.append(message)
            logger.info(f"Dodano nową wiadomość: {message['news_id']} - {message['title']}")
        
        # Prepare simplified message
        simplified_message = self._simplify_message(message)
        
        # Notify subscribers
        await self._notify_subscribers(simplified_message)
    
    def add_message(self, message: Dict[str, Any]) -> None:
        """Synchroniczna metoda dodająca wiadomość - tworzy zadanie asyncio."""
        # Generate one-time event loop for synchronous calls
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.add_message_async(message))
        finally:
            loop.close()
    
    def _simplify_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Upraszcza wiadomość do formatu odpowiedniego dla SSE."""
        narrative_impact = "Unknown"
        if ("analysis_payload" in message and 
            "knowledge_graph_data" in message["analysis_payload"] and 
            "narrative_impact" in message["analysis_payload"]["knowledge_graph_data"]):
            narrative_impact = message["analysis_payload"]["knowledge_graph_data"]["narrative_impact"]
        
        return {
            "news_id": message.get("news_id", ""),
            "title": message.get("title", ""),
            "time_reported": message.get("time_reported", ""),
            "narrative_impact": narrative_impact
        }
    
    async def _notify_subscribers(self, message: Dict[str, Any]) -> None:
        """Powiadamia wszystkich subskrybentów o nowej wiadomości."""
        if not self._subscribers:
            return
            
        message_json = json.dumps(message)
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
        """Pobiera ostatnie wiadomości."""
        with self._lock:
            return list(self._messages)[-limit:]