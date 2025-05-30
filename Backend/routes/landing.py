"""
Moduł tras strony głównej (Wersja Produkcyjna - Hybrydowa).
Używa sesji ciasteczkowej. /index wymaga sesji, API też.
"""
from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends
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


    @app.get("/index", response_class=HTMLResponse, name="index_page_route")
    async def index(request: Request, current_user_session: Dict[str, Any] = Depends(get_current_active_user),context: dict = Depends(get_template_context)) -> HTMLResponse:
        """ Wyświetla główny interfejs aplikacji dla zalogowanego użytkownika. """
        logger.info(f"Dostęp do /index przyznany dla UID: {current_user_session.get('email')}")
        return templates.TemplateResponse("index.html", context)


    # Chroniony endpoint API
    @app.get("/api/index-data", summary="Pobiera dane dla strony głównej (wymaga sesji)")
    async def get_index_data(current_user_session: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
         """ Zwraca chronione dane dla zalogowanego użytkownika. """
         user_email = current_user_session.get("email", "Brak emaila")
         user_uid = current_user_session.get("user_id")
         user_name = current_user_session.get("name")

         logger.info(f"Pobieranie danych API dla użytkownika z sesji: {user_email}")

         data = {
             "welcomeMessage": f"Witaj {user_name or user_email}!",
             "userUid": user_uid,
             "userEmail": user_email,
             "messages": []  # Dane wiadomości są teraz dostarczane przez endpoint /api/news
         }
         return data
    