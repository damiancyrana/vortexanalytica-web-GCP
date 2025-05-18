"""
Moduł tras strony głównej (Wersja Produkcyjna - Hybrydowa).
Używa sesji ciasteczkowej. /index wymaga sesji, API też.
"""
from __future__ import annotations
from Backend.services.news_service import NewsService

import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException # Dodano HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from Backend.core.dependencies import get_template_context, get_current_active_user
from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

def register_landing_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """ Rejestruje trasy /, /index, /api/index-data. """

    @app.get("/", response_class=HTMLResponse, summary="Publiczna strona powitalna")
    async def landing(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """ Obsługa strony głównej (landing page) - publiczna. """
        return templates.TemplateResponse("landing_page.html", context)

    @app.get("/index", response_class=HTMLResponse, name="index_page_route") # Dodano name
    async def index(
        request: Request,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user), # Wymaga sesji
        context: dict = Depends(get_template_context) # Kontekst już zawiera dane użytkownika, jeśli sesja jest ok
    ) -> HTMLResponse:
        """ Wyświetla główny interfejs aplikacji dla zalogowanego użytkownika. """
        # Sprawdzenie, czy sesja na pewno została dodana do kontekstu
        # if not context.get("user"):
        #    logger.error("Błąd: Brak danych użytkownika w kontekście mimo przejścia przez get_current_active_user!")
        #    # To nie powinno się zdarzyć, ale można dodać fallback
        #    context["user"] = current_user_session # Upewnij się, że jest

        logger.info(f"Dostęp do /index przyznany dla UID: {current_user_session.get('user_id')}")
        return templates.TemplateResponse("index.html", context)

    # Chroniony endpoint API
    @app.get("/api/index-data", summary="Pobiera dane dla strony głównej (wymaga sesji)")
    async def get_index_data(
         current_user_session: Dict[str, Any] = Depends(get_current_active_user)
    ) -> Dict[str, Any]:
         """ Zwraca chronione dane dla zalogowanego użytkownika. """
         user_email = current_user_session.get("email", "Brak emaila")
         user_uid = current_user_session.get("user_id")
         user_name = current_user_session.get("name")

         logger.info(f"Pobieranie danych API dla użytkownika z sesji: {user_uid}")

         # TODO: Zastąp przykładowe dane rzeczywistą logiką pobierania danych
         data = {
             "welcomeMessage": f"Witaj {user_name or user_email}!",
             "userUid": user_uid,
             "userEmail": user_email,
             "messages": [
                 {"id": 1, "text": "Wiadomość produkcyjna 1", "category": "equities"},
                 {"id": 2, "text": "Inna wiadomość produkcyjna", "category": "general"},
             ]
         }
         return data
    
    @app.get("/api/news", summary="Pobiera najnowsze wiadomości")
    async def get_news(
        limit: int = 10,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user)
    ) -> Dict[str, Any]:
        """Pobiera najnowsze wiadomości dla zalogowanego użytkownika."""
        logger.info(f"Pobieranie wiadomości dla użytkownika z sesji: {current_user_session.get('user_id')}")
        
        news_service = NewsService()
        messages = news_service.get_messages(limit=limit)
        
        # Przygotuj dane do odpowiedzi - tylko wymagane pola
        simplified_messages = []
        for msg in messages:
            narrative_impact = "Unknown"
            if ("analysis_payload" in msg and 
                "knowledge_graph_data" in msg["analysis_payload"] and 
                "narrative_impact" in msg["analysis_payload"]["knowledge_graph_data"]):
                narrative_impact = msg["analysis_payload"]["knowledge_graph_data"]["narrative_impact"]
            
            simplified_messages.append({
                "news_id": msg.get("news_id", ""),
                "title": msg.get("title", ""),
                "time_reported": msg.get("time_reported", ""),
                "narrative_impact": narrative_impact
            })
        
        return {"news": simplified_messages}