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
async def get_news(limit: int = 30, current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Pobiera najnowsze wiadomości dla zalogowanego użytkownika."""
    logger.info(f"Pobieranie wiadomości dla użytkownika z sesji: {current_user_session.get('emmail')}")
    
    news_service = NewsService()
    messages = await news_service.get_messages(limit=limit)
    
    # Przygotuj dane do odpowiedzi
    simplified_messages = []
    for msg in messages:
        simplified_messages.append(news_service._simplify_message(msg))
    return {"news": simplified_messages}

@router.get("/stream")
async def stream_news(request: Request, current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> StreamingResponse:
    """
    Endpoint SSE dla aktualnych wiadomości.
    Używa długiego połączenia HTTP do przesyłania wiadomości w czasie rzeczywistym.
    """
    user_id = current_user_session.get('user_id')
    user_email = current_user_session.get('email')
    logger.info(f"Otwieranie strumienia SSE dla użytkownika: {user_email}")
    
    async def event_generator():
        # Powiadomienie początkowe
        yield "data: {\"type\": \"connected\", \"message\": \"SSE connection established\"}\n\n"
        
        # Zwróć najnowsze wiadomości natychmiast z Redis
        news_service = NewsService()
        recent_messages = await news_service.get_messages(limit=5)
        for msg in recent_messages:
            simplified = news_service._simplify_message(msg)
            yield f"data: {json.dumps(simplified)}\n\n"
        
        # Utwórz funkcję callbacku dla nowych wiadomości
        send_queue = asyncio.Queue()
        
        async def send_events(data: str):
            await send_queue.put(data)
            return
        
        # Dodaj do subskrybentów
        await news_service.subscribe(send_events, is_critical=False)
        
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
            await news_service.unsubscribe(send_events, is_critical=False)
            logger.info(f"Zamknięto strumień SSE dla użytkownika: {user_email}")
    
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

@router.get("/critical/stream")
async def stream_critical_news(request: Request, current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> StreamingResponse:
    """
    Endpoint SSE dla krytycznych wiadomości rynkowych.
    Przesyła tylko najważniejsze sygnały w czasie rzeczywistym.
    """
    user_id = current_user_session.get('user_id')
    user_email = current_user_session.get('email')
    logger.info(f"Otwieranie krytycznego strumienia SSE dla użytkownika: {user_email}")
    
    async def event_generator():
        # Powiadomienie początkowe
        yield "data: {\"type\": \"connected\", \"message\": \"Critical SSE connection established\"}\n\n"
        
        # Sprawdź czy jest ostatnia krytyczna wiadomość
        news_service = NewsService()
        last_critical = news_service.get_last_critical_message()
        if last_critical:
            yield f"data: {json.dumps(last_critical)}\n\n"
        
        # Utwórz funkcję callbacku dla nowych krytycznych wiadomości
        send_queue = asyncio.Queue()
        
        async def send_events(data: str):
            await send_queue.put(data)
            return
        
        # Dodaj do subskrybentów krytycznych
        await news_service.subscribe(send_events, is_critical=True)
        
        try:
            # Heartbeat co 30 sekund
            heartbeat_task = asyncio.create_task(send_heartbeats(send_queue))
            
            # Timer do czyszczenia starych wiadomości
            cleanup_task = asyncio.create_task(cleanup_old_critical(send_queue))
            
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
                    logger.error(f"Błąd podczas obsługi kolejki krytycznej SSE: {e}", exc_info=True)
                    break
        finally:
            # Anuluj zadania i wypisz subskrybenta
            heartbeat_task.cancel()
            cleanup_task.cancel()
            await news_service.unsubscribe(send_events, is_critical=True)
            logger.info(f"Zamknięto krytyczny strumień SSE dla użytkownika: {user_email}")
    
    # Pomocnicza funkcja do wysyłania heartbeat
    async def send_heartbeats(queue):
        try:
            while True:
                await asyncio.sleep(30)
                await queue.put("data: {\"type\": \"heartbeat\"}\n\n")
        except asyncio.CancelledError:
            pass
    
    # Pomocnicza funkcja do czyszczenia starych wiadomości krytycznych
    async def cleanup_old_critical(queue):
        try:
            while True:
                await asyncio.sleep(60)  # Sprawdzaj co minutę
                # Wyślij sygnał do usunięcia jeśli wiadomość jest za stara
                news_service = NewsService()
                if not news_service.get_last_critical_message():
                    await queue.put("data: {\"type\": \"clear_critical\"}\n\n")
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

@router.get("/stats")
async def get_news_stats(current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Zwraca statystyki wiadomości w Redis."""
    news_service = NewsService()
    total_count = await news_service.get_messages_count()
    return {
        "total_messages": total_count,
        "storage_type": "Redis",
        "user_id": current_user_session.get('user_id')
    }

@router.post("/admin/cleanup")
async def cleanup_old_messages(max_age_hours: int = 24, current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
    """
    Endpoint administracyjny do czyszczenia starych wiadomości.
    UWAGA: W produkcji wymaga uprawnień administratora!
    """
    # TODO: Dodaj sprawdzanie uprawnień administratora
    user_id = current_user_session.get('user_id')
    logger.warning(f"Użytkownik {user_id} uruchomił czyszczenie starych wiadomości (max_age: {max_age_hours}h)")
    
    news_service = NewsService()
    
    # Konwertuj godziny na sekundy
    max_age_seconds = max_age_hours * 3600
    
    # Pobierz statystyki przed czyszczeniem
    count_before = await news_service.get_messages_count()
    
    # Wykonaj czyszczenie
    deleted_count = await news_service.cleanup_old_messages(max_age_seconds=max_age_seconds)
    
    # Pobierz statystyki po czyszczeniu
    count_after = await news_service.get_messages_count()
    
    return {
        "messages_before": count_before,
        "messages_after": count_after,
        "deleted_count": deleted_count,
        "max_age_hours": max_age_hours,
        "performed_by": user_id
    }

@router.delete("/admin/clear-all")
async def clear_all_messages(
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Endpoint administracyjny do usunięcia WSZYSTKICH wiadomości.
    UWAGA: Bardzo niebezpieczny endpoint! W produkcji wyłączony.
    """
    user_id = current_user_session.get('user_id')
    logger.critical(f"UWAGA: Użytkownik {user_id} próbuje usunąć WSZYSTKIE wiadomości!")
    
    # W produkcji - zawsze wyłączone
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Endpoint wyłączony w środowisku produkcyjnym ze względów bezpieczeństwa."
    )