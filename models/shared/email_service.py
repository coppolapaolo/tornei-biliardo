"""
Module: models/shared/email_service.py
Purpose: Service for sending system emails (verification, password reset) via SMTP
"""

import os
import logging
import threading
from flask import current_app
from flask_mail import Message
from markupsafe import escape

from config import Config

from ..base import mail
from ..user.models import User
from ..user.tokens import UserToken

logger = logging.getLogger(__name__)

# Il nome dell'app arriva da Config e non da current_app: queste stringhe
# servono anche fuori da una richiesta (thread di invio, script da console).
APP_NAME = Config.APP_NAME


class EmailService:
    """Service for sending emails using Flask-Mail (SMTP).

    Emails are sent asynchronously in a background thread to avoid
    blocking the request. The send_email method returns True optimistically;
    actual send failures are logged.
    """

    @staticmethod
    def _get_sender() -> str:
        DEFAULT = f"{APP_NAME} <noreply@torneibiliardo.it>"
        try:
            return (
                current_app.config.get("MAIL_DEFAULT_SENDER")
                or os.environ.get("MAIL_DEFAULT_SENDER")
                or DEFAULT
            )
        except RuntimeError:
            # Fuori dall'application context current_app (LocalProxy) solleva
            # RuntimeError. config.get/os.environ.get non sollevano mai
            # ImportError → quel ramo era dead code, rimosso.
            return os.environ.get("MAIL_DEFAULT_SENDER") or DEFAULT

    @staticmethod
    def send_email(to_email: str, subject: str, html_content: str) -> bool:
        """Send an email asynchronously using SMTP.

        The email is dispatched in a background thread so the HTTP response
        is not blocked by SMTP latency. Returns True optimistically.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: Email body (HTML)

        Returns:
            bool: True if the email was queued, False if mail is not configured
        """
        if not mail:
            logger.warning("Flask-Mail not initialized. Email not sent.")
            return False

        try:
            app = current_app._get_current_object()
            msg = Message(
                subject=subject,
                sender=EmailService._get_sender(),
                recipients=[to_email],
                html=html_content,
            )

            def _send(app, msg):  # type: ignore[no-untyped-def]
                with app.app_context():
                    try:
                        mail.send(msg)
                        logger.info(f"Email sent to {to_email} with subject: {subject}")
                    except Exception as e:
                        logger.error(f"Failed to send email to {to_email}: {e}")

            t = threading.Thread(target=_send, args=(app, msg), daemon=True)
            t.start()
            return True
        except Exception as e:
            logger.error(f"Failed to prepare email to {to_email}: {e}")
            return False

    @staticmethod
    def send_verification_email(user: User, token: UserToken, base_url: str) -> bool:
        """Send verification email to user."""
        verification_url = f"{base_url}/auth/verify-email/{token.token}"

        subject = f"Verifica il tuo account - {APP_NAME}"
        # XSS fix: lo username è dato utente non vincolato e finisce in HTML.
        # Va escapato (markupsafe) per non iniettare markup nell'email.
        safe_username = escape(user.username)
        html_content = f"""
        <h1>Benvenuto {safe_username}!</h1>
        <p>Grazie per esserti registrato a {APP_NAME}.</p>
        <p>Per favore, verifica la tua email cliccando sul link sottostante:</p>
        <p><a href="{verification_url}">Verifica Email</a></p>
        <p>Se non hai richiesto questa registrazione, puoi ignorare questa email.</p>
        <p>Il link scadrà tra 24 ore.</p>
        """

        return EmailService.send_email(user.email, subject, html_content)

    @staticmethod
    def send_password_reset_email(user: User, token: UserToken, base_url: str) -> bool:
        """Send password reset email to user."""
        reset_url = f"{base_url}/auth/reset-password/{token.token}"

        subject = f"Reset Password - {APP_NAME}"
        safe_username = escape(user.username)  # XSS: escape dato utente in HTML
        html_content = f"""
        <h1>Reset Password</h1>
        <p>Ciao {safe_username},</p>
        <p>Abbiamo ricevuto una richiesta di reset della password
        per il tuo account.</p>
        <p>Clicca sul link sottostante per impostare una nuova password:</p>
        <p><a href="{reset_url}">Resetta Password</a></p>
        <p>Se non hai richiesto il reset, ignora questa email.</p>
        <p>Il link scadrà tra 24 ore.</p>
        """

        return EmailService.send_email(user.email, subject, html_content)
