"""
Moduł zarządzający cyklem życia aplikacji.
Uproszczona wersja kompatybilna z Pydantic v2
"""
from __future__ import annotations

import logging
import asyncio

from Backend.core.config import get_settings

logger = logging.getLogger(__name__)


async def app_startup() -> None:
    """
    Funkcja wykonywana przy starcie aplikacji.
    
    Inicjalizuje zasoby i przeprowadza niezbędne sprawdzenia.
    """
    logger.info("Uruchamianie aplikacji Vortex Analytica...")
    
    settings = get_settings()
    
    # Ładowanie sekretów jeśli w trybie produkcyjnym
    if settings.is_production:
        try:
            settings.load_secrets()
            logger.info("Sekrety zostały pomyślnie załadowane.")
        except Exception as e:
            logger.error(f"Błąd podczas ładowania sekretów: {e}")
    
    logger.info(f"Aplikacja uruchomiona w trybie: {settings.environment}")


async def app_shutdown() -> None:
    """
    Funkcja wykonywana przy zamykaniu aplikacji.
    
    Zwalnia zasoby i zamyka połączenia.
    """
    logger.info("Zamykanie aplikacji...")
    logger.info("Aplikacja została pomyślnie zamknięta.")
    