"""
Pakiet zawierający wszystkie trasy aplikacji. (Wersja Produkcyjna - Hybrydowa)
"""
from __future__ import annotations
from Backend.routes.news import router as news_router
import logging
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.routes.landing import register_landing_routes
from Backend.routes.auth import register_auth_routes
from Backend.routes.contact import register_contact_routes

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """ Rejestruje wszystkie trasy aplikacji. """
    logger.info("Rejestrowanie tras aplikacji...")
    try:
        register_landing_routes(app, templates, settings)
        register_auth_routes(app, templates, settings)
        register_contact_routes(app, templates, settings)
        app.include_router(news_router)
        logger.info("Trasy aplikacji zarejestrowane pomyślnie.")
    except Exception as e:
        logger.critical(f"Krytyczny błąd podczas rejestrowania tras: {e}", exc_info=True)
        raise RuntimeError("Failed to register application routes.") from e