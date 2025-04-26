"""
Moduł obsługujący trasy związane ze stroną główną.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.core.dependencies import get_template_context


def register_landing_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """
    Rejestruje trasy związane ze stroną główną.
    
    Args:
        app (FastAPI): Instancja aplikacji FastAPI
        templates (Jinja2Templates): Silnik szablonów
        settings (Settings): Konfiguracja aplikacji
    """
    
    @app.get("/", response_class=HTMLResponse)
    async def landing(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """
        Obsługa strony głównej (landing page).
        
        Args:
            context (dict): Kontekst szablonu
        
        Returns:
            HTMLResponse: Odpowiedź HTML z wyrenderowanym szablonem
        """
        return templates.TemplateResponse(
            "landing_page.html",
            context
        )

    @app.get("/index", response_class=HTMLResponse)
    async def index(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """
        Obsługa strony z indeksem danych.
        
        Args:
            context (dict): Kontekst szablonu
        
        Returns:
            HTMLResponse: Odpowiedź HTML z wyrenderowanym szablonem
        """
        return templates.TemplateResponse(
            "index.html",
            context
        )