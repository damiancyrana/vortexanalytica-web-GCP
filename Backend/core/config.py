"""
Moduł konfiguracji aplikacji Vortex Analytica (Wersja Produkcyjna)
"""
from __future__ import annotations

import os
import logging
import time
from functools import lru_cache
from typing import Dict, Any, Optional, Final

from pydantic import field_validator, AnyHttpUrl, Field
from pydantic_settings import BaseSettings
from google.cloud.secretmanager_v1.services.secret_manager_service import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """ Klasa konfiguracji aplikacji. """
    # Stałe aplikacji
    PROJECT_ID: Final[str] = os.getenv("GOOGLE_CLOUD_PROJECT", "vortexanalytica")
    MAIL_TO: Final[str] = os.getenv("MAIL_TO", "vortexanalytica@gmail.com")

    # Podstawowe ustawienia
    app_name: str = "Vortex Analytica"
    environment: str = "production"
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    base_url: Optional[AnyHttpUrl] = Field(None)

    # Ścieżki do katalogów
    base_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Cache dla serwisów
    _secret_manager: Optional[SecretManagerServiceClient] = None
    
    # Cache dla sekretów z TTL
    _secrets_cache: Dict[str, Dict[str, Any]] = {}
    _secrets_ttl: int = 3600  # 1 godzina

    # Zmienne uwierzytelniane
    smtp_user: Optional[str] = Field(None)
    smtp_pass: Optional[str] = Field(None)
    firebase_api_key: Optional[str] = Field(None)
    firebase_auth_domain: Optional[str] = Field(None)
    firebase_service_account_secret_id: str = "firebase-service-account-key-json"

    # Konfiguracja sesji
    SESSION_SECRET_KEY: Optional[str] = Field(None)
    SESSION_SECRET_KEY_NAME: str = "SESSION_SECRET_KEY"
    SESSION_COOKIE_NAME: str = "vortex_session"
    SESSION_COOKIE_MAX_AGE: int = 14 * 24 * 60 * 60  # 14 dni
    SESSION_COOKIE_PATH: str = "/"
    SESSION_COOKIE_DOMAIN: Optional[str] = Field(None)
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    # Konfiguracja Redis (produkcja wymaga zmiennych środowiskowych)
    REDIS_HOST: str = Field(default=None, env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_PASSWORD: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")
    REDIS_MAX_CONNECTIONS: int = Field(default=20, env="REDIS_MAX_CONNECTIONS")
    REDIS_POOL_TIMEOUT: int = Field(default=10, env="REDIS_POOL_TIMEOUT")
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5, env="REDIS_SOCKET_CONNECT_TIMEOUT")
    REDIS_SOCKET_TIMEOUT: int = Field(default=5, env="REDIS_SOCKET_TIMEOUT")
    
    # Konfiguracja wiadomości w Redis
    NEWS_REDIS_KEY: str = "vortex:news:messages"
    NEWS_MAX_MESSAGES: int = Field(default=100, env="NEWS_MAX_MESSAGES")
    NEWS_MESSAGE_TTL: int = Field(default=86400, env="NEWS_MESSAGE_TTL")  # 24h

    # Domyślne ustawienia odpowiedzi HTTP
    default_response_class: Any = None

    model_config = {
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }

    def model_post_init(self, __context: Any) -> None:
        """ Ustawienia po inicjalizacji Pydantic. """
        from fastapi.responses import HTMLResponse
        self.default_response_class = HTMLResponse
        
        # Walidacja Redis w produkcji
        if not self.REDIS_URL and not self.REDIS_HOST:
            raise ValueError("REDIS_URL lub REDIS_HOST musi być ustawiony w produkcji")

    @property
    def templates_dir(self) -> str: 
        return os.path.join(self.base_dir, "Frontend", "templates")
    
    @property
    def static_dir(self) -> str: 
        return os.path.join(self.base_dir, "Frontend", "static")
    
    @property
    def is_development(self) -> bool: 
        return False
    
    @property
    def is_production(self) -> bool: 
        return True
    
    @property
    def secret_manager_client(self) -> SecretManagerServiceClient:
        """ Zwraca klienta Secret Managera, inicjalizując go raz. """
        if getattr(self, '_secret_manager', None) is None:
            logger.info("Inicjalizacja klienta Google Secret Manager...")
            try:
                self._secret_manager = SecretManagerServiceClient()
                logger.info("Klient Secret Manager zainicjalizowany.")
            except Exception as e:
                 logger.critical(f"Nie można zainicjalizować klienta Secret Manager: {e}", exc_info=True)
                 raise RuntimeError("Failed to initialize Secret Manager client") from e
        return self._secret_manager

    def get_secret(self, secret_id: str, force_refresh: bool = False) -> str:
        """ 
        Pobiera najnowszą wersję sekretu z GCP Secret Manager z mechanizmem pamięci podręcznej. 
        """
        if not secret_id:
            logger.error("Próba pobrania sekretu bez podania ID.")
            raise ValueError("Secret ID cannot be empty.")
        if not self.PROJECT_ID:
             logger.error("PROJECT_ID nie jest ustawiony w konfiguracji.")
             raise ValueError("PROJECT_ID must be set to fetch secrets.")

        now = time.time()
        
        # Sprawdź cache
        if not force_refresh and secret_id in self._secrets_cache:
            cache_entry = self._secrets_cache[secret_id]
            if now - cache_entry['timestamp'] < self._secrets_ttl:
                return cache_entry['value']

        # Pobierz nową wartość z Secret Manager
        name = f"projects/{self.PROJECT_ID}/secrets/{secret_id}/versions/latest"
        try:
            client = self.secret_manager_client
            response = client.access_secret_version(name=name)
            secret_value = response.payload.data.decode("UTF-8")
            if not secret_value:
                 logger.error(f"Pobrana wartość sekretu '{secret_id}' jest pusta!")
                 raise ValueError(f"Secret '{secret_id}' value is empty.")
                 
            # Dodaj do cache
            self._secrets_cache[secret_id] = {
                'value': secret_value,
                'timestamp': now
            }
            
            return secret_value
        except (NotFound, PermissionDenied) as e:
             logger.error(f"Nie można uzyskać dostępu do sekretu '{secret_id}': {e}")
             raise ValueError(f"Could not access secret '{secret_id}'. Check name and permissions.") from e
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania sekretu '{secret_id}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to fetch secret '{secret_id}'.") from e
            
    def clear_secrets_cache(self, secret_id: Optional[str] = None) -> None:
        """Czyści pamięć podręczną sekretów."""
        if secret_id:
            if secret_id in self._secrets_cache:
                del self._secrets_cache[secret_id]
        else:
            self._secrets_cache.clear()

    def load_secrets(self) -> None:
        """Ładuje WSZYSTKIE wymagane i opcjonalne sekrety."""
        logger.info("Rozpoczynanie ładowania sekretów...")
        secrets_to_load = {
            "SESSION_SECRET_KEY": (self.SESSION_SECRET_KEY_NAME, True),
            "smtp_user": ("smtp-user", False),
            "smtp_pass": ("smtp-pass", False),
            "firebase_api_key": ("Identity-Platform-apiKey", False),
            "firebase_auth_domain": ("Identity-Platform-authDomain", False),
        }
        all_loaded = True
        for attr_name, (secret_id, is_required) in secrets_to_load.items():
             current_value = getattr(self, attr_name, None)
             if current_value is None:
                try:
                    secret_value = self.get_secret(secret_id)
                    setattr(self, attr_name, secret_value)
                    logger.info(f"Załadowano sekret dla '{attr_name}' z '{secret_id}'.")
                    if attr_name == "SESSION_SECRET_KEY" and len(secret_value) < 32:
                        logger.critical(f"Załadowany {secret_id} jest zbyt krótki!")
                        raise ValueError(f"Loaded secret '{secret_id}' is too short (minimum 32 bytes).")
                except Exception as e:
                     log_level = logging.CRITICAL if is_required else logging.WARNING
                     log_func = logger.critical if is_required else logger.warning
                     log_func(f"Nie udało się załadować {'WYMAGANEGO' if is_required else 'opcjonalnego'} sekretu dla '{attr_name}' z '{secret_id}': {e}")
                     if is_required:
                         all_loaded = False
        if not all_loaded:
             logger.critical("Nie udało się załadować wszystkich wymaganych sekretów.")
             raise ValueError("Failed to load one or more required secrets from Secret Manager.")
        logger.info("Zakończono ładowanie sekretów.")


@lru_cache()
def get_settings() -> Settings:
    """ Tworzy i zwraca obiekt konfiguracji. Ładuje sekrety. """
    logger.info("Inicjalizacja konfiguracji aplikacji...")
    try:
        settings = Settings()
        settings.load_secrets()
        if not settings.SESSION_SECRET_KEY:
            raise ValueError("SESSION_SECRET_KEY nie został pomyślnie załadowany z Secret Manager.")
        logger.info("Konfiguracja aplikacji zainicjalizowana pomyślnie.")
        return settings
    except Exception as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji konfiguracji aplikacji: {e}", exc_info=True)
        raise SystemExit(f"Application cannot start due to configuration/secret error: {e}")
    