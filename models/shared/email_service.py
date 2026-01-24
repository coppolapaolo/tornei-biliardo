"""
Module: models/shared/email_service.py
Purpose: Service for sending system emails (verification, password reset) via SMTP
"""

import os
import logging
from typing import Optional
from flask import current_app
from flask_mail import Message

from ..base import mail
from ..user.models import User
from ..user.tokens import UserToken

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails using Flask-Mail (SMTP)."""

    @staticmethod
    def _get_sender() -> str:
        DEFAULT = "Campionato Biliardo <noreply@campionato.local>"
        try:
            return current_app.config.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_DEFAULT_SENDER") or DEFAULT
        except ImportError:
            return os.environ.get("MAIL_DEFAULT_SENDER") or DEFAULT
        except RuntimeError:
             # Outside application context
             return os.environ.get("MAIL_DEFAULT_SENDER") or DEFAULT

    @staticmethod
    def send_email(to_email: str, subject: str, html_content: str) -> bool:
        """Send an email using SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: Email body (HTML)

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not mail:
            logger.warning("Flask-Mail not initialized. Email not sent.")
            return False

        try:
            msg = Message(
                subject=subject,
                sender=EmailService._get_sender(),
                recipients=[to_email],
                html=html_content
            )
            mail.send(msg)
            logger.info(f"Email sent to {to_email} with subject: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    @staticmethod
    def send_verification_email(user: User, token: UserToken, base_url: str) -> bool:
        """Send verification email to user."""
        verification_url = f"{base_url}/auth/verify-email/{token.token}"
        
        subject = "Verifica il tuo account - Campionato Biliardo"
        html_content = f"""
        <h1>Benvenuto {user.username}!</h1>
        <p>Grazie per esserti registrato al Campionato Biliardo.</p>
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
        
        subject = "Reset Password - Campionato Biliardo"
        html_content = f"""
        <h1>Reset Password</h1>
        <p>Ciao {user.username},</p>
        <p>Abbiamo ricevuto una richiesta di reset della password per il tuo account.</p>
        <p>Clicca sul link sottostante per impostare una nuova password:</p>
        <p><a href="{reset_url}">Resetta Password</a></p>
        <p>Se non hai richiesto il reset, ignora questa email.</p>
        <p>Il link scadrà tra 24 ore.</p>
        """
        
        return EmailService.send_email(user.email, subject, html_content)
