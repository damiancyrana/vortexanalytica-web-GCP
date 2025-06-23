"""
Moduł tras ustawień użytkownika (Wersja Produkcyjna)
"""
from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from Backend.core.dependencies import get_template_context, get_current_active_user
from Backend.core.subscription_dependencies import get_subscription_info
from Backend.core.config import Settings

logger = logging.getLogger(__name__)


def register_settings_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """Rejestruje trasy związane z ustawieniami użytkownika"""
    
    @app.get("/settings", response_class=HTMLResponse, name="settings_page")
    async def settings_page(
        request: Request,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        subscription_info: Dict[str, Any] = Depends(get_subscription_info),
        context: dict = Depends(get_template_context)
    ) -> HTMLResponse:
        """Wyświetla stronę ustawień użytkownika z informacjami o subskrypcji"""
        
        logger.info(f"Dostęp do /settings dla użytkownika: {current_user_session.get('email')}")
        
        # Dodaj informacje o subskrypcji do kontekstu
        context['subscription'] = subscription_info or {'status': 'no_subscription'}
        
        # Formatuj cenę
        if subscription_info and subscription_info.get('amount'):
            context['subscription']['formatted_amount'] = f"{subscription_info['amount'] / 100:.2f}"
        
        # Określ czy pokazać przycisk "Upgrade"
        context['show_upgrade'] = not subscription_info or subscription_info.get('status') in ['no_subscription', 'canceled']
        
        # Dodaj Stripe publishable key dla frontend
        context['stripe_publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
        
        return templates.TemplateResponse("settings.html", context)
    
    @app.get("/payment-required", response_class=HTMLResponse)
    async def payment_required_page(
        request: Request,
        context: dict = Depends(get_template_context)
    ) -> HTMLResponse:
        """Strona informująca o wymaganej płatności"""
        
        # Dodaj Stripe publishable key
        settings = get_template_context()
        context['stripe_publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
        
        return templates.TemplateResponse("payment_required.html", context)