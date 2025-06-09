"""
Moduł obsługi formularza kontaktowego (Wersja Produkcyjna - Hybrydowa).
Wymaga aktywnej sesji ciasteczkowej.
"""
from __future__ import annotations

import logging
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, Form, Depends, status, HTTPException, Request
from fastapi.responses import ORJSONResponse
from fastapi.templating import Jinja2Templates # Nie używane bezpośrednio, ale może być w przyszłości
from pydantic import EmailStr # Użyj EmailStr do walidacji, jeśli email jest w Form

from Backend.core.config import Settings
from Backend.services.email_service import EmailService
from Backend.core.dependencies import get_email_service, get_current_active_user

logger = logging.getLogger(__name__)

def register_contact_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """ Rejestruje trasę POST /contact. """

    @app.post("/contact", response_class=ORJSONResponse, status_code=status.HTTP_202_ACCEPTED, summary="Wysyła formularz kontaktowy (wymaga sesji)")
    async def contact(
        background_tasks: BackgroundTasks,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        email_service: EmailService = Depends(get_email_service),
        subject: str = Form(..., min_length=3, max_length=256), # Dodano min_length
        message: str = Form(..., min_length=10, max_length=10_000), # Dodano min_length
    ) -> ORJSONResponse:
        """ Obsługuje formularz kontaktowy od zalogowanego użytkownika. """
        user_name = current_user_session.get("name", "Użytkownik Anonimowy") # Zapewnij fallback
        user_email = current_user_session.get("email")
        user_id = current_user_session.get("user_id")

        if not user_email:
             logger.error(f"Brak adresu email w sesji dla UID: {user_id} podczas wysyłania kontaktu.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Brak adresu email w Twojej sesji.")

        logger.info(f"Otrzymano formularz kontaktowy od użytkownika: {user_id} ({user_email})")

        body = (
            f"—— Formularz kontaktowy Vortex Analytica ——\n"
            f"Użytkownik ID: {user_id}\n"
            f"Nadawca : {user_name} <{user_email}>\n"
            f"Temat   : {subject}\n\n"
            f"Wiadomość:\n{message}\n"
        )

        try:
            background_tasks.add_task(
                email_service.send_email,
                subject=f"[Vortex Contact] {subject}",
                body=body,
                reply_to=user_email
            )
            return {"ok": True, "msg": "Wiadomość została pomyślnie wysłana."}
        except Exception as e:
            # Logowanie błędu dodawania zadania lub problemu z EmailService
            logger.error(f"Nie udało się wysłać emaila kontaktowego od {user_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nie udało się wysłać wiadomości. Spróbuj ponownie później.")