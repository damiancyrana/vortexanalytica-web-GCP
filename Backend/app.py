"""
Vortex Analytica - Main application module (Production Only)
"""
import logging, os, multiprocessing
from functools import lru_cache
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette_csrf import CSRFMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Logging configuration
def setup_logging():
    """Centralized logging configuration"""
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s:%(lineno)d] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger(__name__)

# Initialize logger at the beginning
logger = setup_logging()

# Import application modules AFTER logging configuration
from Backend.core.config import get_settings, Settings
from Backend.routes import register_routes
from Backend.services import lifecycle
from Backend.core.error_handlers import register_error_handlers


class VortexApplication:
    """Main application class (Singleton)"""
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
        if getattr(self, '_initialized', False): 
            return
            
        self._settings = get_settings()
        self._initialize_app()
        self._initialized = True
        logger.info("VortexApplication initialization complete")

    def _initialize_app(self) -> None:
        """Initializes FastAPI application"""
        self._app = FastAPI(
            title=self._settings.app_name,
            docs_url=None,  # Disable Swagger in production
            redoc_url=None,  # Disable ReDoc in production
            default_response_class=ORJSONResponse,
        )

        self._configure_middleware()
        self._templates = Jinja2Templates(directory=self._settings.templates_dir)
        self._app.mount("/static", StaticFiles(directory=self._settings.static_dir), name="static")
        register_routes(self._app, self._templates, self._settings)
        register_error_handlers(self._app, self._templates)
        self._app.add_event_handler("startup", lifecycle.app_startup)
        self._app.add_event_handler("shutdown", lifecycle.app_shutdown)
        self._configure_static_cache()
        logger.info("FastAPI application initialization complete.")

    def _configure_static_cache(self) -> None:
        """Configures cache for static files (production mode)"""
        @self._app.middleware("http")
        async def add_cache_headers(request, call_next):
            response = await call_next(request)

            if not self._settings:
                logger.warning("Settings not available in _configure_static_cache")
                return response

            # Cache headers for production mode
            if request.url.path.startswith("/static/"):
                if "js" in request.url.path or "css" in request.url.path:
                    response.headers["Cache-Control"] = "public, max-age=604800"  # 7 days
                elif any(ext in request.url.path for ext in [".jpg", ".png", ".gif", ".ico", ".svg"]):
                    response.headers["Cache-Control"] = "public, max-age=2592000"  # 30 days

            return response

    def _configure_middleware(self) -> None:
        """Configures application middleware."""
        # Trusted Host Middleware
        allowed_hosts = [
            "www.vortexanalytica.com",
            "vortexanalytica.com",
            "127.0.0.1",
            "localhost",
        ]
        self._app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

        # GZip Middleware (response compression)
        self._app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=9)

        # CORS Middleware
        self._configure_cors()

        # CSRF Middleware
        self._configure_csrf()

        logger.info("Middleware configuration complete.")

    def _configure_cors(self) -> None:
        """Configures CORS middleware"""
        allowed_origins = [
            "https://www.vortexanalytica.com",
            "https://vortexanalytica.com",
            "http://www.vortexanalytica.com",
            "http://vortexanalytica.com",
        ]
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            max_age=600
        )

    def _configure_csrf(self) -> None:
        """Configures CSRF middleware"""
        try:
            logger.info("Adding CSRFMiddleware...")
            self._app.add_middleware(
                CSRFMiddleware,
                secret=self._settings.SESSION_SECRET_KEY,
                cookie_name="csrftoken",
                cookie_secure=self._settings.SESSION_COOKIE_SECURE,
                cookie_samesite=self._settings.SESSION_COOKIE_SAMESITE,
            )
            logger.info("CSRFMiddleware added successfully.")
        except ImportError:
            logger.critical("LIBRARY starlette-csrf NOT INSTALLED - APPLICATION IS VULNERABLE TO CSRF ATTACKS")
            raise RuntimeError("CSRF protection library (starlette-csrf) not installed. Application cannot run securely.")
        except Exception as e:
            logger.critical(f"Cannot configure CSRFMiddleware: {e}", exc_info=True)
            raise RuntimeError(f"Failed to configure CSRF protection: {e}")

    @property
    def app(self) -> FastAPI:
        """Returns initialized FastAPI instance."""
        if self._app is None:
             logger.error("Critical error: Attempting to access self.app before full VortexApplication initialization!")
             raise RuntimeError("FastAPI application instance is not available.")
        return self._app


@lru_cache()
def create_app() -> FastAPI:
    """Factory function creating FastAPI application (Singleton)."""
    app_instance = VortexApplication()
    return app_instance.app


def get_optimal_workers():
    """Calculates optimal number of workers based on available CPU cores."""
    try:
        cores = multiprocessing.cpu_count()
        if cores <= 4:
            optimal = max(4, cores * 4)  # 4 for small machines
        else:
            optimal = min(cores * 4, 16)  # 4 per core, max 16
        logger.info(f"Detected {cores} CPU cores, optimal worker count: {optimal}")
        return optimal
    except Exception as e:
        logger.warning(f"Cannot determine CPU core count: {e}, using default value 6")
        return 6


# Example command with optimal worker count:
# uvicorn --factory Backend.app:create_app --workers $(python -c "from Backend.app import get_optimal_workers; print(get_optimal_workers())") --host 0.0.0.0 --port 8040

# uvicorn --factory Backend.app:create_app --reload --host 0.0.0.0 --port 8040
# sudo fuser -k 8040/tcp
# ps aux | grep uvicorn

# sudo nginx -t
# sudo systemctl reload nginx

# For compatibility with uvicorn without --factory flag
app = create_app()