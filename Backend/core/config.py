"""
Configuration module for Vortex Analytica application (Production Only).
"""
from __future__ import annotations

import os
import logging
import time
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, Optional

from pydantic import field_validator, AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.cloud.secretmanager_v1.services.secret_manager_service import SecretManagerServiceClient
from google.api_core.exceptions import NotFound, PermissionDenied

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application configuration class - Production Only."""
    # Core settings
    PROJECT_ID: str = Field(default="vortexanalytica")
    MAIL_TO: str = Field(default="vortexanalytica@gmail.com")
    
    # Basic settings
    app_name: str = "Vortex Analytica"
    log_level: str = Field(default="INFO")
    base_url: Optional[AnyHttpUrl] = Field(None)
    
    # Directory paths
    base_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Secret Manager cache
    _secret_manager: Optional[SecretManagerServiceClient] = None
    _secrets_cache: Dict[str, Dict[str, Any]] = {}
    _secrets_ttl: int = 3600  # 1 hour
    
    # Authentication variables (loaded from Secret Manager)
    smtp_user: Optional[str] = Field(None)
    smtp_pass: Optional[str] = Field(None)
    firebase_api_key: Optional[str] = Field(None)
    firebase_auth_domain: Optional[str] = Field(None)
    firebase_service_account_secret_id: str = "firebase-service-account-key-json"
    
    # Session configuration
    SESSION_SECRET_KEY: Optional[str] = Field(None)
    SESSION_COOKIE_NAME: str = "vortex_session"
    SESSION_COOKIE_MAX_AGE: int = 14 * 24 * 60 * 60  # 14 days
    SESSION_COOKIE_PATH: str = "/"
    SESSION_COOKIE_DOMAIN: Optional[str] = Field(None)
    SESSION_COOKIE_SECURE: bool = True  # Always secure in production
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"  # Strict in production
    
    # Redis configuration
    REDIS_HOST: Optional[str] = Field(default=None)
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: Optional[str] = Field(default=None)
    REDIS_DB: int = Field(default=0)
    REDIS_URL: Optional[str] = Field(default=None)
    
    # Redis connection pool settings
    REDIS_MAX_CONNECTIONS: int = Field(default=100)
    REDIS_POOL_TIMEOUT: int = Field(default=10)
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5)
    REDIS_SOCKET_TIMEOUT: int = Field(default=5)
    
    # News message configuration
    NEWS_REDIS_KEY: str = "vortex:news:messages"
    NEWS_MAX_MESSAGES: int = Field(default=100)
    NEWS_MESSAGE_TTL: int = Field(default=86400)  # 24h
    
    # SSE configuration
    MAX_SSE_SUBSCRIBERS: int = Field(default=1000)
    
    # HTTP response settings
    default_response_class: Any = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    def model_post_init(self, __context: Any) -> None:
        """Post-initialization settings."""
        from fastapi.responses import HTMLResponse
        self.default_response_class = HTMLResponse
        
        # Override from environment variables if available
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", self.PROJECT_ID)
        self.MAIL_TO = os.getenv("MAIL_TO", self.MAIL_TO)
        self.log_level = os.getenv("LOG_LEVEL", self.log_level).upper()
        
        # Load Redis config from environment
        self.REDIS_URL = os.getenv("REDIS_URL", self.REDIS_URL)
        self.REDIS_HOST = os.getenv("REDIS_HOST", self.REDIS_HOST)
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", str(self.REDIS_PORT)))
        self.REDIS_DB = int(os.getenv("REDIS_DB", str(self.REDIS_DB)))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", self.REDIS_PASSWORD)
        
        logger.info(f"Configuration loaded:")
        logger.info(f"  PROJECT_ID: {self.PROJECT_ID}")
        logger.info(f"  REDIS_URL: {self.REDIS_URL}")
        logger.info(f"  REDIS_HOST: {self.REDIS_HOST}")
        logger.info(f"  REDIS_PORT: {self.REDIS_PORT}")
        
        # Validate Redis configuration - required in production
        if not self.REDIS_URL and not self.REDIS_HOST:
            logger.error("Redis configuration missing!")
            raise ValueError("REDIS_URL or REDIS_HOST must be set")
    
    def _safe_subdir(self, *parts: str) -> str:
        """Safely constructs a path under base_dir to prevent traversal."""
        base = Path(self.base_dir).resolve()
        path = (base.joinpath(*parts)).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError("Unsafe path traversal detected")
        return str(path)
    
    @property
    def templates_dir(self) -> str:
        return self._safe_subdir("Frontend", "templates")
    
    @property
    def static_dir(self) -> str:
        return self._safe_subdir("Frontend", "static")
    
    @property
    def is_production(self) -> bool:
        """Returns True if running in production mode."""
        environment = os.getenv("ENVIRONMENT", "production").lower()
        return environment == "production"
    
    @property
    def secret_manager_client(self) -> SecretManagerServiceClient:
        """Returns Secret Manager client, initializing it once."""
        if getattr(self, '_secret_manager', None) is None:
            logger.info("Initializing Google Secret Manager client...")
            try:
                self._secret_manager = SecretManagerServiceClient()
                logger.info("Secret Manager client initialized.")
            except Exception as e:
                logger.critical(f"Failed to initialize Secret Manager client: {e}", exc_info=True)
                raise RuntimeError("Failed to initialize Secret Manager client") from e
        return self._secret_manager
    
    def get_secret(self, secret_id: str, force_refresh: bool = False) -> str:
        """
        Fetches the latest version of a secret from GCP Secret Manager with caching.
        """
        if not secret_id:
            logger.error("Attempt to fetch secret without ID.")
            raise ValueError("Secret ID cannot be empty.")
        if not self.PROJECT_ID:
            logger.error("PROJECT_ID not set in configuration.")
            raise ValueError("PROJECT_ID must be set to fetch secrets.")
        
        now = time.time()
        
        # Check cache
        if not force_refresh and secret_id in self._secrets_cache:
            cache_entry = self._secrets_cache[secret_id]
            if now - cache_entry['timestamp'] < self._secrets_ttl:
                return cache_entry['value']
        
        # Fetch new value from Secret Manager
        name = f"projects/{self.PROJECT_ID}/secrets/{secret_id}/versions/latest"
        try:
            client = self.secret_manager_client
            response = client.access_secret_version(name=name)
            secret_value = response.payload.data.decode("UTF-8")
            if not secret_value:
                logger.error(f"Secret '{secret_id}' value is empty!")
                raise ValueError(f"Secret '{secret_id}' value is empty.")
            
            # Add to cache
            self._secrets_cache[secret_id] = {
                'value': secret_value,
                'timestamp': now
            }
            
            return secret_value
        except (NotFound, PermissionDenied) as e:
            logger.error(f"Cannot access secret '{secret_id}': {e}")
            raise ValueError(f"Could not access secret '{secret_id}'. Check name and permissions.") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching secret '{secret_id}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to fetch secret '{secret_id}'.") from e
    
    def clear_secrets_cache(self, secret_id: Optional[str] = None) -> None:
        """Clears the secrets cache."""
        if secret_id:
            if secret_id in self._secrets_cache:
                del self._secrets_cache[secret_id]
        else:
            self._secrets_cache.clear()
    
    def load_secrets(self) -> None:
        """Loads all required secrets from Secret Manager or environment variables in development."""
        environment = os.getenv("ENVIRONMENT", "production").lower()

        if environment == "development":
            logger.info("Development mode detected - loading secrets from environment variables...")
            self._load_secrets_from_env()
        else:
            logger.info("Loading secrets from Secret Manager...")
            self._load_secrets_from_gcp()

    def _load_secrets_from_env(self) -> None:
        """Loads secrets from environment variables for development."""
        secrets_mapping = {
            "SESSION_SECRET_KEY": "SESSION_SECRET_KEY",
            "smtp_user": "SMTP_USER",
            "smtp_pass": "SMTP_PASS",
            "firebase_api_key": "FIREBASE_API_KEY",
            "firebase_auth_domain": "FIREBASE_AUTH_DOMAIN",
        }

        for attr_name, env_var in secrets_mapping.items():
            value = os.getenv(env_var)
            if value:
                setattr(self, attr_name, value)
                logger.info(f"Loaded '{attr_name}' from environment variable.")
            elif attr_name == "SESSION_SECRET_KEY":
                logger.error(f"Required environment variable {env_var} not set!")
                raise ValueError(f"Environment variable {env_var} is required in development mode.")

        logger.info("Finished loading secrets.")

    def _load_secrets_from_gcp(self) -> None:
        """Loads secrets from Google Secret Manager for production."""
        secrets_to_load = {
            "SESSION_SECRET_KEY": ("SESSION_SECRET_KEY", True),  # Using same name as the attribute
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
                    logger.info(f"Loaded secret for '{attr_name}' from '{secret_id}'.")
                    
                    if attr_name == "SESSION_SECRET_KEY" and len(secret_value) < 32:
                        logger.critical(f"Loaded {secret_id} is too short!")
                        raise ValueError(f"Secret '{secret_id}' is too short (minimum 32 bytes).")
                except Exception as e:
                    log_level = logging.CRITICAL if is_required else logging.WARNING
                    log_func = logger.critical if is_required else logger.warning
                    log_func(f"Failed to load {'REQUIRED' if is_required else 'optional'} secret for '{attr_name}' from '{secret_id}': {e}")
                    if is_required:
                        all_loaded = False
        
        if not all_loaded:
            logger.critical("Failed to load all required secrets.")
            raise ValueError("Failed to load one or more required secrets from Secret Manager.")
        
        logger.info("Finished loading secrets.")


@lru_cache()
def get_settings() -> Settings:
    """Creates and returns configuration object. Loads secrets."""
    logger.info("Initializing application configuration...")
    try:
        settings = Settings()
        settings.load_secrets()
        if not settings.SESSION_SECRET_KEY:
            raise ValueError("SESSION_SECRET_KEY not successfully loaded.")
        logger.info("Application configuration initialized successfully.")
        return settings
    except Exception as e:
        logger.critical(f"Critical error initializing application configuration: {e}", exc_info=True)
        raise SystemExit(f"Application cannot start due to configuration error: {e}")