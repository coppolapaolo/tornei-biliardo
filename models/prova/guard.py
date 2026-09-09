"""«È di prova?» — per chi deve scartare (ADR-058).

Gamification e notifiche non devono reagire a ciò che succede dentro una
competizione di prova. Qui c'è la domanda, in tre forme: per una gara, per
un campionato, per un evento di dominio. Le risposte passano da query a
colonna singola con `include_prova=True`: il filtro di visibilità non deve
poter rispondere «non esiste» a chi chiede proprio se è una prova.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from sqlalchemy import select


def gara_e_di_prova(gara_id: Optional[int]) -> bool:
    if not gara_id:
        return False
    from models.base import db
    from models.competition.models import Gara

    valore = db.session.execute(
        select(Gara.is_prova)
        .where(Gara.id == gara_id)
        .execution_options(include_prova=True)
    ).scalar()
    return bool(valore)


def campionato_e_di_prova(campionato_id: Optional[int]) -> bool:
    if not campionato_id:
        return False
    from models.base import db
    from models.campionato.models import Campionato

    valore = db.session.execute(
        select(Campionato.is_prova)
        .where(Campionato.id == campionato_id)
        .execution_options(include_prova=True)
    ).scalar()
    return bool(valore)


def _gara_del_match(match_id: Optional[int]) -> Optional[int]:
    if not match_id:
        return None
    from models.base import db
    from models.match.models import Match

    return db.session.execute(
        select(Match.gara_id).where(Match.id == match_id)
    ).scalar()


def evento_di_prova(event: Any) -> bool:
    """True se l'evento riguarda una competizione di prova.

    Guarda gli attributi che gli eventi di dominio usano per dire di quale
    competizione parlano: `gara_id`, `campionato_id`, e in mancanza
    `match_id` (le sfide individuali non hanno gara e non sono mai di prova).
    """
    gara_id = getattr(event, "gara_id", None)
    if gara_id:
        return gara_e_di_prova(gara_id)
    campionato_id = getattr(event, "campionato_id", None)
    if campionato_id:
        return campionato_e_di_prova(campionato_id)
    if getattr(event, "match_id", None) and not hasattr(event, "gara_id"):
        return gara_e_di_prova(_gara_del_match(event.match_id))
    return False


def senza_prove(handler: Callable[[Any], None]) -> Callable[[Any], None]:
    """Avvolge un handler di eventi perché ignori le competizioni di prova."""

    @wraps(handler)
    def _guardato(event: Any) -> None:
        if evento_di_prova(event):
            return
        handler(event)

    return _guardato
