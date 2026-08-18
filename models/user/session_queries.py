"""
Module: models/user/session_queries.py
Purpose: le domande che si fanno alla traccia degli accessi.

Data Structures: FiltroAccessi, RigaAccesso, RiepilogoAccessi

Le date dei filtri arrivano dal modulo di ricerca, cioè **nel fuso di chi
guarda** (ADR-043), mentre `user_session` tiene naive-UTC come tutto il resto.
La conversione sta qui e solo qui: un admin a Londra che chiede «oggi» deve
ottenere il suo oggi, non quello di Roma.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, List, Optional, Sequence

from sqlalchemy import func, or_

from ..base import db, utc_now
from ..transaction.manager import read_only
from .models import User
from .session_models import INATTIVITA_MASSIMA, UserSession


@dataclass(frozen=True)
class FiltroAccessi:
    """Cosa ha chiesto di vedere l'admin."""

    dal: Optional[date] = None
    al: Optional[date] = None
    testo: Optional[str] = None
    ruolo: Optional[str] = None
    solo_collegati: bool = False


@dataclass(frozen=True)
class RiepilogoAccessi:
    """I quattro numeri in cima alla pagina."""

    accessi: int
    persone: int
    durata_media_secondi: int
    collegati_adesso: int


def _confine_utc(giorno: date, fine_giornata: bool) -> datetime:
    """Mezzanotte locale di `giorno` espressa in naive-UTC."""
    from utils.local_time import to_utc_naive

    locale = datetime.combine(giorno, time.max if fine_giornata else time.min)
    return to_utc_naive(locale)


class UserSessionQueryService:
    """Interroga `user_session` per la schermata degli accessi."""

    @staticmethod
    def _base(filtro: FiltroAccessi):
        query = db.session.query(UserSession, User).join(
            User, User.id == UserSession.user_id
        )

        if filtro.dal is not None:
            query = query.filter(
                UserSession.started_at >= _confine_utc(filtro.dal, False)
            )
        if filtro.al is not None:
            query = query.filter(
                UserSession.started_at <= _confine_utc(filtro.al, True)
            )
        if filtro.testo:
            like = f"%{filtro.testo.strip()}%"
            query = query.filter(or_(User.username.ilike(like), User.email.ilike(like)))
        if filtro.ruolo:
            query = query.filter(User.role == filtro.ruolo)
        if filtro.solo_collegati:
            query = query.filter(
                UserSession.ended_at.is_(None),
                UserSession.last_seen_at >= utc_now() - INATTIVITA_MASSIMA,
            )
        return query

    @staticmethod
    @read_only()
    def elenco(filtro: FiltroAccessi, limite: int = 300) -> Sequence[Any]:
        """Gli accessi che rispondono al filtro, dal più recente.

        Il limite non è una paginazione: è un tetto perché la pagina resti
        servibile su PythonAnywhere anche quando qualcuno chiede «tutto».
        Quando morde, la schermata lo dice — un elenco troncato in silenzio si
        legge come un elenco completo.
        """
        return (
            UserSessionQueryService._base(filtro)
            .order_by(UserSession.started_at.desc())
            .limit(limite)
            .all()
        )

    @staticmethod
    @read_only()
    def quanti(filtro: FiltroAccessi) -> int:
        return UserSessionQueryService._base(filtro).count()

    @staticmethod
    @read_only()
    def riepilogo(filtro: FiltroAccessi) -> RiepilogoAccessi:
        base = UserSessionQueryService._base(filtro).subquery()

        accessi, persone = db.session.query(
            func.count(base.c.id), func.count(func.distinct(base.c.user_id))
        ).one()

        # La durata la calcola SQLite: portarsi in Python trecento righe per
        # farne una media sarebbe lavoro inutile su un hosting lento.
        media = db.session.query(
            func.avg(
                func.julianday(func.coalesce(base.c.ended_at, base.c.last_seen_at))
                - func.julianday(base.c.started_at)
            )
        ).scalar()
        durata_media = int((media or 0) * 86400)

        collegati = (
            db.session.query(func.count(func.distinct(UserSession.user_id)))
            .filter(
                UserSession.ended_at.is_(None),
                UserSession.last_seen_at >= utc_now() - INATTIVITA_MASSIMA,
            )
            .scalar()
        ) or 0

        return RiepilogoAccessi(
            accessi=accessi or 0,
            persone=persone or 0,
            durata_media_secondi=durata_media,
            collegati_adesso=collegati,
        )

    @staticmethod
    @read_only()
    def per_utente(user_id: int, limite: int = 20) -> List[UserSession]:
        """Gli ultimi accessi di una persona sola, per la sua scheda."""
        return (
            UserSession.query.filter(UserSession.user_id == user_id)
            .order_by(UserSession.started_at.desc())
            .limit(limite)
            .all()
        )

    @staticmethod
    @read_only()
    def mai_entrati(giorni: int = 30) -> List[User]:
        """Chi si è registrato e non si è più fatto vedere.

        È la domanda che manda in fumo il senso di un'iscrizione: registrati
        da almeno `giorni` giorni, e nessun accesso registrato. Prima di
        questa tabella non si poteva sapere.
        """
        soglia = utc_now() - timedelta(days=giorni)
        con_accesso = db.session.query(UserSession.user_id).distinct()
        return (
            User.query.filter(
                User.created_at <= soglia,
                ~User.id.in_(con_accesso),
            )
            .order_by(User.created_at.desc())
            .all()
        )
