"""
Middleware do sprawdzania statusu subskrypcji (Opcjonalne)
"""
from __future__ import annotations

import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Ścieżki które wymagają aktywnej subskrypcji
PROTECTED_PATHS = [
    "/index",
    "/api/index-data",
    "/api/news",
    "/api/narrative",
    # Dodaj więcej chronionych ścieżek według potrzeb
]

# Ścieżki które są zawsze dostępne
PUBLIC_PATHS = [
    "/",
    "/login",
    "/logout",
    "/auth",
    "/api/auth",
    "/static",
    "/settings",
    "/payment-required",
    "/payment-success",
    "/api/payments",
    "/webhook",
    "/contact",
]


class SubscriptionMiddleware(BaseHTTPMiddleware):
    """
    Middleware który sprawdza czy użytkownik ma aktywną subskrypcję
    dla chronionych ścieżek.
    
    Uwaga: To jest opcjonalne rozwiązanie. Główna weryfikacja
    odbywa się przez dependency require_active_subscription.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Sprawdź czy ścieżka wymaga subskrypcji
        requires_subscription = any(
            path.startswith(protected) for protected in PROTECTED_PATHS
        )
        
        # Pomiń jeśli to publiczna ścieżka
        is_public = any(
            path.startswith(public) for public in PUBLIC_PATHS
        )
        
        if requires_subscription and not is_public:
            # Tu możesz dodać dodatkową logikę sprawdzania
            # Na razie polegamy na dependencies w routes
            pass
        
        response = await call_next(request)
        return response