"""
Moduł zawierający zależności (dependencies) dla FastAPI
Uproszczona wersja kompatybilna z Pydantic v2
"""
from __future__ import annotations

from typing import Dict, Any
from fastapi import Request, Depends

from Backend.core.config import Settings, get_settings
from Backend.services.email_service import EmailService


def get_template_context(request: Request, settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
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


def get_email_service(settings: Settings = Depends(get_settings)) -> EmailService:
    """
    Tworzy i zwraca instancję serwisu email.
    
    Args:
        settings (Settings): Konfiguracja aplikacji
    
    Returns:
        EmailService: Instancja serwisu email
    """
    # Upewnij się, że mamy dane do SMTP
    if settings.smtp_user is None or settings.smtp_pass is None:
        settings.load_secrets()
    
    return EmailService(
        smtp_user=settings.smtp_user,
        smtp_pass=settings.smtp_pass,
        default_recipient=settings.MAIL_TO
    )