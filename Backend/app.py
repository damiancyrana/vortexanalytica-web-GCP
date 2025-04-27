"""
Vortex Analytica - Główny moduł aplikacji (Wersja Produkcyjna - Hybrydowa)
"""
import logging
import os
import multiprocessing
from functools import lru_cache
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
# === WAŻNE: Import dla CSRF Middleware (przykład) ===
# Należy zainstalować: pip install starlette-csrf
from starlette_csrf import CSRFMiddleware
# ===============================================
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Konfiguracja logowania na początku, przed importami używającymi loggera
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(name)s:%(lineno)d] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__) # Teraz można używać loggera

# Importy modułów aplikacji PO konfiguracji logów
from Backend.core.config import get_settings, Settings
from Backend.routes import register_routes
from Backend.services import lifecycle


class VortexApplication:
    """ Główna klasa aplikacji (Singleton). """
    _instance: Optional["VortexApplication"] = None
    _app: Optional[FastAPI] = None
    _templates: Optional[Jinja2Templates] = None
    _settings: Optional[Settings] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VortexApplication, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, '_initialized', False): return
        logger.info("Inicjalizacja instancji VortexApplication...")
        self._settings = get_settings() # Pobierz ustawienia (ładuje sekrety)
        self._initialize_app()
        self._initialized = True
        logger.info("Inicjalizacja VortexApplication zakończona.")

    def _initialize_app(self) -> None:
        """ Inicjalizuje aplikację FastAPI. """
        logger.info("Inicjalizacja aplikacji FastAPI...")
        self._app = FastAPI(
             title=self._settings.app_name,
             docs_url=None, # Wyłącz Swagger na produkcji
             redoc_url=None, # Wyłącz ReDoc na produkcji
             # Można dodać version="x.y.z"
         )
        logger.info("Konfigurowanie middleware...")
        self._configure_middleware()
        logger.info("Konfigurowanie szablonów Jinja2...")
        self._templates = Jinja2Templates(directory=self._settings.templates_dir)
        logger.info("Montowanie plików statycznych...")
        self._app.mount( "/static", StaticFiles(directory=self._settings.static_dir), name="static")
        logger.info("Rejestrowanie tras...")
        register_routes(self._app, self._templates, self._settings)
        logger.info("Dodawanie obsługi zdarzeń startup/shutdown...")
        self._app.add_event_handler("startup", lifecycle.app_startup)
        self._app.add_event_handler("shutdown", lifecycle.app_shutdown)
        logger.info("Inicjalizacja aplikacji FastAPI zakończona.")

        # Dodawanie middleware cache dla plików statycznych
        @self._app.middleware("http")
        async def add_cache_headers(request, call_next):
            response = await call_next(request)
            
            # Dodaj nagłówki cache dla plików statycznych
            if request.url.path.startswith("/static/"):
                if "js" in request.url.path or "css" in request.url.path:
                    # Javascript i CSS - 7 dni
                    response.headers["Cache-Control"] = "public, max-age=604800"
                elif any(ext in request.url.path for ext in [".jpg", ".png", ".gif", ".ico", ".svg"]):
                    # Obrazy - 30 dni
                    response.headers["Cache-Control"] = "public, max-age=2592000"
            
            return response

    def _configure_middleware(self) -> None:
        """ Konfiguruje middleware aplikacji. """
        # ZAWSZE dodawaj middleware w odpowiedniej kolejności (od zewnątrz do wewnątrz)

        # 1. GZip Middleware (kompresja odpowiedzi)
        self._app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=9) # Wyższy poziom kompresji dla prod

        # 2. CORS Middleware - dodane dla obsługi requestów z różnych źródeł
        allowed_origins = [
            str(self._settings.base_url) if self._settings.base_url else "https://vortexanalytica.com",
            "https://www.vortexanalytica.com",
            # W środowisku deweloperskim dodaj localhost
            *(["http://localhost:8040", "http://127.0.0.1:8040"] if self._settings.is_development else [])
        ]
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            max_age=600  # 10 minut cache preflight
        )
        logger.info(f"Skonfigurowano CORS dla domen: {allowed_origins}")

        # 3. === Middleware CSRF (KRYTYCZNE DLA BEZPIECZEŃSTWA!) ===
        try:
            logger.info("Dodawanie CSRFMiddleware...")
            self._app.add_middleware(
                CSRFMiddleware,
                secret=self._settings.SESSION_SECRET_KEY, # Użyj tego samego sekretu co dla sesji
                cookie_name="csrftoken", # Domyślna nazwa
                cookie_secure=self._settings.SESSION_COOKIE_SECURE,
                cookie_samesite=self._settings.SESSION_COOKIE_SAMESITE,
                # safe_methods={"GET", "HEAD", "OPTIONS", "TRACE"} # Domyślne bezpieczne metody
                # header_name="X-CSRF-Token" # Jeśli używasz tokenu w nagłówku dla AJAX
            )
            logger.info("CSRFMiddleware dodane pomyślnie.")
        except ImportError:
            logger.critical("!!! BIBLIOTEKA starlette-csrf NIE JEST ZAINSTALOWANA !!!")
            logger.critical("!!! OCHRONA CSRF JEST WYMAGANA PRZY UŻYCIU CIASTECZEK - APLIKACJA JEST PODATNA NA ATAKI CSRF !!!")
            # W produkcji zatrzymujemy aplikację:
            if self._settings.is_production:
                raise RuntimeError("CSRF protection library (starlette-csrf) not installed. Application cannot run securely.")
        except Exception as e:
            logger.critical(f"!!! Nie można skonfigurować CSRFMiddleware: {e} !!!", exc_info=True)
            if self._settings.is_production:
                raise RuntimeError(f"Failed to configure CSRF protection: {e}")

        logger.info("Konfiguracja middleware zakończona.")


    @property
    def app(self) -> FastAPI:
        """ Zwraca zainicjalizowaną instancję FastAPI. """
        if self._app is None:
             # Sytuacja awaryjna - nie powinna się zdarzyć
             logger.error("Krytyczny błąd: Próba dostępu do self.app przed pełną inicjalizacją VortexApplication!")
             raise RuntimeError("FastAPI application instance is not available.")
        return self._app

@lru_cache()
def create_app() -> FastAPI:
    """ Funkcja fabryczna tworząca aplikację FastAPI (Singleton). """
    logger.debug("Wywołanie funkcji fabrycznej create_app...")
    app_instance = VortexApplication()
    logger.debug("Instancja VortexApplication uzyskana/utworzona w create_app.")
    return app_instance.app

def get_optimal_workers():
    """Oblicza optymalną liczbę workerów na podstawie liczby dostępnych rdzeni CPU."""
    try:
        cores = multiprocessing.cpu_count()
        # Reguła: 2 workery na rdzeń, minimum 2, maksimum 8 (unikamy przeciążenia VM)
        optimal = max(2, min(cores * 2, 8))
        logger.info(f"Wykryto {cores} rdzeni CPU, optymalna liczba workerów: {optimal}")
        return optimal
    except Exception as e:
        logger.warning(f"Nie można określić liczby rdzeni CPU: {e}, używam domyślnej wartości 4")
        return 4

# Główny punkt wejścia (dla uruchomienia np. przez `python -m Backend.app` lub uvicorn)
if __name__ == "__main__":
    logger.info("Uruchamianie aplikacji bezpośrednio (if __name__ == '__main__')...")
    try:
        # get_settings() jest już wywoływane w VortexApplication, ale pobierzmy je tu dla uvicorn.run
        # Upewnij się, że logi są skonfigurowane PRZED pierwszym wywołaniem get_settings
        settings = get_settings()

        # Parametry dla Uvicorn
        uvicorn_config = {
            "host": os.getenv("HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", 8040)),
            "factory": True, # Używamy funkcji fabrycznej
            "reload": settings.is_development, # Włącz reload tylko w dev
            "workers": get_optimal_workers(),
            "log_level": settings.log_level.lower(),
            # Można dodać bardziej zaawansowaną konfigurację logowania uvicorn,
            # np. używając dictConfig z logging.config
            # "log_config": None,
        }
        logger.info(f"Konfiguracja Uvicorn: {uvicorn_config}")

        # Uruchomienie serwera
        uvicorn.run( "Backend.app:create_app", **uvicorn_config )

    except SystemExit as e:
         logger.critical(f"Aplikacja zakończona przez SystemExit podczas startu: {e}")
         import sys
         sys.exit(1) # Zwróć kod błędu
    except Exception as e:
         logger.critical(f"Nie można uruchomić aplikacji Uvicorn: {e}", exc_info=True)
         import sys
         sys.exit(1) # Zwróć kod błędu