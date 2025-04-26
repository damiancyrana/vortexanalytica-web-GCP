from __future__ import annotations

import os, uvicorn
from email.message import EmailMessage
from functools import lru_cache
from smtplib import SMTP_SSL
from typing import Final
from fastapi import FastAPI, Request, BackgroundTasks, Form, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.cloud import secretmanager

# ─────────────────────────  USTAWIENIA STAŁE  ─────────────────────────
PROJECT_ID: Final[str] = "vortexanalytica"          # jeśli zmienisz projekt → podmień
MAIL_TO:    Final[str] = "vortexanalytica@gmail.com"

BASE_DIR      = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "Frontend", "templates")
STATIC_DIR    = os.path.join(BASE_DIR, "..", "Frontend", "static")

# ───────────────────────  SEKRETY SMTP (Secret Manager)  ───────────────
@lru_cache
def fetch_secret(secret_id: str) -> str:
    """Zwróć wartość wersji 'latest' sekretu z GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name   = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    resp   = client.access_secret_version(name=name)
    return resp.payload.data.decode()

SMTP_USER: Final[str] = fetch_secret("smtp-user")
SMTP_PASS: Final[str] = fetch_secret("smtp-pass")

# ─────────────────────────  FABRYKA APLIKACJI  ─────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(title="Vortex Analytica Landing", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # statyczne pliki (CSS, JS, obrazy)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # ——— ROUTES ——————————————————————————————————————————
    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "landing_page.html",
            {"request": request, "auth_url": os.getenv("AUTH_URL", "#")},
        )

    @app.get("/index", response_class=HTMLResponse)
    async def index_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {"request": request}
        )
    
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "login.html",
            {"request": request}
        )
    
    @app.post("/contact", response_class=JSONResponse,
              status_code=status.HTTP_202_ACCEPTED)
    async def contact(
        background_tasks: BackgroundTasks,
        name:    str = Form(..., max_length=128),
        email:   str = Form(...),
        subject: str = Form(..., max_length=256),
        message: str = Form(..., max_length=10_000),
    ) -> JSONResponse:
        body = (
            "—— Formularz kontaktowy Vortex Analytica ——\n\n"
            f"Nadawca : {name} <{email}>\n"
            f"Temat   : {subject}\n\n"
            f"Wiadomość:\n{message}\n"
        )
        background_tasks.add_task(send_mail, subject, body, reply_to=email)
        return {"ok": True, "msg": "Wiadomość została wysłana."}

    return app

# ─────────────────────────────  SMTP  ─────────────────────────────
def send_mail(subject: str, body: str, *, reply_to: str) -> None:
    msg = EmailMessage()
    msg["Subject"]  = f"[Vortex landing] {subject}"
    msg["From"]     = SMTP_USER
    msg["To"]       = MAIL_TO
    msg["Reply-To"] = reply_to
    msg.set_content(body)

    with SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)

# ───────────────────────────  LOCAL DEV  ──────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "Backend.app:create_app",
        host="0.0.0.0",
        port=8040,
        factory=True,
        reload=True,   # usuń w produkcji
    )