"""Uno username libero, a partire da un nome che si legge.

Lo usano i due generi di utenti che l'app crea al posto di una persona: i
fittizi di una prova (ADR-058) e i giocatori non ancora registrati (ADR-085).
In entrambi i casi lo username è il nome con cui si gioca — classifiche,
abbinamenti e segnapunti lo mostrano — quindi è «Maria Rossi», non un codice.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from models.base import db

#: La colonna `user.username` è lunga 80; il suffisso « (NN)» ne vuole qualcuno.
LUNGHEZZA_MASSIMA_BASE = 72


def username_libero(base: str) -> str:
    """`base`, o `base (2)`, `base (3)`… se è già preso.

    Due prove aperte insieme hanno entrambe una Maria Rossi: la seconda si
    chiama «Maria Rossi (2)». Si guarda **tutta** la tabella, fittizi di altre
    prove e utenti soft-eliminati compresi: il vincolo di unicità vale per
    tutte le righe, non per quelle visibili.
    """
    from models.user.models import User

    base = " ".join(base.split())[:LUNGHEZZA_MASSIMA_BASE].strip()
    presi = {
        nome
        for (nome,) in db.session.execute(
            select(User.username)
            .where(or_(User.username == base, User.username.like(f"{base} (%")))
            .execution_options(include_prova=True, include_deleted=True)
        ).all()
    }
    if base not in presi:
        return base
    n = 2
    while f"{base} ({n})" in presi:
        n += 1
    return f"{base} ({n})"


__all__ = ["username_libero", "LUNGHEZZA_MASSIMA_BASE"]
