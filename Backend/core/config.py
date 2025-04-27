"""
Moduł konfiguracji aplikacji Vortex Analytica (Wersja Produkcyjna - Hybrydowa)
Dostosowany do Pydantic v2.x
Klucz Firebase ładowany z Secret Managera.
Klucz Sesji (SESSION_SECRET_KEY) ładowany WYŁĄCZNIE z Secret Managera.
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
    PROJECT_ID: Final[str] = os.getenv("GOOGLE_CLOUD_PROJECT", "vortexanalytica") # Pobierz z env, jeśli dostępne
    MAIL_TO: Final[str] = "vortexanalytica@gmail.com" # Można też wczytać z env/secret

    # Podstawowe ustawienia
    app_name: str = "Vortex Analytica"
    environment: str = os.getenv("ENVIRONMENT", "production") # Domyślnie produkcja
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    base_url: Optional[AnyHttpUrl] = Field(None) # Wczytaj z env, jeśli potrzebne (np. BASE_URL=...)

    # Ścieżki do katalogów (mogą wymagać dostosowania w kontenerze)
    base_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Cache dla serwisów (inicjalizowany w property)
    _secret_manager: Optional[SecretManagerServiceClient] = None
    
    # Cache dla sekretów z TTL
    _secrets_cache: Dict[str, Dict[str, Any]] = {}
    _secrets_ttl: int = 3600  # Czas życia cache w sekundach (1h)

    # Zmienne uwierzytelniane (cache z Secret Managera)
    smtp_user: Optional[str] = Field(None)
    smtp_pass: Optional[str] = Field(None)
    firebase_api_key: Optional[str] = Field(None)
    firebase_auth_domain: Optional[str] = Field(None)
    firebase_service_account_secret_id: str = "firebase-service-account-key-json"

    # Konfiguracja sesji - klucz ładowany z Secret Managera
    SESSION_SECRET_KEY: Optional[str] = Field(None) # Ładowany w load_secrets
    SESSION_SECRET_KEY_NAME: str = "SESSION_SECRET_KEY" # Nazwa sekretu w Secret Manager
    SESSION_COOKIE_NAME: str = "vortex_session"
    SESSION_COOKIE_MAX_AGE: int = 14 * 24 * 60 * 60  # 14 dni
    SESSION_COOKIE_PATH: str = "/"
    SESSION_COOKIE_DOMAIN: Optional[str] = Field(None) # Ustaw, jeśli potrzebujesz dla subdomen
    SESSION_COOKIE_SECURE: bool = True # Na produkcji ZAWSZE True
    SESSION_COOKIE_HTTPONLY: bool = True # ZAWSZE True
    SESSION_COOKIE_SAMESITE: str = "lax" # "lax" jest dobrym kompromisem, "strict" bezpieczniejszy, ale może psuć niektóre przepływy

    # Domyślne ustawienia odpowiedzi HTTP
    default_response_class: Any = None

    model_config = {
        "env_file": ".env", # Dla lokalnego developmentu
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }

    def model_post_init(self, __context: Any) -> None:
        """ Ustawienia po inicjalizacji Pydantic. """
        from fastapi.responses import HTMLResponse
        self.default_response_class = HTMLResponse
        # Wymuś Secure=True na produkcji
        if self.is_production:
            self.SESSION_COOKIE_SECURE = True
        else:
            # Dostosuj logikę dla dev, jeśli konieczne (np. testy na HTTP)
            base_url_str = str(self.base_url) if self.base_url else ""
            if self.environment == "development" and ("http://localhost" in base_url_str or "http://127.0.0.1" in base_url_str):
                 logger.warning("Uruchomiono w trybie deweloperskim na HTTP, ustawiam SESSION_COOKIE_SECURE=False.")
                 self.SESSION_COOKIE_SECURE = False
            else:
                 # Nawet w dev, jeśli nie jest to localhost http, używaj Secure
                 self.SESSION_COOKIE_SECURE = True


    @property
    def templates_dir(self) -> str: return os.path.join(self.base_dir, "Frontend", "templates")
    @property
    def static_dir(self) -> str: return os.path.join(self.base_dir, "Frontend", "static")
    @property
    def is_development(self) -> bool: return self.environment.lower() == "development"
    @property
    def is_production(self) -> bool: return self.environment.lower() == "production"
    @property
    def secret_manager_client(self) -> SecretManagerServiceClient:
        """ Zwraca klienta Secret Managera, inicjalizując go raz. """
        if getattr(self, '_secret_manager', None) is None:
            logger.info("Inicjalizacja klienta Google Secret Manager...")
            try:
                # Klient użyje domyślnych poświadczeń środowiska (np. konta usługi Cloud Run)
                self._secret_manager = SecretManagerServiceClient()
                logger.info("Klient Secret Manager zainicjalizowany.")
            except Exception as e:
                 logger.critical(f"Nie można zainicjalizować klienta Secret Manager: {e}", exc_info=True)
                 raise RuntimeError("Failed to initialize Secret Manager client") from e
        return self._secret_manager

    def get_secret(self, secret_id: str, force_refresh: bool = False) -> str:
        """ 
        Pobiera najnowszą wersję sekretu z GCP Secret Manager z mechanizmem pamięci podręcznej. 
        
        Args:
            secret_id: Identyfikator sekretu w Secret Manager.
            force_refresh: Wymusza pobranie sekretu z Secret Manager niezależnie od stanu cache.
            
        Returns:
            Wartość sekretu jako ciąg znaków.
        """
        if not secret_id:
            logger.error("Próba pobrania sekretu bez podania ID.")
            raise ValueError("Secret ID cannot be empty.")
        if not self.PROJECT_ID:
             logger.error("PROJECT_ID nie jest ustawiony w konfiguracji. Nie można pobrać sekretu.")
             raise ValueError("PROJECT_ID must be set to fetch secrets.")

        now = time.time()
        
        # Sprawdź czy sekret jest w cache i czy nie wygasł
        if not force_refresh and secret_id in self._secrets_cache:
            cache_entry = self._secrets_cache[secret_id]
            if now - cache_entry['timestamp'] < self._secrets_ttl:
                logger.debug(f"Pobieranie sekretu '{secret_id}' z pamięci podręcznej.")
                return cache_entry['value']
            else:
                logger.debug(f"Sekret '{secret_id}' wygasł w pamięci podręcznej (TTL: {self._secrets_ttl}s).")

        # Pobierz nową wartość z Secret Manager
        name = f"projects/{self.PROJECT_ID}/secrets/{secret_id}/versions/latest"
        logger.debug(f"Pobieranie sekretu z Secret Manager: {name}")
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
            
            logger.debug(f"Pomyślnie pobrano sekret '{secret_id}' i dodano do pamięci podręcznej.")
            return secret_value
        except (NotFound, PermissionDenied) as e:
             logger.error(f"Nie można uzyskać dostępu do sekretu '{secret_id}' (NotFound lub PermissionDenied): {e}")
             raise ValueError(f"Could not access secret '{secret_id}'. Check name and permissions.") from e
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania sekretu '{secret_id}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to fetch secret '{secret_id}'.") from e
            
    def clear_secrets_cache(self, secret_id: Optional[str] = None) -> None:
        """
        Czyści pamięć podręczną sekretów.
        
        Args:
            secret_id: Jeśli podano, czyści tylko konkretny sekret. W przeciwnym razie czyści całą pamięć podręczną.
        """
        if secret_id:
            if secret_id in self._secrets_cache:
                del self._secrets_cache[secret_id]
                logger.debug(f"Usunięto sekret '{secret_id}' z pamięci podręcznej.")
        else:
            self._secrets_cache.clear()
            logger.debug("Wyczyszczono całą pamięć podręczną sekretów.")

    def load_secrets(self) -> None:
        """Ładuje WSZYSTKIE wymagane i opcjonalne sekrety (SMTP, Firebase API, Session Key)."""
        logger.info("Rozpoczynanie ładowania sekretów...")
        secrets_to_load = {
            "SESSION_SECRET_KEY": (self.SESSION_SECRET_KEY_NAME, True), # Wymagany
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
                    # Pobierz z sekretu (używa mechanizmu cache)
                    secret_value = self.get_secret(secret_id)
                    setattr(self, attr_name, secret_value)
                    logger.info(f"Załadowano sekret dla '{attr_name}' z '{secret_id}'.")
                    if attr_name == "SESSION_SECRET_KEY" and len(secret_value) < 32:
                        logger.critical(f"Załadowany {secret_id} jest zbyt krótki! Bezpieczeństwo zagrożone.")
                        raise ValueError(f"Loaded secret '{secret_id}' is too short (minimum 32 bytes).")
                except Exception as e:
                     log_level = logging.CRITICAL if is_required else logging.WARNING
                     log_func = logger.critical if is_required else logger.warning
                     log_func(f"Nie udało się załadować {'WYMAGANEGO' if is_required else 'opcjonalnego'} sekretu dla '{attr_name}' z '{secret_id}': {e}")
                     if is_required:
                         all_loaded = False # Oznacz, że wystąpił błąd krytyczny
                         # Nie rzucamy tutaj błędu, aby spróbować załadować inne, logujemy na końcu
        if not all_loaded:
             logger.critical("Nie udało się załadować wszystkich wymaganych sekretów. Aplikacja nie może bezpiecznie wystartować.")
             raise ValueError("Failed to load one or more required secrets from Secret Manager.")
        logger.info("Zakończono ładowanie sekretów.")


@lru_cache()
def get_settings() -> Settings:
    """ Tworzy i zwraca obiekt konfiguracji. Ładuje sekrety. """
    logger.info("Inicjalizacja konfiguracji aplikacji (get_settings)...")
    try:
        settings = Settings()
        settings.load_secrets() # Ładujemy WSZYSTKIE sekrety tutaj
        if not settings.SESSION_SECRET_KEY: # Ostateczne sprawdzenie
            raise ValueError("SESSION_SECRET_KEY nie został pomyślnie załadowany z Secret Manager.")
        logger.info("Konfiguracja aplikacji zainicjalizowana pomyślnie.")
        return settings
    except Exception as e:
        logger.critical(f"Krytyczny błąd podczas inicjalizacji konfiguracji aplikacji: {e}", exc_info=True)
        raise SystemExit(f"Application cannot start due to configuration/secret error: {e}")