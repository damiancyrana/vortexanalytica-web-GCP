"""
Moduł obsługujący trasy związane z formularzem kontaktowym.
"""
from __future__ import annotations

from fastapi import FastAPI, BackgroundTasks, Form, Depends, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from Backend.core.config import Settings
from Backend.services.email_service import EmailService
from Backend.core.dependencies import get_email_service


def register_contact_routes(app: FastAPI, templates: Jinja2Templates, settings: Settings) -> None:
    """
    Rejestruje trasy związane z formularzem kontaktowym.
    
    Args:
        app (FastAPI): Instancja aplikacji FastAPI
        templates (Jinja2Templates): Silnik szablonów
        settings (Settings): Konfiguracja aplikacji
    """
    
    @app.post("/contact", response_class=JSONResponse, status_code=status.HTTP_202_ACCEPTED)
    async def contact(
        background_tasks: BackgroundTasks,
        email_service: EmailService = Depends(get_email_service),
        name: str = Form(..., max_length=128),
        email: str = Form(...),
        subject: str = Form(..., max_length=256),
        message: str = Form(..., max_length=10_000),
    ) -> JSONResponse:
        """
        Obsługa formularza kontaktowego.
        
        Args:
            background_tasks (BackgroundTasks): Zadania wykonywane w tle
            email_service (EmailService): Serwis do obsługi wiadomości e-mail
            name (str): Imię i nazwisko
            email (str): Adres e-mail
            subject (str): Temat wiadomości
            message (str): Treść wiadomości
        
        Returns:
            JSONResponse: Odpowiedź w formacie JSON
        """
        # Przygotowanie treści wiadomości
        body = (
            "—— Formularz kontaktowy Vortex Analytica ——\n\n"
            f"Nadawca : {name} <{email}>\n"
            f"Temat   : {subject}\n\n"
            f"Wiadomość:\n{message}\n"
        )
        
        # Wysłanie wiadomości w tle
        background_tasks.add_task(
            email_service.send_email,
            subject=f"[Vortex landing] {subject}",
            body=body,
            reply_to=email
        )
        
        # Zwrócenie odpowiedzi
        return {"ok": True, "msg": "Wiadomość została wysłana."}