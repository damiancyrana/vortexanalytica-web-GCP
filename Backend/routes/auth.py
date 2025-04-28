"""
Moduł tras autoryzacji (Wersja Produkcyjna - Hybrydowa).
Logowanie Firebase + sesja ciasteczkowa, wylogowanie.
Dodano endpoint sprawdzający status sesji.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional # Dodano Optional
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, EmailStr

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature, BadSignature
# Importujemy potrzebne zależności
from Backend.core.dependencies import get_template_context, verify_firebase_token, get_current_active_user
from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Model danych dla żądania logowania sesji
class FirebaseSessionLoginRequest(BaseModel):
    token: str = Field(..., description="Firebase ID Token uzyskany z frontendu")

# Funkcja rejestrująca trasy w aplikacji FastAPI
def register_auth_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """ Rejestruje trasy /login, /logout, /auth/firebase-session-login, /auth/firebase-config. """

    # Trasa GET dla strony logowania
    @app.get(
        "/login",
        # response_class=HTMLResponse, # Opcjonalnie, dla dokumentacji
        response_model=None, # WAŻNE: Rozwiązanie problemu FastAPIError
        summary="Wyświetla stronę logowania lub przekierowuje"
    )
    async def login_page(
        request: Request, # Potrzebny dla request.url_for
        context: dict = Depends(get_template_context) # Pobiera podstawowy kontekst (z info o sesji)
    ) -> HTMLResponse | RedirectResponse: # Adnotacja typu zwracanego
        """ Wyświetla stronę logowania lub przekierowuje, jeśli użytkownik ma aktywną sesję. """
        # Sprawdź, czy użytkownik już ma sesję (dane z get_template_context)
        if context.get("user") and context["user"].get("user_id"):
            logger.debug(f"Użytkownik {context['user'].get('user_id')} z aktywną sesją na /login, przekierowanie do /index.")
            try:
                 # Próba użycia nazwy trasy dla elastyczności
                 index_url = request.url_for('index_page_route') # Nadaj name='index_page_route' trasie /index w landing.py
            except Exception:
                 logger.warning("Nie można znaleźć trasy 'index_page_route', używam fallback '/index'.")
                 index_url = "/index" # Fallback, jeśli nazwa trasy nie działa
            return RedirectResponse(url=index_url, status_code=status.HTTP_303_SEE_OTHER)
        # Jeśli nie ma sesji, zwróć szablon logowania
        return templates.TemplateResponse("login.html", context)

    # Trasa POST do tworzenia sesji na podstawie tokenu Firebase
    @app.post("/auth/firebase-session-login", status_code=status.HTTP_200_OK, summary="Tworzy sesję na podstawie tokenu Firebase")
    async def firebase_session_login(
        response: Response, # Obiekt odpowiedzi do ustawienia ciasteczka
        request_data: FirebaseSessionLoginRequest, # Oczekiwane dane z tokenem
        settings: Settings = Depends(get_settings) # Dostęp do konfiguracji
    ) -> Dict[str, str]:
        """ Weryfikuje token Firebase ID i tworzy sesję ciasteczkową. """
        if not settings.SESSION_SECRET_KEY:
             logger.critical("Krytyczny błąd: Brak SESSION_SECRET_KEY podczas tworzenia sesji!")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Błąd konfiguracji serwera sesji.")

        try:
            # Weryfikacja tokenu Firebase
            decoded_token = await verify_firebase_token(request_data.token)
            user_id = decoded_token.get('uid')
            user_email = decoded_token.get('email')
            user_name = decoded_token.get('name') # Może być None

            if not user_id:
                logger.error("Token Firebase zweryfikowany, ale brakuje w nim UID.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy token Firebase (brak UID).")

            logger.info(f"Weryfikacja Firebase OK dla UID: {user_id}, Email: {user_email}")

            # TODO: Dodatkowa logika (np. sprawdzanie użytkownika w lokalnej bazie danych)

            # Przygotowanie danych do zapisania w ciasteczku
            session_data = { "user_id": user_id }
            if user_email: session_data["email"] = user_email
            if user_name: session_data["name"] = user_name
            # Można dodać np. timestamp utworzenia sesji: session_data["iat"] = datetime.utcnow()

            # Stworzenie i podpisanie ciasteczka
            serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
            session_cookie_value = serializer.dumps(session_data)

            # Ustawienie ciasteczka w odpowiedzi
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=session_cookie_value,
                max_age=settings.SESSION_COOKIE_MAX_AGE,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                samesite=settings.SESSION_COOKIE_SAMESITE
            )

            logger.info(f"Ustawiono ciasteczko sesyjne dla użytkownika: {user_id}")
            # Zwrócenie sukcesu do frontendu
            return {"status": "ok", "message": "Session cookie set successfully."}

        except HTTPException as e:
             # Przekazanie błędów HTTP (np. 401 z weryfikacji tokenu)
             logger.info(f"Błąd HTTP podczas tworzenia sesji: {e.status_code} - {e.detail}")
             raise e
        except Exception as e:
            # Logowanie nieoczekiwanych błędów
            logger.error(f"Nieoczekiwany błąd podczas tworzenia sesji ciasteczkowej: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Błąd wewnętrzny serwera podczas logowania sesji.")

    # Trasa GET zwracająca konfigurację Firebase dla frontendu
    @app.get("/auth/firebase-config", response_class=JSONResponse, summary="Zwraca publiczną konfigurację Firebase")
    async def firebase_config(settings: Settings = Depends(get_settings)) -> JSONResponse:
        """ Zwraca publiczną konfigurację Firebase (apiKey, authDomain). """
        api_key = settings.firebase_api_key
        auth_domain = settings.firebase_auth_domain
        # Upewnij się, że wartości zostały załadowane (get_settings powinno o to zadbać)
        if not api_key or not auth_domain:
             logger.critical("Krytyczny błąd: Brak firebase_api_key lub firebase_auth_domain w załadowanej konfiguracji!")
             # Zwracamy 503, bo usługa jest źle skonfigurowana
             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Konfiguracja systemu uwierzytelniania jest niedostępna.")
        return JSONResponse(content={"apiKey": api_key, "authDomain": auth_domain})

    # Trasa POST do wylogowania (usuwa ciasteczko sesyjne)
    @app.post("/logout", status_code=status.HTTP_200_OK, summary="Wylogowuje użytkownika (usuwa ciasteczko sesji)")
    async def logout(
        response: Response,
        settings: Settings = Depends(get_settings)
    ):
        logger.info(f"Żądanie wylogowania - usuwanie ciasteczka: {settings.SESSION_COOKIE_NAME}")
        response.delete_cookie(
            key=settings.SESSION_COOKIE_NAME,
            path=settings.SESSION_COOKIE_PATH,
            domain=settings.SESSION_COOKIE_DOMAIN,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=settings.SESSION_COOKIE_HTTPONLY,
            samesite=settings.SESSION_COOKIE_SAMESITE
        )
        return {"status": "ok", "message": "Logged out successfully."}

    # NOWY ENDPOINT: Sprawdzanie statusu sesji
    @app.get("/api/auth/session-status", summary="Sprawdza status sesji użytkownika")
    async def check_session_status(
        request: Request,
        settings: Settings = Depends(get_settings)
    ) -> Dict[str, Any]:
        """
        Sprawdza status sesji użytkownika i zwraca informacje o sesji.
        Nie rzuca wyjątku, jeśli użytkownik nie jest zalogowany.
        """
        session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if not session_cookie or not settings.SESSION_SECRET_KEY:
            return {"authenticated": False, "user": None}
        
        try:
            serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
            session_data = serializer.loads(session_cookie, max_age=settings.SESSION_COOKIE_MAX_AGE)
            
            if not isinstance(session_data, dict) or 'user_id' not in session_data:
                logger.warning(f"Nieprawidłowa struktura danych w sesji: {type(session_data)}")
                return {"authenticated": False, "user": None}
            
            # Zwróć dane sesji
            return {
                "authenticated": True,
                "user": {
                    "user_id": session_data.get("user_id"),
                    "email": session_data.get("email"),
                    "name": session_data.get("name")
                }
            }
        except SignatureExpired:
            logger.info(f"Wygasła sesja podczas sprawdzania statusu")
            return {"authenticated": False, "user": None, "error": "expired_session"}
        except (BadTimeSignature, BadSignature) as e:
            logger.warning(f"Nieprawidłowy podpis sesji podczas sprawdzania statusu: {e}")
            return {"authenticated": False, "user": None, "error": "invalid_session"}
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania statusu sesji: {e}", exc_info=True)
            return {"authenticated": False, "user": None, "error": "server_error"}