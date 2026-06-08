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
        # NOTA: commit manuale *intenzionale*, eccezione documentata alla regola
        # "niente db.session.commit() a mano / usa @transactional".
        # Perché NON @transactional qui:
        #   1) È un effetto collaterale "best-effort" dentro un hook
        #      before_request: se fallisce NON deve far fallire la richiesta.
        #      @transactional ri-solleva l'eccezione (manager.py: `raise` dopo il
        #      rollback) → un intoppo sul timestamp diventerebbe un 500 sulla
        #      pagina. Qui invece l'errore viene ingoiato di proposito.
        #   2) C'è una sola sessione per richiesta: @transactional farebbe
        #      comunque commit() sulla stessa sessione, quindi non isolerebbe il
        #      commit dallo stato in sospeso — non risolverebbe nulla.
        # Sicurezza: questo è l'ULTIMO before_request e i precedenti
        # (enforce_endpoint_allowlist / enforce_onboarding) sono read-only, quindi
        # alla commit non c'è altro stato applicativo in sospeso. Se in futuro si
        # aggiunge un before_request che SCRIVE prima di questo, va rivalutato.
        db.session.commit()
        return True
    except Exception:
        import logging

        db.session.rollback()
        logging.getLogger(__name__).debug(
            "touch_user_activity: aggiornamento last_active_at fallito", exc_info=True
        )
        return False
