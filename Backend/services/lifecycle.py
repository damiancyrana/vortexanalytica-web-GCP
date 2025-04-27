"""
Moduł cyklu życia aplikacji (Wersja Produkcyjna - Hybrydowa).
Inicjalizuje Firebase Admin SDK.
"""
from __future__ import annotations

import logging
import json
from json import JSONDecodeError

import firebase_admin
from firebase_admin import credentials

from Backend.core.config import get_settings, Settings # Dodano Settings
from Backend.services.email_service import EmailService # Import dla shutdown

logger = logging.getLogger(__name__)

async def app_startup() -> None:
    """ Inicjalizuje Firebase Admin SDK przy starcie aplikacji. """
    logger.info("Uruchamianie aplikacji Vortex Analytica (startup event)...")
    try:
        settings = get_settings() # Pobierz konfigurację (ładuje też sekrety)
    except Exception as e:
        # Błąd krytyczny już zalogowany w get_settings, tutaj tylko potwierdzamy zatrzymanie
        logger.critical("Zatrzymanie aplikacji z powodu błędu konfiguracji.")
        raise SystemExit(f"Application cannot start due to configuration error on startup: {e}")

    # Inicjalizacja Firebase Admin SDK
    try:
        if not firebase_admin._apps:
            logger.info(f"Pobieranie klucza Firebase Admin SDK z sekretu: {settings.firebase_service_account_secret_id}")
            firebase_key_json_str = settings.get_secret(settings.firebase_service_account_secret_id)
            # Sprawdzenie pustej wartości jest teraz w get_secret
            firebase_credentials_dict = json.loads(firebase_key_json_str)
            cred = credentials.Certificate(firebase_credentials_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK zainicjalizowany pomyślnie.")
        else:
             logger.info("Firebase Admin SDK jest już zainicjalizowane (możliwe ponowne ładowanie uvicorn).")
    except (JSONDecodeError, ValueError, FileNotFoundError, TypeError, Exception) as e: # Łapiemy więcej potencjalnych błędów
        logger.critical(f"Krytyczny błąd podczas inicjalizacji Firebase Admin SDK z sekretu '{settings.firebase_service_account_secret_id}': {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize Firebase Admin SDK from secret '{settings.firebase_service_account_secret_id}'.") from e

    logger.info(f"Aplikacja uruchomiona pomyślnie w trybie: {settings.environment}")

async def app_shutdown() -> None:
    """ Zwalnia zasoby przy zamykaniu aplikacji. """
    logger.info("Zamykanie aplikacji Vortex Analytica (shutdown event)...")
    # Zamknij pulę połączeń SMTP, jeśli EmailService był używany
    try:
        # Pobierz instancję EmailService, ale tylko jeśli jest zainicjalizowana
        # To wymaga poprawki w EmailService, aby można było pobrać instancję bez parametrów
        # lub globalnego zarządzania instancją. Na razie pomijamy.
        # service_instance = EmailService.get_instance() # Przykładowa metoda statyczna
        # if service_instance and hasattr(service_instance, 'close_all_connections'):
        #     service_instance.close_all_connections()
         pass
    except Exception as e:
         logger.warning(f"Błąd podczas zamykania puli połączeń EmailService: {e}", exc_info=True)

    # Opcjonalne zamknięcie Firebase App
    # if firebase_admin._apps: ... (rzadko potrzebne)

    logger.info("Aplikacja zamknięta pomyślnie.")