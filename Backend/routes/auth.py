"""
Moduł obsługujący trasy związane z autoryzacją i uwierzytelnianiem.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.core.dependencies import get_template_context


def register_auth_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """
    Rejestruje trasy związane z autoryzacją.
    
    Args:
        app (FastAPI): Instancja aplikacji FastAPI
        templates (Jinja2Templates): Silnik szablonów
        settings (Settings): Konfiguracja aplikacji
    """
    
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """
        Obsługa strony logowania.
        
        Args:
            context (dict): Kontekst szablonu
        
        Returns:
            HTMLResponse: Odpowiedź HTML z wyrenderowanym szablonem
        """
        return templates.TemplateResponse(
            "login.html",
            context
        )
    
    # Tutaj w przyszłości można dodać więcej tras do obsługi autoryzacji
    # np. rejestracja, resetowanie hasła, itp.