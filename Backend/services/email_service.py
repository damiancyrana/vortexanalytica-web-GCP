"""
Serwis do obsługi e-mail (Wersja Produkcyjna - Hybrydowa).
Singleton z pulą połączeń.
"""
from __future__ import annotations

import logging
import ssl
from email.message import EmailMessage
from typing import Optional, List, Dict # Dodano Dict
from smtplib import SMTP_SSL, SMTPException # Dodano SMTPException
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class EmailService:
    """ Serwis e-mail z pulą połączeń SMTP_SSL (Singleton). """
    _instance = None
    _smtp_connection_pool: Dict[str, Optional[SMTP_SSL]] = {}
    _initialized = False # Flaga inicjalizacji

    # Dane konfiguracyjne (ustawiane raz w __init__)
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    default_recipient: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    timeout: int = 15
    ssl_context: Optional[ssl.SSLContext] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            logger.debug("Tworzenie nowej instancji EmailService (Singleton).")
            cls._instance = super(EmailService, cls).__new__(cls)
            cls._instance._initialized = False # Reset flagi dla nowej instancji
        return cls._instance

    def __init__(self, smtp_user: str, smtp_pass: str, default_recipient: str,
                 smtp_host: str = "smtp.gmail.com", smtp_port: int = 465, timeout: int = 15) -> None:
        """ Inicjalizuje serwis (tylko raz). Wymaga podania danych SMTP. """
        if self._initialized:
            # logger.debug("EmailService już zainicjalizowany, pomijanie __init__.")
            return

        logger.info(f"Inicjalizacja EmailService dla użytkownika {smtp_user}...")
        if not smtp_user or not smtp_pass or not default_recipient:
            # Ten błąd nie powinien wystąpić, jeśli tworzenie jest zarządzane poprawnie
            logger.critical("Próba inicjalizacji EmailService bez kompletu danych SMTP/odbiorcy!")
            raise ValueError("Dane SMTP i odbiorca są wymagane do inicjalizacji EmailService.")

        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass # TODO: Rozważ bezpieczniejsze przechowywanie hasła w pamięci
        self.default_recipient = default_recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.timeout = timeout
        try:
            self.ssl_context = ssl.create_default_context()
        except Exception as e:
             logger.error(f"Nie można utworzyć domyślnego kontekstu SSL: {e}")
             # Można rzucić błąd lub próbować działać bez kontekstu (niezalecane)
             raise RuntimeError("Failed to create SSL context for EmailService") from e

        self._initialized = True
        logger.info(f"EmailService zainicjalizowany pomyślnie (host: {self.smtp_host}:{self.smtp_port}).")

    @contextmanager
    def get_smtp_connection(self):
        """ Kontekstowy menedżer dla połączeń SMTP z puli. """
        if not self._initialized or not self.smtp_user:
             logger.critical("Próba uzyskania połączenia SMTP przez niezainicjalizowany EmailService!")
             raise RuntimeError("EmailService is not properly initialized.")

        connection_key = f"{self.smtp_host}:{self.smtp_port}"
        connection = self._smtp_connection_pool.get(connection_key)
        reused = False

        if connection:
            try:
                connection.noop() # Sprawdź czy połączenie żyje
                # logger.debug(f"Ponowne użycie połączenia SMTP {connection_key}")
                reused = True
                yield connection
                return # Zakończ, jeśli połączenie jest OK
            except (SMTPServerDisconnected, SMTPException, OSError) as e: # Łapiemy więcej błędów
                logger.warning(f"Nieaktywne połączenie SMTP w puli ({connection_key}): {e}. Zamykanie.")
                try: connection.quit()
                except: pass
                self._smtp_connection_pool[connection_key] = None # Usuń z puli
            except Exception as e: # Inne nieoczekiwane błędy
                 logger.error(f"Nieoczekiwany błąd podczas sprawdzania połączenia SMTP ({connection_key}): {e}", exc_info=True)
                 try: connection.quit()
                 except: pass
                 self._smtp_connection_pool[connection_key] = None

        # Utworzenie nowego połączenia
        logger.info(f"Tworzenie nowego połączenia SMTP do {connection_key}...")
        smtp: Optional[SMTP_SSL] = None # Inicjalizacja None
        try:
            smtp = SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout, context=self.ssl_context)
            # logger.debug(f"Połączono z SMTP: {connection_key}, logowanie...")
            smtp.login(self.smtp_user, self.smtp_pass)
            logger.info(f"Pomyślnie zalogowano do SMTP: {connection_key}")
            self._smtp_connection_pool[connection_key] = smtp # Dodaj do puli
            yield smtp
        except (SMTPException, OSError, ssl.SSLError, TimeoutError) as e: # Łapiemy typowe błędy
            logger.error(f"Błąd podczas łączenia lub logowania do SMTP ({connection_key}): {e}")
            if smtp: # Jeśli połączenie zostało częściowo utworzone, spróbuj zamknąć
                 try: smtp.quit()
                 except: pass
            # Usuń z puli w razie błędu
            self._smtp_connection_pool.pop(connection_key, None)
            raise RuntimeError(f"Failed to connect or login to SMTP server {connection_key}.") from e
        except Exception as e: # Inne błędy
             logger.error(f"Nieoczekiwany błąd podczas tworzenia połączenia SMTP ({connection_key}): {e}", exc_info=True)
             if smtp:
                  try: smtp.quit()
                  except: pass
             self._smtp_connection_pool.pop(connection_key, None)
             raise # Rzuć wyjątek dalej


    def send_email(self, subject: str, body: str, recipients: Optional[List[str]] = None, reply_to: Optional[str] = None, html_body: Optional[str] = None) -> None:
        """ Wysyła wiadomość e-mail używając połączenia z puli. """
        if not self._initialized:
             logger.error("Próba wysłania emaila przez niezainicjalizowany EmailService.")
             return # Cicho zignoruj

        final_recipients = recipients if recipients is not None else [self.default_recipient]
        if not final_recipients or not all(isinstance(r, str) and r for r in final_recipients):
             logger.error(f"Brak poprawnych odbiorców dla emaila (Temat: {subject}). Odbiorcy: {final_recipients}")
             return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(final_recipients)
        if reply_to: msg["Reply-To"] = reply_to
        msg.set_content(body)
        if html_body: msg.add_alternative(html_body, subtype="html")

        try:
            with self.get_smtp_connection() as smtp:
                smtp.send_message(msg)
                logger.info(f"Wysłano e-mail do {final_recipients} (Temat: {subject})")
        except (SMTPException, OSError, RuntimeError) as e: # Łapiemy też RuntimeError z get_smtp_connection
             logger.error(f"Błąd podczas wysyłania e-mail do {final_recipients} (Temat: {subject}): {e}", exc_info=True)
             # Można dodać logikę ponawiania
        except Exception as e:
             logger.error(f"Nieoczekiwany błąd podczas wysyłania e-mail: {e}", exc_info=True)


    def close_all_connections(self) -> None:
        """ Zamyka wszystkie aktywne połączenia SMTP w puli. Wywoływana przy shutdown aplikacji. """
        logger.info("Zamykanie wszystkich połączeń SMTP w puli EmailService...")
        closed_count = 0
        # Bezpieczniej iterować po kopii kluczy, gdy modyfikujemy słownik
        keys_to_close = list(self._smtp_connection_pool.keys())
        for key in keys_to_close:
            connection = self._smtp_connection_pool.pop(key, None) # Usuń z puli
            if connection:
                try:
                    # logger.debug(f"Zamykanie połączenia SMTP: {key}")
                    connection.quit()
                    closed_count += 1
                except (SMTPException, OSError):
                    # logger.warning(f"Błąd podczas zamykania połączenia SMTP ({key}): {e}")
                    pass # Ignorujemy błędy przy zamykaniu
                except Exception as e:
                     logger.warning(f"Nieoczekiwany błąd podczas zamykania połączenia SMTP ({key}): {e}", exc_info=True)
        logger.info(f"Zamknięto {closed_count} z {len(keys_to_close)} połączeń SMTP.")
        # Upewnijmy się, że pula jest pusta
        self._smtp_connection_pool.clear()