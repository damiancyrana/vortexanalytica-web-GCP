"""
FastAPI dependencies module (Production Only).
Firebase verification + cookie session.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

from fastapi import Request, Depends, HTTPException, status

import firebase_admin
from firebase_admin import auth
from firebase_admin.auth import ExpiredIdTokenError, InvalidIdTokenError

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature, BadSignature

from Backend.core.config import Settings, get_settings
from Backend.services.email_service import EmailService

logger = logging.getLogger(__name__)


async def verify_firebase_token(id_token: str) -> dict:
    """Verifies Firebase ID token and returns decoded token."""
    if not firebase_admin._apps:
        logger.error("Attempt to verify Firebase token, but SDK is not initialized.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server authentication configuration issue.")

    try:
        decoded_token = auth.verify_id_token(id_token)
        if not decoded_token or not isinstance(decoded_token, dict):
            logger.error(f"verify_id_token returned unexpected result: {type(decoded_token)}")
            raise InvalidIdTokenError("Failed to decode token or result has wrong type.")

        settings = get_settings()
        expected_iss = f"https://securetoken.google.com/{settings.PROJECT_ID}"
        if decoded_token.get("iss") != expected_iss or decoded_token.get("aud") != settings.PROJECT_ID:
            logger.warning("Issuer or audience mismatch in Firebase token")
            raise InvalidIdTokenError("Invalid issuer or audience")

        if not decoded_token.get("email_verified", False):
            logger.info("User does not have verified email address")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not verified")

        return decoded_token
    except ExpiredIdTokenError:
        logger.info("Received expired Firebase ID token.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firebase token expired.")
    except InvalidIdTokenError as e:
        logger.info(f"Received invalid Firebase ID token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase token.")
    except Exception as e:
        logger.error(f"Unexpected error verifying Firebase token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error verifying Firebase token.")


async def get_current_active_user(
    request: Request,
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """Reads and verifies session cookie. Returns session data."""
    if not settings.SESSION_SECRET_KEY:
        logger.critical("No SESSION_SECRET_KEY in configuration during session cookie verification!")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session server configuration error.")

    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_cookie:
        # This is normal for non-logged-in users, not necessarily an error
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No session credentials.", headers={"WWW-Authenticate": "Session"})

    serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
    try:
        session_data = serializer.loads(session_cookie, max_age=settings.SESSION_COOKIE_MAX_AGE)
        if not isinstance(session_data, dict) or 'user_id' not in session_data:
            logger.warning(f"Invalid session cookie data structure: {type(session_data)}")
            raise BadSignature("Invalid session data structure.")
        return session_data
    except SignatureExpired:
        logger.info(f"Expired session cookie: {settings.SESSION_COOKIE_NAME}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.", headers={"WWW-Authenticate": "Session"})
    except BadTimeSignature as e:
        logger.warning(f"Invalid time format in session cookie ({settings.SESSION_COOKIE_NAME}): {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session cookie (time).", headers={"WWW-Authenticate": "Session"})
    except BadSignature as e:
        logger.warning(f"Invalid session cookie signature ({settings.SESSION_COOKIE_NAME}): {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session credentials (signature).", headers={"WWW-Authenticate": "Session"})
    except Exception as e:
        logger.error(f"Unexpected error verifying session cookie: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing session.")


def get_template_context(request: Request, settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Creates base context for templates, attempting to read session."""
    user_session = None
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_value and settings.SESSION_SECRET_KEY:
        serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
        try:
            # Don't check max_age here, only signature
            user_session = serializer.loads(cookie_value)
            if not isinstance(user_session, dict) or 'user_id' not in user_session:
                user_session = None
        except BadSignature:
            user_session = None
        except Exception:
            user_session = None

    return {
        "request": request,
        "app_name": settings.app_name,
        "auth_url": "/login",
        "logout_url": "/logout",
        "user": user_session  # May be None
    }


def get_email_service(settings: Settings = Depends(get_settings)) -> EmailService:
    """Creates and returns email service instance."""
    if settings.smtp_user is None or settings.smtp_pass is None:
        logger.error("Missing SMTP authentication data in EmailService configuration.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Email service configuration incomplete.")
    
    try:
        # Pass data to constructor to avoid issues with multiple loading in singleton
        service = EmailService(
            smtp_user=settings.smtp_user,
            smtp_pass=settings.smtp_pass,
            default_recipient=settings.MAIL_TO
        )
        return service
    except Exception as e:
        logger.error(f"Error creating EmailService instance: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cannot create email service.")