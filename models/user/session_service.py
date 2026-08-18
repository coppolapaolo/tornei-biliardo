"""
Module: models/user/session_service.py
Purpose: apre, tiene viva e chiude le sessioni di `UserSession`.

Il tracciamento si aggancia ai segnali di Flask-Login (`user_logged_in`,
`user_logged_out`) invece che alle route: `login_user()` e' chiamata da tre
punti diversi (login normale, quick-login di sviluppo, cancellazione account),
e un quarto domani non se lo ricorderebbe nessuno.

Il segno di vita si aggiorna in `after_request`, e **solo per le risposte
HTML**. Le pagine che interrogano il server a intervalli regolari
risponderebbero altrimenti «e' ancora qui» a un browser lasciato aperto su un
tavolo vuoto: la durata media diventerebbe una misura di quanto restano aperte
le schede, non di quanto la gente usa il sito.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import request, session

from ..base import db, utc_now
from ..transaction.manager import transactional
from .session_models import INATTIVITA_MASSIMA, UserSession

logger = logging.getLogger(__name__)

# Chiavi nella sessione di Flask. `_accesso_visto` e' un epoch: evita una
# SELECT per ogni richiesta solo per scoprire che non e' ancora ora di
# scrivere. Il cookie e' firmato, quindi non e' falsificabile; e comunque ogni
# scrittura filtra anche per `user_id`, quindi al massimo si toccherebbe una
# riga propria.
CHIAVE_ID = "_accesso_id"
CHIAVE_VISTO = "_accesso_visto"

# Ogni quanto scrivere `last_seen_at`. Piu' fitto non aggiunge informazione e
# su PythonAnywhere ogni UPDATE si paga.
PASSO_AGGIORNAMENTO_SECONDI = 60


def _dispositivo(user_agent: Optional[str]) -> Optional[str]:
    """Famiglia di dispositivo, non l'impronta.

    Dello user agent teniamo la sola risposta alla domanda «da cosa entra la
    gente»: la stringa intera identifica un browser fra mille, e non ci serve.
    """
    if not user_agent:
        return None
    ua = user_agent.lower()
    if "ipad" in ua or ("android" in ua and "mobile" not in ua) or "tablet" in ua:
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    return "desktop"


class UserSessionService:
    """Ciclo di vita di una permanenza sul sito."""

    @staticmethod
    @transactional(domain="user")
    def apri(user_id: int, user_agent: Optional[str] = None) -> UserSession:
        """Apre una sessione e la ricorda nel cookie."""
        accesso = UserSession(
            user_id=user_id,
            started_at=utc_now(),
            last_seen_at=utc_now(),
            device=_dispositivo(user_agent),
        )
        db.session.add(accesso)
        db.session.flush()  # serve l'id subito, per metterlo nella sessione
        session[CHIAVE_ID] = accesso.id
        session[CHIAVE_VISTO] = utc_now().timestamp()
        return accesso

    @staticmethod
    @transactional(domain="user")
    def chiudi(user_id: int) -> None:
        """Chiude la sessione corrente all'ultimo istante certo."""
        accesso_id = session.pop(CHIAVE_ID, None)
        session.pop(CHIAVE_VISTO, None)
        if accesso_id is None:
            return
        accesso = db.session.get(UserSession, accesso_id)
        if accesso is None or accesso.user_id != user_id:
            return
        accesso.chiudi()

    @staticmethod
    @transactional(domain="user")
    def segna_vivo(user_id: int) -> None:
        """Aggiorna `last_seen_at`, o apre una sessione nuova dopo una pausa.

        La pausa lunga non allunga la sessione vecchia: la chiude all'ultimo
        istante certo e ne comincia un'altra. Senza questa regola un
        «ricordami» trasformerebbe una settimana in un unico accesso da sette
        giorni, e la durata media non vorrebbe piu' dire niente.
        """
        accesso_id = session.get(CHIAVE_ID)
        if accesso_id is None:
            UserSessionService.apri(user_id, request.headers.get("User-Agent"))
            return

        accesso = db.session.get(UserSession, accesso_id)
        if accesso is None or accesso.user_id != user_id:
            UserSessionService.apri(user_id, request.headers.get("User-Agent"))
            return

        adesso = utc_now()
        if adesso - accesso.last_seen_at > INATTIVITA_MASSIMA:
            accesso.chiudi()
            UserSessionService.apri(user_id, request.headers.get("User-Agent"))
            return

        accesso.last_seen_at = adesso
        session[CHIAVE_VISTO] = adesso.timestamp()

    @staticmethod
    def registra_attivita(user_id: int) -> None:
        """Punto d'ingresso di `after_request`: strozzato e a prova di guasto.

        Non deve mai far fallire una risposta gia' pronta: una tabella di
        statistiche non vale la pagina che l'utente stava guardando.
        """
        try:
            visto = session.get(CHIAVE_VISTO)
            adesso = utc_now().timestamp()
            if (
                visto is not None
                and adesso - float(visto) < PASSO_AGGIORNAMENTO_SECONDI
            ):
                return
            UserSessionService.segna_vivo(user_id)
        except Exception:
            logger.warning("Accesso non registrato", exc_info=True)
