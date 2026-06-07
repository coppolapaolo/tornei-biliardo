"""Tracciamento leggero dell'attività utente (ADR-036).

Aggiorna ``User.last_active_at`` a ogni richiesta autenticata, ma con un
*throttle*: scrive solo se il timestamp è assente o più vecchio di
``throttle_minutes`` — così la stragrande maggioranza delle richieste non
genera alcuna scrittura. Usato dall'auto-refresh dei segnali-domanda.
"""

from __future__ import annotations

from datetime import timedelta

from models.base import db, utc_now

# Frequenza massima di scrittura del timestamp di attività.
ACTIVITY_THROTTLE_MINUTES = 60


def touch_user_activity(
    user, throttle_minutes: int = ACTIVITY_THROTTLE_MINUTES
) -> bool:
    """Aggiorna ``last_active_at`` se "stantio"; ritorna True se ha scritto.

    Pensata per l'hook ``before_request``: errori isolati (non deve mai far
    fallire la richiesta). Esegue il commit della sola modifica del timestamp.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    now = utc_now()
    last = getattr(user, "last_active_at", None)
    if last is not None and (now - last) < timedelta(minutes=throttle_minutes):
        return False

    try:
        user.last_active_at = now
        db.session.commit()
        return True
    except Exception:
        import logging

        db.session.rollback()
        logging.getLogger(__name__).debug(
            "touch_user_activity: aggiornamento last_active_at fallito", exc_info=True
        )
        return False
