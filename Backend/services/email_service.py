"""
Email service module (Production Version).
Singleton with connection pooling.
"""

from __future__ import annotations

import logging
import ssl
from email.message import EmailMessage
from typing import Optional, List, Dict
from smtplib import SMTP_SSL, SMTPException, SMTPServerDisconnected
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class EmailService:
    """Email service with SMTP_SSL connection pool (Singleton)."""

    _instance = None
    _smtp_connection_pool: Dict[str, Optional[SMTP_SSL]] = {}
    _initialized = False

    # Configuration data (set once in __init__)
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    default_recipient: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    timeout: int = 15
    ssl_context: Optional[ssl.SSLContext] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            logger.debug("Creating new EmailService instance (Singleton).")
            cls._instance = super(EmailService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        smtp_user: str,
        smtp_pass: str,
        default_recipient: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 465,
        timeout: int = 15,
    ) -> None:
        """Initialize service (only once). Requires SMTP data."""
        if self._initialized:
            return

        logger.info(f"Initializing EmailService for user {smtp_user}...")
        if not smtp_user or not smtp_pass or not default_recipient:
            logger.critical(
                "Attempt to initialize EmailService without complete SMTP/recipient data!"
            )
            raise ValueError(
                "SMTP data and recipient are required to initialize EmailService."
            )

        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.default_recipient = default_recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.timeout = timeout

        try:
            self.ssl_context = ssl.create_default_context()
        except Exception as e:
            logger.error(f"Cannot create default SSL context: {e}")
            raise RuntimeError("Failed to create SSL context for EmailService") from e

        self._initialized = True
        logger.info(
            f"EmailService initialized successfully (host: {self.smtp_host}:{self.smtp_port})."
        )

    @contextmanager
    def get_smtp_connection(self):
        """Context manager for SMTP connections from pool."""
        if not self._initialized or not self.smtp_user:
            logger.critical(
                "Attempt to get SMTP connection from uninitialized EmailService!"
            )
            raise RuntimeError("EmailService is not properly initialized.")

        connection_key = f"{self.smtp_host}:{self.smtp_port}"
        connection = self._smtp_connection_pool.get(connection_key)
        reused = False

        if connection:
            try:
                connection.noop()  # Check if connection is alive
                reused = True
                yield connection
                return  # End if connection is OK
            except (SMTPServerDisconnected, SMTPException, OSError) as e:
                logger.warning(
                    f"Inactive SMTP connection in pool ({connection_key}): {e}. Closing."
                )
                try:
                    connection.quit()
                except:
                    pass
                self._smtp_connection_pool[connection_key] = None
            except Exception as e:
                logger.error(
                    f"Unexpected error checking SMTP connection ({connection_key}): {e}",
                    exc_info=True,
                )
                try:
                    connection.quit()
                except:
                    pass
                self._smtp_connection_pool[connection_key] = None

        # Create new connection
        logger.info(f"Creating new SMTP connection to {connection_key}...")
        smtp: Optional[SMTP_SSL] = None
        try:
            smtp = SMTP_SSL(
                self.smtp_host,
                self.smtp_port,
                timeout=self.timeout,
                context=self.ssl_context,
            )
            smtp.login(self.smtp_user, self.smtp_pass)
            logger.info(f"Successfully logged in to SMTP: {connection_key}")
            self._smtp_connection_pool[connection_key] = smtp
            yield smtp
        except (SMTPException, OSError, ssl.SSLError, TimeoutError) as e:
            logger.error(
                f"Error connecting or logging in to SMTP ({connection_key}): {e}"
            )
            if smtp:
                try:
                    smtp.quit()
                except:
                    pass
            self._smtp_connection_pool.pop(connection_key, None)
            raise RuntimeError(
                f"Failed to connect or login to SMTP server {connection_key}."
            ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error creating SMTP connection ({connection_key}): {e}",
                exc_info=True,
            )
            if smtp:
                try:
                    smtp.quit()
                except:
                    pass
            self._smtp_connection_pool.pop(connection_key, None)
            raise

    def send_email(
        self,
        subject: str,
        body: str,
        recipients: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> None:
        """Sends email using connection from pool."""
        if not self._initialized:
            logger.error("Attempt to send email through uninitialized EmailService.")
            return

        final_recipients = (
            recipients if recipients is not None else [self.default_recipient]
        )
        if not final_recipients or not all(
            isinstance(r, str) and r for r in final_recipients
        ):
            logger.error(
                f"No valid recipients for email (Subject: {subject}). Recipients: {final_recipients}"
            )
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(final_recipients)
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        try:
            with self.get_smtp_connection() as smtp:
                smtp.send_message(msg)
                logger.info(f"Email sent to {final_recipients} (Subject: {subject})")
        except (SMTPException, OSError, RuntimeError) as e:
            logger.error(
                f"Error sending email to {final_recipients} (Subject: {subject}): {e}",
                exc_info=True,
            )
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}", exc_info=True)

    def close_all_connections(self) -> None:
        """Closes all active SMTP connections in pool. Called at application shutdown."""
        logger.info("Closing all SMTP connections in EmailService pool...")
        closed_count = 0
        keys_to_close = list(self._smtp_connection_pool.keys())

        for key in keys_to_close:
            connection = self._smtp_connection_pool.pop(key, None)
            if connection:
                try:
                    connection.quit()
                    closed_count += 1
                except (SMTPException, OSError):
                    pass
                except Exception as e:
                    logger.warning(
                        f"Unexpected error closing SMTP connection ({key}): {e}",
                        exc_info=True,
                    )

        logger.info(f"Closed {closed_count} of {len(keys_to_close)} SMTP connections.")
        self._smtp_connection_pool.clear()
