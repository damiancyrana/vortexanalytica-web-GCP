"""
Vortex Analytica - Główny moduł aplikacji (Wersja Produkcyjna - Hybrydowa)
"""
import logging
import os
from functools import lru_cache
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware import Middleware # Poprawiony import
# === WAŻNE: Import dla CSRF Middleware (przykład) ===
# Należy zainstalować: pip install starlette-csrf
# from starlette_csrf import CSRFMiddleware
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

    def _configure_middleware(self) -> None:
        """ Konfiguruje middleware aplikacji. """
        # ZAWSZE dodawaj middleware w odpowiedniej kolejności (od zewnątrz do wewnątrz)

        # 1. GZip Middleware (kompresja odpowiedzi)
        self._app.add_middleware( GZipMiddleware, minimum_size=1024, compresslevel=9 ) # Wyższy poziom kompresji dla prod

        # 2. Middleware do obsługi błędów / logowania żądań (opcjonalnie)
        # Np. middleware logujące czas odpowiedzi, statusy itp.

        # 3. === Middleware CSRF (KRYTYCZNE DLA BEZPIECZEŃSTWA!) ===
        # Musisz zainstalować (np. pip install starlette-csrf) i skonfigurować.
        # Odkomentuj i dostosuj PONIŻEJ, gdy będziesz gotowy.
        # --- POCZĄTEK PRZYKŁADU CSRF ---
        # try:
        #     from starlette_csrf import CSRFMiddleware
        #     logger.info("Dodawanie CSRFMiddleware...")
        #     self._app.add_middleware(
        #         CSRFMiddleware,
        #         secret=self._settings.SESSION_SECRET_KEY, # Użyj tego samego sekretu co dla sesji
        #         cookie_name="csrftoken", # Domyślna nazwa
        #         cookie_secure=self._settings.SESSION_COOKIE_SECURE,
        #         cookie_samesite=self._settings.SESSION_COOKIE_SAMESITE,
        #         # safe_methods={"GET", "HEAD", "OPTIONS", "TRACE"} # Domyślne bezpieczne metody
        #         # header_name="X-CSRF-Token" # Jeśli używasz tokenu w nagłówku dla AJAX
        #     )
        #     logger.info("CSRFMiddleware dodane pomyślnie.")
        # except ImportError:
        #      logger.critical("!!! BIBLIOTEKA starlette-csrf NIE JEST ZAINSTALOWANA !!!")
        #      logger.critical("!!! OCHRONA CSRF JEST WYMAGANA PRZY UŻYCIU CIASTECZEK - APLIKACJA JEST PODATNA NA ATAKI CSRF !!!")
        #      # W produkcji można rozważyć zatrzymanie aplikacji:
        #      # raise RuntimeError("CSRF protection library (starlette-csrf) not installed. Application cannot run securely.")
        # except Exception as e:
        #      logger.critical(f"!!! Nie można skonfigurować CSRFMiddleware: {e} !!!", exc_info=True)
        #      # Można rozważyć zatrzymanie aplikacji
        # --- KONIEC PRZYKŁADU CSRF ---
        logger.critical("!!! OCHRONA CSRF NIE JEST AKTYWNA W TYM KODZIE. ZAINSTALUJ, SKONFIGURUJ I ODKOMENTUJ ODPOWIEDNIE MIDDLEWARE W _configure_middleware() !!!")
        # ============================================================

        # Inne middleware (np. CORS, jeśli API ma być dostępne z innych domen)
        # from fastapi.middleware.cors import CORSMiddleware
        # self._app.add_middleware(CORSMiddleware, allow_origins=["your_frontend_domain"], ...)

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
            "workers": 1 if settings.is_development else int(os.getenv("WEB_CONCURRENCY", 4)),
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