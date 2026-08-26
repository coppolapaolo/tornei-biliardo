"""
Module: models/shared/email_service.py
Purpose: Service for sending system emails (verification, password reset) via SMTP
"""

import os
import logging
import threading
import time
from typing import Callable, Sequence

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

# Quanto aspettare **prima di ogni ritentativo**: due ripetizioni oltre al
# tentativo iniziale, quindi tre invii tentati in tutto nell'arco di ~10s.
#
# Non e' prudenza generica, sono i guasti che si sono visti davvero (GlitchTip,
# aprile-agosto 2026): `EOF occurred in violation of protocol`,
# `Connection unexpectedly closed`, `please run connect() first` — tutti modi
# diversi di dire che la connessione SMTP e' caduta, tutti transitori. Con un
# tentativo solo, l'email non arriva e chi l'aspettava non lo sa: la route ha
# gia' risposto «Controlla la tua casella di posta», e per il recupero password
# il silenzio e' pure deliberato (anti-enumerazione degli account). Un utente ha
# chiesto la verifica tre volte in un'ora e mezza senza ricevere nulla.
#
# Le attese sono lunghe perche' il thread e' in secondo piano e non trattiene
# nessuna risposta HTTP: l'unico costo e' un thread che dorme.
RITENTATIVI_ATTESE = (2, 8)


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
    def _invia_con_ritentativi(
        msg,  # type: ignore[no-untyped-def]
        to_email: str,
        subject: str,
        attese: Sequence[float] = RITENTATIVI_ATTESE,
        pausa: Callable[[float], None] = time.sleep,
    ) -> bool:
        """Prova a spedire, e ci riprova finche' le attese non sono finite.

        Vive fuori da `send_email` per due ragioni: gira nel thread di invio,
        dove non c'e' nessuno a cui restituire un esito, ed e' l'unico pezzo
        che si possa provare senza far partire un thread — `pausa` iniettabile
        e' li' apposta.

        Un fallimento intermedio e' un `warning` e non un `error`: se il
        tentativo dopo riesce, l'email e' arrivata e non c'e' niente da
        guardare. L'`error` resta per la resa definitiva, che e' l'unico caso
        in cui qualcuno non ricevera' mai la sua email.
        """
        totale = len(attese) + 1  # il tentativo iniziale non ha attesa davanti
        ultimo_errore: Exception | None = None

        for numero in range(1, totale + 1):
            try:
                mail.send(msg)
                coda = f" (al tentativo {numero})" if numero > 1 else ""
                logger.info(f"Email sent to {to_email} with subject: {subject}{coda}")
                return True
            except Exception as e:  # noqa: BLE001 - qualunque guasto va ritentato
                ultimo_errore = e
                if numero < totale:
                    attesa = attese[numero - 1]
                    logger.warning(
                        f"Invio a {to_email} fallito al tentativo {numero}"
                        f"/{totale}, riprovo fra {attesa}s: {e}"
                    )
                    pausa(attesa)

        # Il messaggio conserva il prefisso storico «Failed to send email to»:
        # e' il titolo con cui queste issue esistono su GlitchTip, e cambiarlo
        # ne aprirebbe di nuove, scollegate dalle precedenti.
        logger.error(
            f"Failed to send email to {to_email}: {ultimo_errore} "
            f"(dopo {totale} tentativi)"
        )
        return False

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
                    EmailService._invia_con_ritentativi(msg, to_email, subject)

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
    def send_password_reset_email(
        user: User, token: "UserToken | str", base_url: str
    ) -> bool:
        """Send password reset email to user.

        `token` puo' essere l'oggetto o la sola stringa. Chi invia **dopo** il
        commit (`UserProfileService.request_password_reset`) passa la stringa,
        per non dipendere da un oggetto ORM che a quel punto e' scaduto.
        """
        token_str = token if isinstance(token, str) else token.token
        reset_url = f"{base_url}/auth/reset-password/{token_str}"

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
