"""
Landing page routes module (Production Version).
Uses cookie session. /index requires session, API too.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from Backend.core.dependencies import get_template_context, get_current_active_user
from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def register_landing_routes(
    app: FastAPI, templates: Jinja2Templates, settings: Settings
) -> None:
    """Registers /, /index, /api/index-data routes."""

    @app.get("/", response_class=HTMLResponse, summary="Public welcome page")
    async def landing(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """Handles main landing page - public."""
        return templates.TemplateResponse("landing_page/landing_page.html", context)

    @app.get(
        "/daily_report",
        response_class=HTMLResponse,
        summary="Daily report subscription",
    )
    async def daily_report(
        context: dict = Depends(get_template_context),
    ) -> HTMLResponse:
        """Displays the daily report subscription page - public."""
        return templates.TemplateResponse("landing_page/daily_report.html", context)

    @app.get("/index", response_class=HTMLResponse, name="index_page_route")
    async def index(
        request: Request,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        context: dict = Depends(get_template_context),
    ) -> HTMLResponse:
        """Displays main application interface for logged-in user."""
        logger.info(
            f"Access to /index granted for UID: {current_user_session.get('email')}"
        )
        return templates.TemplateResponse("index.html", context)

    @app.get("/terms", response_class=HTMLResponse, summary="Terms of Service page")
    async def terms_of_service(
        context: dict = Depends(get_template_context),
    ) -> HTMLResponse:
        """Displays the Terms of Service page - public."""
        return templates.TemplateResponse(
            "landing_page/documents/terms_service.html", context
        )

    @app.get(
        "/intellectual-property",
        response_class=HTMLResponse,
        summary="Intellectual Property page",
    )
    async def intellectual_property(
        context: dict = Depends(get_template_context),
    ) -> HTMLResponse:
        """Displays the Intellectual Property Statement page - public."""
        return templates.TemplateResponse(
            "landing_page/documents/intellectual_property.html", context
        )

    @app.get("/security", response_class=HTMLResponse, summary="Security page")
    async def security(context: dict = Depends(get_template_context)) -> HTMLResponse:
        """Displays the Security page - public."""
        return templates.TemplateResponse(
            "landing_page/documents/security.html", context
        )

    @app.get("/api/index-data", summary="Fetches data for main page (requires session)")
    async def get_index_data(
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
    ) -> Dict[str, Any]:
        """Returns protected data for logged-in user."""
        user_email = current_user_session.get("email", "No email")
        user_uid = current_user_session.get("user_id")
        user_name = current_user_session.get("name")

        logger.info(f"Fetching API data for user from session: {user_email}")

        data = {
            "welcomeMessage": f"Welcome {user_name or user_email}!",
            "userUid": user_uid,
            "userEmail": user_email,
            "messages": [],  # Message data is now provided by /api/news endpoint
        }
        return data
