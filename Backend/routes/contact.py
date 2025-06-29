"""
Contact form handler module (Production Version).
Requires active cookie session.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import (
    FastAPI,
    BackgroundTasks,
    Form,
    Depends,
    status,
    HTTPException,
    Request,
)
from fastapi.responses import ORJSONResponse
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.services.email_service import EmailService
from Backend.core.dependencies import get_email_service, get_current_active_user

logger = logging.getLogger(__name__)


def register_contact_routes(
    app: FastAPI, templates: Jinja2Templates, settings: Settings
) -> None:
    """Registers POST /contact route."""

    @app.post(
        "/contact",
        response_class=ORJSONResponse,
        status_code=status.HTTP_202_ACCEPTED,
        summary="Sends contact form (requires session)",
    )
    async def contact(
        background_tasks: BackgroundTasks,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        email_service: EmailService = Depends(get_email_service),
        subject: str = Form(..., min_length=3, max_length=256),
        message: str = Form(..., min_length=10, max_length=10_000),
    ) -> ORJSONResponse:
        """Handles contact form from logged-in user."""
        user_name = current_user_session.get("name", "Anonymous User")
        user_email = current_user_session.get("email")
        user_id = current_user_session.get("user_id")

        if not user_email:
            logger.error(
                f"No email address in session for UID: {user_id} when sending contact."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No email address in your session.",
            )

        logger.info(f"Received contact form from user: {user_id} ({user_email})")

        body = (
            f"—— Vortex Analytica Contact Form ——\n"
            f"User ID: {user_id}\n"
            f"From: {user_name} <{user_email}>\n"
            f"Subject: {subject}\n\n"
            f"Message:\n{message}\n"
        )

        try:
            background_tasks.add_task(
                email_service.send_email,
                subject=f"[Vortex Contact] {subject}",
                body=body,
                reply_to=user_email,
            )
            return {"ok": True, "msg": "Message sent successfully."}
        except Exception as e:
            logger.error(
                f"Failed to send contact email from {user_id}: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send message. Please try again later.",
            )
