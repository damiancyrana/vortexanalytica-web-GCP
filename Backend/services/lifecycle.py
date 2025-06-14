"""
Moduł cyklu życia aplikacji (Wersja Produkcyjna).
Inicjalizuje Firebase Admin SDK, serwis Pub/Sub oraz Redis.
"""
from __future__ import annotations

import logging
import orjson
from orjson import JSONDecodeError

import firebase_admin
from firebase_admin import credentials

from Backend.core.config import get_settings, Settings
from Backend.services.email_service import EmailService
from Backend.services.pubsub_service import PubSubService
from Backend.services.news_service import NewsService

logger = logging.getLogger(__name__)

# Zmienne do przechowywania instancji serwisów globalnie
_pubsub_service = None
_news_service = None


async def app_startup() -> None:
    """ Inicjalizuje serwisy przy starcie aplikacji. """
    global _pubsub_service, _news_service
    
    logger.info("Uruchamianie aplikacji Vortex Analytica...")
    try:
        settings = get_settings()
    except Exception as e:
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
                firebase_credentials_dict = orjson.loads(firebase_key_json_str)
            except JSONDecodeError as json_err:
                logger.critical(f"Nieprawidłowy format klucza Firebase: {json_err}")
                raise ValueError(f"Invalid Firebase key format: {json_err}")
            
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
             logger.info("Firebase Admin SDK jest już zainicjalizowane.")
    except (JSONDecodeError, ValueError, FileNotFoundError, TypeError) as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize Firebase Admin SDK: {e}") from e
    except Exception as e:
        logger.critical(f"Nieznany błąd podczas inicjalizacji Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Unexpected error initializing Firebase: {e}") from e

    # Inicjalizacja NewsService z Redis
    try:
        logger.info("Inicjalizacja NewsService z Redis...")
        _news_service = NewsService()
        
        # Test podstawowych operacji Redis (asynchroniczny)
        test_count = await _news_service.get_messages_count()
        logger.info(f"Połączenie z Redis sprawdzone. Wiadomości w bazie: {test_count}")
        
        # Opcjonalne: wyczyść stare wiadomości przy starcie
        cleaned_count = await _news_service.cleanup_old_messages(max_age_seconds=7 * 24 * 3600)  # 7 dni
        if cleaned_count > 0:
            logger.info(f"Wyczyszczono {cleaned_count} starych wiadomości przy starcie")
            
    except Exception as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji NewsService z Redis: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize NewsService with Redis: {e}") from e


    # Initialize NarrativeService and load existing messages
    try:
        logger.info("Initializing NarrativeService...")
        from Backend.services.narrative_service import NarrativeService
        narrative_service = NarrativeService()
        
        # Load recent messages into narrative clustering
        logger.info("Loading existing messages into narrative clusters...")
        recent_messages = await _news_service.get_messages(limit=200)
        
        processed_count = 0
        for message in recent_messages:
            try:
                await narrative_service.add_message(message)
                processed_count += 1
            except Exception as e:
                logger.warning(f"Could not add message to narratives: {e}")
        
        logger.info(f"Loaded {processed_count} messages into narrative clusters")
        
        # Get initial stats
        active_narratives = await narrative_service.get_active_narratives(limit=10)
        logger.info(f"Active narratives: {len(active_narratives)}")
        
    except Exception as e:
        logger.error(f"Error initializing NarrativeService: {e}")
        # Non-critical, continue startup


    # Inicjalizacja Pub/Sub Service
    try:
        logger.info("Inicjalizacja serwisu Pub/Sub...")
        _pubsub_service = PubSubService(settings)
        
        # Uruchom nasłuchiwanie asynchronicznie dla obu topiców
        if await _pubsub_service.start_listener_async():
            logger.info("Serwis Pub/Sub uruchomiony pomyślnie (standard + critical).")
        else:
            logger.warning("Nie udało się uruchomić nasłuchiwania Pub/Sub, ale aplikacja kontynuuje działanie.")
    except Exception as e:
        logger.error(f"Błąd podczas inicjalizacji serwisu Pub/Sub: {e}", exc_info=True)
        logger.warning("Aplikacja będzie kontynuować działanie bez serwisu Pub/Sub.")
    
    logger.info(f"Aplikacja uruchomiona pomyślnie w trybie: {settings.environment}")

    
async def app_shutdown() -> None:
    """ Zwalnia zasoby przy zamykaniu aplikacji. """
    global _pubsub_service, _news_service
    
    logger.info("Zamykanie aplikacji Vortex Analytica...")
    
    # Zatrzymaj serwis Pub/Sub
    if _pubsub_service:
        try:
            logger.info("Zatrzymywanie serwisu Pub/Sub...")
            await _pubsub_service.stop_listener_async()
        except Exception as e:
            logger.warning(f"Błąd podczas zatrzymywania serwisu Pub/Sub: {e}", exc_info=True)
    
    # Zamknij połączenia Redis w NewsService
    if _news_service:
        try:
            logger.info("Zamykanie połączeń Redis w NewsService...")
            await _news_service.close_connections()
        except Exception as e:
            logger.warning(f"Błąd podczas zamykania połączeń Redis: {e}", exc_info=True)
    

    # Close NarrativeService connections
    try:
        from Backend.services.narrative_service import NarrativeService
        narrative_service = NarrativeService._instance
        if narrative_service:
            logger.info("Closing NarrativeService connections...")
            await narrative_service.close_connections()
    except Exception as e:
        logger.warning(f"Error closing NarrativeService connections: {e}")


    # Zamknij pulę połączeń SMTP, jeśli EmailService był używany
    try:
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
