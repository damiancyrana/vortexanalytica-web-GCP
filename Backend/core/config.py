"""
Moduł konfiguracji aplikacji Vortex Analytica (Wersja Produkcyjna)
"""
from __future__ import annotations

import os
import logging
import time
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, Optional, Final

# Load .env file explicitly at module level
from dotenv import load_dotenv
load_dotenv()

from pydantic import field_validator, AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.cloud.secretmanager_v1.services.secret_manager_service import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """ Klasa konfiguracji aplikacji. """
    # FIXED: Proper PROJECT_ID initialization
    PROJECT_ID: str = Field(default="vortexanalytica")
    MAIL_TO: str = Field(default="vortexanalytica@gmail.com")

    # Podstawowe ustawienia
    app_name: str = "Vortex Analytica"
    environment: str = Field(default="development")  # CHANGED to development for testing
    log_level: str = Field(default="INFO")
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

    # Konfiguracja sesji - FIXED: Add default values for development
    SESSION_SECRET_KEY: Optional[str] = Field(default="development-secret-key-change-in-production-12345678901234567890")
    SESSION_SECRET_KEY_NAME: str = "SESSION_SECRET_KEY"
    SESSION_COOKIE_NAME: str = "vortex_session"
    SESSION_COOKIE_MAX_AGE: int = 14 * 24 * 60 * 60  # 14 dni
    SESSION_COOKIE_PATH: str = "/"
    SESSION_COOKIE_DOMAIN: Optional[str] = Field(None)
    SESSION_COOKIE_SECURE: bool = False  # CHANGED for development
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"  # CHANGED for development

    # Konfiguracja Redis (produkcja wymaga zmiennych środowiskowych)
    REDIS_HOST: Optional[str] = Field(default=None)
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    REDIS_DB: int = Field(default=0)
    REDIS_URL: Optional[str] = Field(default=None)
    
    # Zwiększono domyślną liczbę połączeń z Redis dla obsługi większej liczby użytkowników
    REDIS_MAX_CONNECTIONS: int = Field(default=100)
    REDIS_POOL_TIMEOUT: int = Field(default=10)
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5)
    REDIS_SOCKET_TIMEOUT: int = Field(default=5)
    
    # Konfiguracja wiadomości w Redis
    NEWS_REDIS_KEY: str = "vortex:news:messages"
    NEWS_MAX_MESSAGES: int = Field(default=100)
    NEWS_MESSAGE_TTL: int = Field(default=86400)  # 24h

    # Maksymalna liczba subskrybentów SSE jednocześnie
    MAX_SSE_SUBSCRIBERS: int = Field(default=1000)

    # Domyślne ustawienia odpowiedzi HTTP
    default_response_class: Any = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        """ Ustawienia po inicjalizacji Pydantic. """
        from fastapi.responses import HTMLResponse
        self.default_response_class = HTMLResponse
        
        # Override from environment variables if available
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", self.PROJECT_ID)
        self.MAIL_TO = os.getenv("MAIL_TO", self.MAIL_TO)
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.log_level = os.getenv("LOG_LEVEL", self.log_level).upper()
        
        # Load Redis config from environment
        self.REDIS_URL = os.getenv("REDIS_URL", self.REDIS_URL)
        self.REDIS_HOST = os.getenv("REDIS_HOST", self.REDIS_HOST)
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", str(self.REDIS_PORT)))
        self.REDIS_DB = int(os.getenv("REDIS_DB", str(self.REDIS_DB)))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", self.REDIS_PASSWORD)
        
        # Debug: Print configuration
        logger.info(f"Configuration loaded:")
        logger.info(f"  Environment: {self.environment}")
        logger.info(f"  PROJECT_ID: {self.PROJECT_ID}")
        logger.info(f"  REDIS_URL: {self.REDIS_URL}")
        logger.info(f"  REDIS_HOST: {self.REDIS_HOST}")
        logger.info(f"  REDIS_PORT: {self.REDIS_PORT}")
        
        # Walidacja Redis - tylko w produkcji
        if self.environment.lower() == "production" and not self.REDIS_URL and not self.REDIS_HOST:
            logger.error("Brak konfiguracji Redis w trybie produkcyjnym!")
            raise ValueError("REDIS_URL lub REDIS_HOST musi być ustawiony w produkcji")
        elif not self.REDIS_URL and not self.REDIS_HOST:
            logger.warning("Redis nie jest skonfigurowany - niektóre funkcje mogą nie działać")

    def _safe_subdir(self, *parts: str) -> str:
        """Safely constructs a path under base_dir to prevent traversal."""
        base = Path(self.base_dir).resolve()
        path = (base.joinpath(*parts)).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError("Unsafe path traversal detected when building path")
        return str(path)

    @property
    def templates_dir(self) -> str:
        return self._safe_subdir("Frontend", "templates")

    @property
    def static_dir(self) -> str:
        return self._safe_subdir("Frontend", "static")
    
    @property
    def is_development(self) -> bool: 
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool: 
        return self.environment.lower() == "production"
    
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
        """Ładuje WSZYSTKIE wymagane i opcjonalne sekrety - tylko w trybie produkcyjnym."""
        if self.is_development:
            logger.info("Tryb rozwojowy - pomijanie ładowania sekretów z Secret Manager")
            # Set development defaults
            if not self.SESSION_SECRET_KEY or self.SESSION_SECRET_KEY.startswith("development-"):
                self.SESSION_SECRET_KEY = "development-secret-key-change-in-production-12345678901234567890"
            
            # Set dummy values for development
            self.smtp_user = "development@example.com"
            self.smtp_pass = "development-password"
            self.firebase_api_key = "development-api-key"
            self.firebase_auth_domain = "development.firebaseapp.com"
            
            logger.info("Tryb rozwojowy skonfigurowany z domyślnymi wartościami")
            return
            
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
             if current_value is None or (attr_name == "SESSION_SECRET_KEY" and current_value.startswith("development-")):
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
            raise ValueError("SESSION_SECRET_KEY nie został pomyślnie załadowany.")
        logger.info("Konfiguracja aplikacji zainicjalizowana pomyślnie.")
        return settings
    except Exception as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji konfiguracji aplikacji: {e}", exc_info=True)
        raise SystemExit(f"Application cannot start due to configuration/secret error: {e}")