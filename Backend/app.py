"""
Vortex Analytica - Moduł główny aplikacji
Zoptymalizowana implementacja z wykorzystaniem wzorców projektowych i OOP
Dostosowana do Pydantic v2.x
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Dict, Any, Optional, Final

import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import BackgroundTasks, Form, status
from email.message import EmailMessage
from smtplib import SMTP_SSL

# Logger
logger = logging.getLogger(__name__)

# Importy wewnętrzne - lazy import aby uniknąć problemów z cyklicznymi importami
def get_settings():
    from Backend.core.config import get_settings
    return get_settings()


class VortexApplication:
    """
    Główna klasa aplikacji implementująca wzorzec Singleton.
    Odpowiada za inicjalizację i konfigurację FastAPI.
    """
    _instance: Optional[VortexApplication] = None
    _app: Optional[FastAPI] = None
    _templates: Optional[Jinja2Templates] = None
    
    def __new__(cls) -> VortexApplication:
        """Implementacja wzorca Singleton"""
        if cls._instance is None:
            cls._instance = super(VortexApplication, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """Inicjalizacja tylko jeśli nie była wcześniej wykonana"""
        if getattr(self, '_initialized', False):
            return
            
        self._settings = get_settings()
        self._initialize_app()
        self._initialized = True
    
    def _initialize_app(self) -> None:
        """Inicjalizacja aplikacji FastAPI z optymalnymi ustawieniami"""
        self._app = FastAPI(
            title="Vortex Analytica",
            docs_url=None,  # Wyłącz dokumentację Swagger
            redoc_url=None  # Wyłącz dokumentację ReDoc
        )
        
        # Zoptymalizowane middleware
        self._configure_middleware()
        
        # Szablony
        base_dir = os.path.dirname(os.path.dirname(__file__))
        templates_dir = os.path.join(base_dir, "Frontend", "templates")
        static_dir = os.path.join(base_dir, "Frontend", "static")
        
        self._templates = Jinja2Templates(directory=templates_dir)
        
        # Statyczne pliki z cache-control
        self._app.mount(
            "/static", 
            StaticFiles(directory=static_dir), 
            name="static"
        )
        
        # Rejestracja tras
        self._register_routes()
        
        # Zdarzenia cyklu życia aplikacji
        self._app.add_event_handler("startup", self._on_startup)
        self._app.add_event_handler("shutdown", self._on_shutdown)
    
    async def _on_startup(self) -> None:
        """Funkcja uruchamiana przy starcie aplikacji"""
        logger.info("Uruchamianie aplikacji Vortex Analytica...")
        
        # Ładowanie sekretów w razie potrzeby
        settings = get_settings()
        if settings.is_production:
            settings.load_secrets()
            
        logger.info(f"Aplikacja uruchomiona w trybie: {settings.environment}")
    
    async def _on_shutdown(self) -> None:
        """Funkcja uruchamiana przy zatrzymaniu aplikacji"""
        logger.info("Zamykanie aplikacji...")
        logger.info("Aplikacja została pomyślnie zamknięta.")
    
    def _configure_middleware(self) -> None:
        """Konfiguracja middleware z optymalnymi ustawieniami wydajności"""
        # GZip dla kompresji odpowiedzi (oszczędność przepustowości)
        self._app.add_middleware(
            GZipMiddleware, 
            minimum_size=1024,  # Minimalna wielkość do kompresji
            compresslevel=6     # Balans między wydajnością a stopniem kompresji
        )
    
    def _register_routes(self) -> None:
        """
        Rejestracja tras aplikacji
        
        W pierwszej iteracji implementujemy je bezpośrednio, aby zapewnić
        kompatybilność z istniejącym kodem.
        """
        @self._app.get("/", response_class=HTMLResponse)
        async def landing(request: Request) -> HTMLResponse:
            """Strona główna (landing page)"""
            return self._templates.TemplateResponse(
                "landing_page.html",
                {"request": request, "auth_url": "/login"}
            )

        @self._app.get("/index", response_class=HTMLResponse)
        async def index_page(request: Request) -> HTMLResponse:
            """Strona indeksu"""
            return self._templates.TemplateResponse(
                "index.html",
                {"request": request}
            )
        
        @self._app.get("/login", response_class=HTMLResponse)
        async def login_page(request: Request) -> HTMLResponse:
            """Strona logowania"""
            return self._templates.TemplateResponse(
                "login.html",
                {"request": request}
            )
        
        @self._app.post("/contact", response_class=JSONResponse,
                  status_code=status.HTTP_202_ACCEPTED)
        async def contact(
            background_tasks: BackgroundTasks,
            name: str = Form(..., max_length=128),
            email: str = Form(...),
            subject: str = Form(..., max_length=256),
            message: str = Form(..., max_length=10_000),
        ) -> JSONResponse:
            """Obsługa formularza kontaktowego"""
            # Funkcja do wysyłania e-maili
            def send_mail(subject: str, body: str, *, reply_to: str) -> None:
                """Wysyła wiadomość e-mail"""
                settings = get_settings()
                
                # Upewnij się, że mamy dane do SMTP
                if settings.smtp_user is None or settings.smtp_pass is None:
                    settings.load_secrets()
                
                msg = EmailMessage()
                msg["Subject"] = f"[Vortex landing] {subject}"
                msg["From"] = settings.smtp_user
                msg["To"] = settings.MAIL_TO
                msg["Reply-To"] = reply_to
                msg.set_content(body)

                with SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
                    smtp.login(settings.smtp_user, settings.smtp_pass)
                    smtp.send_message(msg)
            
            body = (
                "—— Formularz kontaktowy Vortex Analytica ——\n\n"
                f"Nadawca : {name} <{email}>\n"
                f"Temat   : {subject}\n\n"
                f"Wiadomość:\n{message}\n"
            )
                
            background_tasks.add_task(send_mail, subject, body, reply_to=email)
            return {"ok": True, "msg": "Wiadomość została wysłana."}
    
    @property
    def app(self) -> FastAPI:
        """Zwraca skonfigurowaną instancję aplikacji FastAPI"""
        if self._app is None:
            self._initialize_app()
        return self._app


# Funkcja fabryczna zgodna z poprzednim interfejsem
@lru_cache
def create_app() -> FastAPI:
    """
    Funkcja fabryczna tworząca aplikację FastAPI.
    
    Wykorzystuje wzorzec Singleton z cache dla powtórnych wywołań,
    co zwiększa wydajność przy wielu wywołaniach.
    
    Returns:
        FastAPI: Skonfigurowana instancja aplikacji
    """
    app_instance = VortexApplication()
    return app_instance.app


# Uruchomienie serwera deweloperskiego
if __name__ == "__main__":
    # Konfiguracja logów
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # Parametry uruchomieniowe
    uvicorn.run(
        "Backend.app:create_app",
        host="0.0.0.0",
        port=8040,
        factory=True,
        reload=True,   # tylko w trybie dev
        workers=4,     # W trybie dev wystarczy jeden worker
        log_level="info",
    )