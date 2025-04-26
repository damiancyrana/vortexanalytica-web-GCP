"""
Pakiet zawierający wszystkie trasy aplikacji.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.routes.landing import register_landing_routes
from Backend.routes.auth import register_auth_routes
from Backend.routes.contact import register_contact_routes


def register_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """
    Rejestruje wszystkie trasy aplikacji.
    Wykorzystuje wzorzec fasady dla organizacji kodu.
    
    Args:
        app (FastAPI): Instancja aplikacji FastAPI
        templates (Jinja2Templates): Silnik szablonów
        settings (Settings): Konfiguracja aplikacji
    """
    # Rejestracja tras według modułów funkcjonalnych
    register_landing_routes(app, templates, settings)
    register_auth_routes(app, templates, settings)
    register_contact_routes(app, templates, settings)
    