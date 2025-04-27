"""
Moduł zależności FastAPI (Wersja Produkcyjna - Hybrydowa)
Weryfikacja Firebase + sesja ciasteczkowa.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from fastapi import Request, Depends, HTTPException, status, Response

import firebase_admin
from firebase_admin import auth
from firebase_admin.auth import UserRecord, ExpiredIdTokenError, InvalidIdTokenError

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature, BadSignature

from Backend.core.config import Settings, get_settings
from Backend.services.email_service import EmailService

logger = logging.getLogger(__name__)

async def verify_firebase_token(id_token: str) -> dict:
    """ Weryfikuje token Firebase ID i zwraca zdekodowany token (dict). """
    if not firebase_admin._apps:
        logger.error("Próba weryfikacji tokenu Firebase, ale SDK nie jest zainicjalizowane.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Problem z konfiguracją autentykacji serwera.")
    try:
        decoded_token = auth.verify_id_token(id_token)
        if not decoded_token or not isinstance(decoded_token, dict):
             logger.error(f"verify_id_token zwrócił nieoczekiwany wynik: {type(decoded_token)}")
             raise InvalidIdTokenError("Nie udało się zdekodować tokenu lub wynik ma zły typ.")
        return decoded_token
    except ExpiredIdTokenError:
        logger.info("Otrzymano wygasły token Firebase ID.") # Info zamiast warning
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Firebase wygasł.")
    except InvalidIdTokenError as e:
        logger.info(f"Otrzymano nieprawidłowy token Firebase ID: {e}") # Info zamiast warning
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token Firebase.")
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd podczas weryfikacji tokenu Firebase: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Błąd podczas weryfikacji tokenu Firebase.")

async def get_current_active_user(
    request: Request,
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """ Odczytuje i weryfikuje ciasteczko sesyjne. Zwraca dane sesji. """
    if not settings.SESSION_SECRET_KEY:
         logger.critical("Brak SESSION_SECRET_KEY w konfiguracji podczas próby weryfikacji ciasteczka!")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Błąd konfiguracji serwera sesji.")

    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_cookie:
        # To jest normalne dla niezalogowanych użytkowników, niekoniecznie błąd
        # logger.debug("Brak ciasteczka sesyjnego w żądaniu.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Brak poświadczeń sesji.", headers={"WWW-Authenticate": "Session"})

    serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
    try:
        session_data = serializer.loads(session_cookie, max_age=settings.SESSION_COOKIE_MAX_AGE)
        if not isinstance(session_data, dict) or 'user_id' not in session_data:
             logger.warning(f"Nieprawidłowa struktura danych w ciasteczku sesyjnym: {type(session_data)}")
             raise BadSignature("Nieprawidłowa struktura danych sesji.")
        # logger.debug(f"Pomyślnie zweryfikowano sesję dla user_id: {session_data.get('user_id')}")
        return session_data
    except SignatureExpired:
        logger.info(f"Wygasłe ciasteczko sesyjne: {settings.SESSION_COOKIE_NAME}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesja wygasła.", headers={"WWW-Authenticate": "Session"})
    except BadTimeSignature as e:
        logger.warning(f"Nieprawidłowy format czasu w ciasteczku sesyjnym ({settings.SESSION_COOKIE_NAME}): {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe ciasteczko sesyjne (czas).", headers={"WWW-Authenticate": "Session"})
    except BadSignature as e:
        logger.warning(f"Nieprawidłowa sygnatura ciasteczka sesyjnego ({settings.SESSION_COOKIE_NAME}): {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe poświadczenia sesji (sygnatura).", headers={"WWW-Authenticate": "Session"})
    except Exception as e:
         logger.error(f"Nieoczekiwany błąd podczas weryfikacji ciasteczka sesyjnego: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Wystąpił błąd podczas przetwarzania sesji.")

def get_template_context(request: Request, settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """ Tworzy bazowy kontekst dla szablonów, próbując odczytać sesję. """
    user_session = None
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_value and settings.SESSION_SECRET_KEY:
        serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
        try:
            # Nie sprawdzamy max_age tutaj, tylko sygnaturę
            user_session = serializer.loads(cookie_value)
            if not isinstance(user_session, dict) or 'user_id' not in user_session:
                user_session = None
        except BadSignature: # Ignorujemy też SignatureExpired, BadTimeSignature
            user_session = None
        except Exception: # Ogólny wyjątek
             user_session = None

    return {
        "request": request,
        "app_name": settings.app_name,
        "auth_url": "/login",
        "logout_url": "/logout",
        "environment": settings.environment,
        "is_production": settings.is_production,
        "user": user_session # Może być None
    }

def get_email_service(settings: Settings = Depends(get_settings)) -> EmailService:
    """ Tworzy i zwraca instancję serwisu email. """
    if settings.smtp_user is None or settings.smtp_pass is None:
        logger.error("Brak danych uwierzytelniających SMTP w konfiguracji EmailService.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Konfiguracja serwisu e-mail jest niekompletna.")
    # Używamy fabryki/singletona z __init__, który pobiera dane z settings
    try:
         # Przekazujemy dane do konstruktora, aby uniknąć problemów z wielokrotnym ładowaniem w singletonie
         service = EmailService(
             smtp_user=settings.smtp_user,
             smtp_pass=settings.smtp_pass,
             default_recipient=settings.MAIL_TO
         )
         return service
    except Exception as e:
         logger.error(f"Błąd podczas tworzenia instancji EmailService: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nie można utworzyć serwisu e-mail.")