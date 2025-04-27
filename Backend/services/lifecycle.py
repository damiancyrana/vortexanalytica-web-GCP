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

from Backend.core.config import get_settings, Settings
from Backend.services.email_service import EmailService

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
            
            # Weryfikacja czy zawartość nie jest pusta
            if not firebase_key_json_str:
                logger.critical("Klucz Firebase jest pusty!")
                raise ValueError("Firebase service account key is empty")
                
            # Parsowanie JSON
            try:
                firebase_credentials_dict = json.loads(firebase_key_json_str)
            except JSONDecodeError as json_err:
                logger.critical(f"Nieprawidłowy format klucza Firebase (niepoprawny JSON): {json_err}")
                raise ValueError(f"Invalid Firebase key format (not a valid JSON): {json_err}")
            
            # Walidacja minimalnych wymaganych pól w kluczu Firebase
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [field for field in required_fields if field not in firebase_credentials_dict]
            
            if missing_fields:
                logger.critical(f"Brak wymaganych pól w kluczu Firebase: {', '.join(missing_fields)}")
                raise ValueError(f"Firebase key missing required fields: {', '.join(missing_fields)}")
            
            # Dodatkowe sprawdzenie typu konta usługowego
            if firebase_credentials_dict.get('type') != 'service_account':
                logger.critical("Niewłaściwy typ klucza Firebase: oczekiwano 'service_account'")
                raise ValueError("Invalid Firebase key type: expected 'service_account'")
            
            # Tworzenie i inicjalizacja
            cred = credentials.Certificate(firebase_credentials_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK zainicjalizowany pomyślnie.")
        else:
             logger.info("Firebase Admin SDK jest już zainicjalizowane (możliwe ponowne ładowanie uvicorn).")
    except (JSONDecodeError, ValueError, FileNotFoundError, TypeError) as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize Firebase Admin SDK: {e}") from e
    except Exception as e:
        logger.critical(f"Nieznany błąd podczas inicjalizacji Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Unexpected error initializing Firebase: {e}") from e

    logger.info(f"Aplikacja uruchomiona pomyślnie w trybie: {settings.environment}")

async def app_shutdown() -> None:
    """ Zwalnia zasoby przy zamykaniu aplikacji. """
    logger.info("Zamykanie aplikacji Vortex Analytica (shutdown event)...")
    # Zamknij pulę połączeń SMTP, jeśli EmailService był używany
    try:
        # Spróbuj uzyskać dostęp do instancji EmailService
        email_service = EmailService._instance
        if email_service and hasattr(email_service, 'close_all_connections'):
            logger.info("Zamykanie połączeń EmailService...")
            email_service.close_all_connections()
    except Exception as e:
         logger.warning(f"Błąd podczas zamykania puli połączeń EmailService: {e}", exc_info=True)

    # Spróbuj wyczyścić aplikacje Firebase, jeśli istnieją
    try:
        if firebase_admin._apps:
            logger.info("Czyszczenie aplikacji Firebase...")
            for app in list(firebase_admin._apps.values()):
                try:
                    app.delete()
                except Exception as fe:
                    logger.warning(f"Nie można wyczyścić aplikacji Firebase: {fe}")
    except Exception as e:
        logger.warning(f"Błąd podczas czyszczenia aplikacji Firebase: {e}")

    logger.info("Aplikacja zamknięta pomyślnie.")