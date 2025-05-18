from __future__ import annotations

import logging
import asyncio, json
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, status, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from Backend.core.dependencies import get_current_active_user
from Backend.services.news_service import NewsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/news",
    tags=["news"],
    dependencies=[Depends(get_current_active_user)]
)

@router.get("")
async def get_news(
    limit: int = 10,
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Pobiera najnowsze wiadomości dla zalogowanego użytkownika."""
    logger.info(f"Pobieranie wiadomości dla użytkownika z sesji: {current_user_session.get('user_id')}")
    
    news_service = NewsService()
    messages = news_service.get_messages(limit=limit)
    
    # Przygotuj dane do odpowiedzi - używamy _simplify_message z NewsService
    simplified_messages = []
    for msg in messages:
        simplified_messages.append(news_service._simplify_message(msg))
    
    return {"news": simplified_messages}


@router.get("/stream")
async def stream_news(
    request: Request,
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> StreamingResponse:
    """
    Endpoint SSE dla aktualnych wiadomości.
    Używa długiego połączenia HTTP do przesyłania wiadomości w czasie rzeczywistym.
    """
    user_id = current_user_session.get('user_id')
    logger.info(f"Otwieranie strumienia SSE dla użytkownika: {user_id}")
    
    async def event_generator():
        # Powiadomienie początkowe
        yield "data: {\"type\": \"connected\", \"message\": \"SSE connection established\"}\n\n"
        
        # Zwróć najnowsze wiadomości natychmiast
        news_service = NewsService()
        recent_messages = news_service.get_messages(limit=5)
        for msg in recent_messages:
            simplified = news_service._simplify_message(msg)
            yield f"data: {json.dumps(simplified)}\n\n"
        
        # Utwórz funkcję callbacku dla nowych wiadomości
        send_queue = asyncio.Queue()
        
        async def send_events(data: str):
            await send_queue.put(data)
            return
        
        # Dodaj do subskrybentów
        await news_service.subscribe(send_events)
        
        try:
            # Heartbeat co 30 sekund
            heartbeat_task = asyncio.create_task(send_heartbeats(send_queue))
            
            # Czekaj na wiadomości lub rozłączenie
            while not await request.is_disconnected():
                try:
                    # Czekaj na dane z kolejki z timeout
                    data = await asyncio.wait_for(send_queue.get(), timeout=3.0)
                    yield data
                except asyncio.TimeoutError:
                    # Sprawdź rozłączenie co 3 sekundy
                    continue
                except Exception as e:
                    logger.error(f"Błąd podczas obsługi kolejki SSE: {e}", exc_info=True)
                    break
        finally:
            # Anuluj heartbeat i wypisz subskrybenta
            heartbeat_task.cancel()
            await news_service.unsubscribe(send_events)
            logger.info(f"Zamknięto strumień SSE dla użytkownika: {user_id}")
    
    # Pomocnicza funkcja do wysyłania heartbeat
    async def send_heartbeats(queue):
        try:
            while True:
                await asyncio.sleep(30)
                await queue.put("data: {\"type\": \"heartbeat\"}\n\n")
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Wyłącza buforowanie dla Nginx
        }
    )