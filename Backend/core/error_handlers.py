"""
Moduł obsługi błędów dla aplikacji Vortex Analytica.
Dostarcza spersonalizowane strony błędów dla różnych kodów HTTP.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional, Union

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

def register_error_handlers(app: FastAPI, templates: Jinja2Templates) -> None:
    """
    Rejestruje wszystkie handlery błędów dla aplikacji FastAPI.

    Args:
        app: Instancja aplikacji FastAPI
        templates: Instancja Jinja2Templates do renderowania stron błędów
    """

    @app.exception_handler(404)
    @app.exception_handler(StarletteHTTPException)
    async def not_found_exception_handler(request: Request, exc: Union[StarletteHTTPException, Any]) -> HTMLResponse:
        """
        Obsługuje błędy 404 i inne błędy HTTP z kodem statusu.
        Przekierowuje na stronę logowania, jeśli błąd to 401 Unauthorized.
        """
        status_code = getattr(exc, "status_code", 404)

        # Redirect to login page for unauthorized users
        if status_code == status.HTTP_401_UNAUTHORIZED:
            logger.info(f"Unauthorized access attempt to {request.url.path}, redirecting to login")
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

        if status_code != 404:
            # Log detailed error information but show only minimal info to user
            detail = getattr(exc, "detail", "Unknown error")
            logger.error(f"HTTP Exception {status_code}: {detail} at {request.url.path}")

        try:
            # Map status codes to template names including the 'error/' subdirectory
            template_map = {
                400: "error/400.html", # ZAKTUALIZOWANO ścieżkę
                401: "error/401.html", # ZAKTUALIZOWANO ścieżkę
                403: "error/403.html", # ZAKTUALIZOWANO ścieżkę
                404: "error/404.html", # ZAKTUALIZOWANO ścieżkę
                429: "error/429.html", # ZAKTUALIZOWANO ścieżkę
                500: "error/500.html", # ZAKTUALIZOWANO ścieżkę
                503: "error/503.html"  # ZAKTUALIZOWANO ścieżkę
            }

            # Redirect to login page for unauthorized users
            if status_code == status.HTTP_401_UNAUTHORIZED:
                logger.info(f"Unauthorized access attempt to {request.url.path}, redirecting to login")
                return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

            # Redirect to payment required page for 402
            if status_code == status.HTTP_402_PAYMENT_REQUIRED:
                logger.info(f"Payment required for {request.url.path}, redirecting to payment page")
                return RedirectResponse(url="/payment-required", status_code=status.HTTP_302_FOUND)

            # Use specific template if available, otherwise use an appropriate fallback
            if status_code in template_map:
                template_name = template_map[status_code]
            elif 400 <= status_code < 500:
                template_name = "error/400.html"  # Generic client error (use error subdir)
            else:
                template_name = "error/500.html"  # Generic server error (use error subdir)

            logger.debug(f"Attempting to render error template: {template_name} for status code: {status_code}")
            return templates.TemplateResponse(
                template_name,
                {"request": request},
                status_code=status_code
            )
        

        except Exception as e:
            # Fallback to a basic HTML response if template rendering fails
            # Log error including which template failed
            logger.error(f"Error rendering error template '{locals().get('template_name', 'N/A')}': {e}", exc_info=True)
            status_message = {
                400: "Bad Request",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not Found",
                429: "Too Many Requests",
                500: "Internal Server Error",
                503: "Service Unavailable"
            }.get(status_code, "Error")

            html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>{status_code} - {status_message}</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                        h1 {{ color: #e74c3c; }}
                        a {{ color: #3498db; text-decoration: none; }}
                        a:hover {{ text-decoration: underline; }}
                    </style>
                </head>
                <body>
                    <h1>{status_code} - {status_message}</h1>
                    <p>Przepraszamy, wystąpił błąd.</p>
                    <p><a href="/">Wróć do strony głównej</a></p>
                </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=status_code)

    @app.exception_handler(500)
    @app.exception_handler(Exception)
    async def internal_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        """
        Obsługuje wewnętrzne błędy serwera (500) i ogólne wyjątki.
        """
        # Generate traceback info
        tb_str = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb_str = "".join(tb_str)

        # Log error with traceback
        logger.error(
            f"Internal error: {str(exc)} at {request.url.path}\n"
            f"Method: {request.method}\n"
            f"Traceback: \n{tb_str}"
        )

        try:
            # Render 500 error page using the correct path
            return templates.TemplateResponse(
                "error/500.html", # ZAKTUALIZOWANO ścieżkę
                {"request": request},
                status_code=500
            )
        except Exception as template_error:
            # Fallback to a basic HTML response if template rendering fails
            logger.error(f"Error rendering 500 template: {template_error}", exc_info=True)
            html_content = """
            <!DOCTYPE html>
            <html>
                <head>
                    <title>500 - Internal Server Error</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                        h1 { color: #e74c3c; }
                        a { color: #3498db; text-decoration: none; }
                        a:hover { text-decoration: underline; }
                    </style>
                </head>
                <body>
                    <h1>500 - Internal Server Error</h1>
                    <p>Przepraszamy, coś poszło nie tak po naszej stronie.</p>
                    <p><a href="/">Wróć do strony głównej</a></p>
                </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=500)