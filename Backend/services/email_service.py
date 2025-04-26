"""
Moduł zawierający serwis do obsługi wiadomości e-mail.
"""
from __future__ import annotations

import logging
import ssl
from email.message import EmailMessage
from typing import Optional, List
from smtplib import SMTP_SSL
from contextlib import contextmanager

# Logger
logger = logging.getLogger(__name__)


class EmailService:
    """
    Serwis do obsługi wysyłania wiadomości e-mail.
    Implementuje wzorzec Singleton dla optymalnego zarządzania zasobami.
    """
    # Zmienne klasowe do współdzielenia między instancjami
    _instance = None
    _smtp_connection_pool = {}
    
    def __new__(cls, *args, **kwargs):
        """Implementacja wzorca Singleton"""
        if cls._instance is None:
            cls._instance = super(EmailService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, smtp_user: str, smtp_pass: str, default_recipient: str, smtp_host: str = "smtp.gmail.com", smtp_port: int = 465, timeout: int = 15) -> None:
        """
        Inicjalizacja serwisu e-mail.
        
        Args:
            smtp_user (str): Nazwa użytkownika SMTP
            smtp_pass (str): Hasło SMTP
            default_recipient (str): Domyślny odbiorca
            smtp_host (str, optional): Host SMTP. Domyślnie "smtp.gmail.com".
            smtp_port (int, optional): Port SMTP. Domyślnie 465.
            timeout (int, optional): Limit czasu połączenia. Domyślnie 15.
        """
        # Inicjalizujemy tylko raz
        if getattr(self, '_initialized', False):
            return
            
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.default_recipient = default_recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.timeout = timeout
        
        # Kontext SSL dla bezpiecznych połączeń
        self.ssl_context = ssl.create_default_context()
        
        self._initialized = True
    
    @contextmanager
    def get_smtp_connection(self):
        """
        Kontekstowy menedżer dla połączeń SMTP.
        Zapewnia optymalnie wykorzystanie połączeń poprzez pulę.
        
        Yields:
            SMTP_SSL: Połączenie SMTP
        """
        # Klucz do identyfikacji połączenia
        connection_key = f"{self.smtp_host}:{self.smtp_port}"
        
        # Sprawdź czy mamy aktywne połączenie
        if connection_key in self._smtp_connection_pool and self._smtp_connection_pool[connection_key] is not None:
            try:
                # Sprawdź czy połączenie jest nadal aktywne
                self._smtp_connection_pool[connection_key].noop()
                # Jeśli tak, użyj istniejącego połączenia
                yield self._smtp_connection_pool[connection_key]
                return
            except Exception as e:
                # Połączenie nie jest aktywne, zamknij je i utwórz nowe
                logger.warning(f"Nieaktywne połączenie SMTP: {e}")
                try:
                    self._smtp_connection_pool[connection_key].quit()
                except:
                    pass
                self._smtp_connection_pool[connection_key] = None
        
        # Utworzenie nowego połączenia
        try:
            smtp = SMTP_SSL(
                self.smtp_host, 
                self.smtp_port, 
                timeout=self.timeout,
                context=self.ssl_context
            )
            smtp.login(self.smtp_user, self.smtp_pass)
            
            # Zapisz połączenie w puli
            self._smtp_connection_pool[connection_key] = smtp
            
            yield smtp
        except Exception as e:
            logger.error(f"Błąd podczas łączenia z serwerem SMTP: {e}")
            # Zamknij połączenie w przypadku błędu
            if connection_key in self._smtp_connection_pool:
                try:
                    self._smtp_connection_pool[connection_key].quit()
                except:
                    pass
                self._smtp_connection_pool[connection_key] = None
            raise
    
    def send_email(self, subject: str, body: str, recipients: Optional[List[str]] = None, reply_to: Optional[str] = None, html_body: Optional[str] = None) -> None:
        """
        Wysyła wiadomość e-mail.
        
        Args:
            subject (str): Temat wiadomości
            body (str): Treść wiadomości (plain text)
            recipients (Optional[List[str]], optional): Lista odbiorców. 
                Jeśli None, używa domyślnego odbiorcy.
            reply_to (Optional[str], optional): Adres odpowiedzi.
            html_body (Optional[str], optional): Treść HTML wiadomości.
        
        Raises:
            Exception: Błąd podczas wysyłania wiadomości
        """
        # Przygotowanie wiadomości
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        
        # Odbiorcy
        if recipients is None:
            recipients = [self.default_recipient]
        msg["To"] = ", ".join(recipients)
        
        # Adres odpowiedzi
        if reply_to:
            msg["Reply-To"] = reply_to
        
        # Treść wiadomości
        msg.set_content(body)
        
        # Opcjonalna treść HTML
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        
        # Wysłanie wiadomości
        with self.get_smtp_connection() as smtp:
            smtp.send_message(msg)
            logger.info(f"Wysłano wiadomość e-mail do {recipients}")
    
    def close_all_connections(self):
        """Zamyka wszystkie połączenia SMTP w puli"""
        for key, connection in self._smtp_connection_pool.items():
            if connection is not None:
                try:
                    connection.quit()
                except:
                    pass
        self._smtp_connection_pool.clear()