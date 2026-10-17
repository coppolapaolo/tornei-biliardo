"""Gli utenti storici che sono giocatori non registrati senza saperlo (ADR-086).

Prima dell'ADR-085 chi arrivava in sala senza account se lo vedeva creare dal
direttore, con un'email e una password che poi nessuno usava. In produzione
restano utenti che hanno giocato ma non sono **mai entrati**: sono non
registrati a tutti gli effetti, e senza creatore. Segnarli ``is_placeholder``
li rende riscattabili — e, non avendo un creatore, il riscatto lo conferma
**solo l'admin**.

I criteri sono quelli del piano, tutti insieme:

- nessuna riga in ``user_session``: non ha mai aperto una sessione;
- ``last_active_at`` NULL: nessuna richiesta autenticata registrata;
- ``onboarding_completed`` falso: l'onboarding si fa al primo accesso;
- almeno un'iscrizione: ha giocato, quindi c'è qualcosa da riscattare;
- non admin, non fittizio di una prova, non già non registrato, non cancellato.

Lo usa ``scripts/mark_placeholder_users.py``; la scelta si rivede prima di
scrivere, perché segnato non registrato un utente non entra più (il login lo
rifiuta) finché qualcuno non lo riscatta o l'admin non toglie il segno.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import exists, select

from models.base import db

from .models import User
from .role_enum import UserRole
from .session_models import UserSession


def candidati_storici() -> List[User]:
    """Gli utenti da segnare non registrati, in ordine di id."""
    from models.competition.models import Inscription

    ha_sessioni = exists().where(UserSession.user_id == User.id)
    ha_iscrizioni = exists().where(Inscription.user_id == User.id)
    query = (
        select(User)
        .where(
            User.role != UserRole.ADMIN.value,
            User.is_fittizio.is_(False),
            User.is_placeholder.is_(False),
            User.deleted_at.is_(None),
            User.onboarding_completed.is_(False),
            User.last_active_at.is_(None),
            ~ha_sessioni,
            ha_iscrizioni,
        )
        .order_by(User.id.asc())
    )
    return list(db.session.execute(query).scalars().all())


def segna(utenti: List[User]) -> int:
    """Segna non registrati gli utenti dati. Non fa commit: decide chi chiama."""
    for utente in utenti:
        utente.is_placeholder = True
    db.session.flush()
    return len(utenti)
