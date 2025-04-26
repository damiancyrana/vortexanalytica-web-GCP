"""
Moduł konfiguracji aplikacji Vortex Analytica
Dostosowany do Pydantic v2.x
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Any, Optional, Final

# Zmodyfikowane importy dla zgodności z Pydantic v2
from pydantic import field_validator, AnyHttpUrl
from pydantic_settings import BaseSettings
from google.cloud.secretmanager_v1.services.secret_manager_service import SecretManagerServiceClient


class Settings(BaseSettings):
    """
    Klasa konfiguracji aplikacji bazująca na Pydantic.
    Automatycznie ładuje zmienne środowiskowe i zapewnia walidację.
    """
    # Stałe aplikacji
    PROJECT_ID: Final[str] = "vortexanalytica"
    MAIL_TO: Final[str] = "vortexanalytica@gmail.com"
    
    # Podstawowe ustawienia
    app_name: str = "Vortex Analytica"
    environment: str = os.getenv("ENVIRONMENT", "development")
    base_url: Optional[AnyHttpUrl] = None
    
    # Ścieżki do katalogów
    base_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    # Cache dla serwisów
    _secret_manager: Optional[SecretManagerServiceClient] = None
    
    # Zmienne uwierzytelniane (cache z Secret Managera)
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    firebase_api_key: Optional[str] = None
    firebase_auth_domain: Optional[str] = None
    
    # Domyślne ustawienia odpowiedzi HTTP
    default_response_class: Any = None  # Będzie ustawione podczas inicjalizacji
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }
    
    def model_post_init(self, __context: Any) -> None:
        """
        Metoda wywoływana po inicjalizacji modelu.
        W Pydantic v2 zastępuje __post_init_post_parse__
        """
        # Import lokalny, aby uniknąć cyklicznych zależności
        from fastapi.responses import HTMLResponse
        self.default_response_class = HTMLResponse
    
    @property
    def templates_dir(self) -> str:
        """Zwraca ścieżkę do katalogu z szablonami"""
        return os.path.join(self.base_dir, "Frontend", "templates")
    
    @property
    def static_dir(self) -> str:
        """Zwraca ścieżkę do katalogu ze statycznymi plikami"""
        return os.path.join(self.base_dir, "Frontend", "static")
    
    @property
    def is_development(self) -> bool:
        """Sprawdza czy aplikacja działa w trybie deweloperskim"""
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Sprawdza czy aplikacja działa w trybie produkcyjnym"""
        return self.environment.lower() == "production"
    
    @property
    def secret_manager_client(self) -> SecretManagerServiceClient:
        """
        Zwraca klienta Secret Managera (tworzy go tylko raz)
        W Pydantic v2 nie możemy używać _client jako ClassVar,
        więc używamy zmiennej instancji
        """
        if not hasattr(self, '_secret_manager') or self._secret_manager is None:
            # Używamy innej nazwy, aby uniknąć konfliktu
            self._secret_manager = SecretManagerServiceClient()
        return self._secret_manager
    
    def get_secret(self, secret_id: str) -> str:
        """
        Pobiera sekret z GCP Secret Manager.
        Implementacja z cache dla lepszej wydajności.
        """
        name = f"projects/{self.PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = self.secret_manager_client.access_secret_version(name=name)
        return response.payload.data.decode()
    
    def load_secrets(self) -> None:
        """Ładuje sekrety z Secret Managera do pamięci, jeśli nie są ustawione"""
        # Ładujemy tylko te sekrety, które nie są jeszcze ustawione
        if self.smtp_user is None:
            try:
                self.smtp_user = self.get_secret("smtp-user")
            except Exception as e:
                import logging
                logging.error(f"Błąd pobierania sekretu smtp-user: {e}")
                
        if self.smtp_pass is None:
            try:
                self.smtp_pass = self.get_secret("smtp-pass")
            except Exception as e:
                import logging
                logging.error(f"Błąd pobierania sekretu smtp-pass: {e}")
                
        if self.firebase_api_key is None:
            try:
                self.firebase_api_key = self.get_secret("Identity-Platform-apiKey")
            except Exception as e:
                import logging
                logging.error(f"Błąd pobierania sekretu Identity-Platform-apiKey: {e}")
                
        if self.firebase_auth_domain is None:
            try:
                self.firebase_auth_domain = self.get_secret("Identity-Platform-authDomain")
            except Exception as e:
                import logging
                logging.error(f"Błąd pobierania sekretu Identity-Platform-authDomain: {e}")


@lru_cache
def get_settings() -> Settings:
    """
    Tworzy i zwraca obiekt konfiguracji z cache.
    Wzorzec Singleton zapewnia, że konfiguracja jest tworzona tylko raz.
    
    Returns:
        Settings: Instancja konfiguracji aplikacji
    """
    settings = Settings()
    # Ładujemy sekrety tylko w produkcji lub na żądanie
    if settings.is_production:
        settings.load_secrets()
    return settings