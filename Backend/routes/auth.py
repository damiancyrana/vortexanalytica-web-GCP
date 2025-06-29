"""
Authorization routes module (Production Version).
Firebase login + cookie session, logout.
Added endpoint for checking session status.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response, Body
from fastapi.responses import HTMLResponse, RedirectResponse, ORJSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, EmailStr

from itsdangerous import (
    URLSafeTimedSerializer,
    SignatureExpired,
    BadTimeSignature,
    BadSignature,
)
from Backend.core.dependencies import (
    get_template_context,
    verify_firebase_token,
    get_current_active_user,
)
from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class FirebaseSessionLoginRequest(BaseModel):
    token: str = Field(..., description="Firebase ID Token obtained from frontend")


def register_auth_routes(
    app: FastAPI, templates: Jinja2Templates, settings: Settings
) -> None:
    """Registers /login, /logout, /auth/firebase-session-login, /auth/firebase-config routes."""

    @app.get("/login", response_model=None, summary="Displays login page or redirects")
    async def login_page(
        request: Request, context: dict = Depends(get_template_context)
    ) -> HTMLResponse | RedirectResponse:
        """Displays login page or redirects if user has active session."""
        # Check if user already has session (data from get_template_context)
        if context.get("user") and context["user"].get("user_id"):
            logger.debug(
                f"User {context['user'].get('user_id')} with active session on /login, redirecting to /index."
            )
            try:
                # Try to use route name for flexibility
                index_url = request.url_for("index_page_route")
            except Exception:
                logger.warning(
                    "Cannot find route 'index_page_route', using fallback '/index'."
                )
                index_url = "/index"
            return RedirectResponse(
                url=index_url, status_code=status.HTTP_303_SEE_OTHER
            )

        # If no session, return login template
        return templates.TemplateResponse("landing_page/login.html", context)

    @app.post(
        "/auth/firebase-session-login",
        status_code=status.HTTP_200_OK,
        summary="Creates session based on Firebase token",
    )
    async def firebase_session_login(
        response: Response,
        request_data: FirebaseSessionLoginRequest,
        settings: Settings = Depends(get_settings),
    ) -> Dict[str, str]:
        """Verifies Firebase ID token and creates cookie session."""
        if not settings.SESSION_SECRET_KEY:
            logger.critical(
                "Critical error: No SESSION_SECRET_KEY when creating session!"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session server configuration error.",
            )

        try:
            # Verify Firebase token
            decoded_token = await verify_firebase_token(request_data.token)
            user_id = decoded_token.get("uid")
            user_email = decoded_token.get("email")
            user_name = decoded_token.get("name")  # May be None

            if not user_id:
                logger.error("Firebase token verified, but missing UID.")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Firebase token (no UID).",
                )

            logger.info(
                f"Firebase verification OK for UID: {user_id}, Email: {user_email}"
            )

            # Prepare data to save in cookie
            session_data = {"user_id": user_id}
            if user_email:
                session_data["email"] = user_email
            if user_name:
                session_data["name"] = user_name

            # Create and sign cookie
            serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
            session_cookie_value = serializer.dumps(session_data)

            # Set cookie in response
            response.set_cookie(
                key=settings.SESSION_COOKIE_NAME,
                value=session_cookie_value,
                max_age=settings.SESSION_COOKIE_MAX_AGE,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )

            logger.info(f"Session cookie set for user: {user_id}")
            return {"status": "ok", "message": "Session cookie set successfully."}

        except HTTPException as e:
            logger.info(
                f"HTTP error during session creation: {e.status_code} - {e.detail}"
            )
            raise e
        except Exception as e:
            logger.error(
                f"Unexpected error during cookie session creation: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during session login.",
            )

    @app.get(
        "/auth/firebase-config",
        response_class=ORJSONResponse,
        summary="Returns public Firebase configuration",
    )
    async def firebase_config(
        settings: Settings = Depends(get_settings),
    ) -> ORJSONResponse:
        """Returns public Firebase configuration (apiKey, authDomain)."""
        api_key = settings.firebase_api_key
        auth_domain = settings.firebase_auth_domain

        if not api_key or not auth_domain:
            logger.critical(
                "Critical error: No firebase_api_key or firebase_auth_domain in loaded configuration!"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication system configuration unavailable.",
            )

        return ORJSONResponse(content={"apiKey": api_key, "authDomain": auth_domain})

    @app.post(
        "/logout",
        status_code=status.HTTP_200_OK,
        summary="Logs out user (removes session cookie)",
    )
    async def logout(response: Response, settings: Settings = Depends(get_settings)):
        """Logs out user by removing session cookie."""
        logger.info(f"Logout request - removing cookie: {settings.SESSION_COOKIE_NAME}")
        response.delete_cookie(
            key=settings.SESSION_COOKIE_NAME,
            path=settings.SESSION_COOKIE_PATH,
            domain=settings.SESSION_COOKIE_DOMAIN,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=settings.SESSION_COOKIE_HTTPONLY,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )
        return {"status": "ok", "message": "Logged out successfully."}

    @app.get("/api/auth/session-status", summary="Checks user session status")
    async def check_session_status(
        request: Request, settings: Settings = Depends(get_settings)
    ) -> Dict[str, Any]:
        """
        Checks user session status and returns session information.
        Does not throw exception if user is not logged in.
        """
        session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if not session_cookie or not settings.SESSION_SECRET_KEY:
            return {"authenticated": False, "user": None}

        try:
            serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)
            session_data = serializer.loads(
                session_cookie, max_age=settings.SESSION_COOKIE_MAX_AGE
            )

            if not isinstance(session_data, dict) or "user_id" not in session_data:
                logger.warning(f"Invalid session data structure: {type(session_data)}")
                return {"authenticated": False, "user": None}

            # Return session data
            return {
                "authenticated": True,
                "user": {
                    "user_id": session_data.get("user_id"),
                    "email": session_data.get("email"),
                    "name": session_data.get("name"),
                },
            }
        except SignatureExpired:
            logger.info(f"Expired session during status check")
            return {"authenticated": False, "user": None, "error": "expired_session"}
        except (BadTimeSignature, BadSignature) as e:
            logger.warning(f"Invalid session signature during status check: {e}")
            return {"authenticated": False, "user": None, "error": "invalid_session"}
        except Exception as e:
            logger.error(
                f"Unexpected error checking session status: {e}", exc_info=True
            )
            return {"authenticated": False, "user": None, "error": "server_error"}
