"""
Moduł zawierający zależności (dependencies) dla FastAPI
Uproszczona wersja kompatybilna z Pydantic v2
"""
from __future__ import annotations

from typing import Dict, Any
from fastapi import Request

from Backend.core.config import Settings


def get_template_context(request: Request, settings: Settings) -> Dict[str, Any]:
    """
    Tworzy bazowy kontekst dla szablonów.
    
    Args:
        request (Request): Obiekt żądania HTTP
        settings (Settings): Konfiguracja aplikacji
    
    Returns:
        Dict[str, Any]: Bazowy kontekst zawierający wspólne zmienne dla wszystkich szablonów
    """
    return {
        "request": request,
        "app_name": settings.app_name,
        "auth_url": "/login",  # Nowe ustawienie dla strony logowania
        "environment": settings.environment,
        "is_production": settings.is_production,
    }