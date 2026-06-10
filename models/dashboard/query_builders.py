"""
Module: models/dashboard/query_builders.py
Purpose: Dashboard query builders and gara annotation helpers
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.campionato.models import Campionato
from models.user.models import DirectorAssignment
from models.competition.models import Gara, Inscription
from models.status_enum import GaraStatus


def campionatos_q():
    """Campionati visibili nelle viste pubbliche (dashboard, archivio).

    Filtra solo i soft-deleted (`is_deleted=True`); include i terminated
    (`is_active=False` + `terminated_at IS NOT NULL`) perché vanno mostrati
    come archivio storico — il campionato esiste ancora, è solo concluso.

    Coerente con `HomepageService.get_homepage_data` e
    `routes/main.py:public_campionatos_list`.
    """
    return (
        db.session.query(Campionato)
        .filter(Campionato.is_deleted.is_(False))
        .options(joinedload(getattr(Campionato, "gare")))
        .order_by(Campionato.created_at.desc())
    )


def managed_campionatos_q(user_id: int):
    """Campionati managed by a specific director (non-deleted)."""
    return (
        db.session.query(Campionato)
        .filter(Campionato.is_deleted.is_(False))
        .join(
            DirectorAssignment,
            (DirectorAssignment.entity_type == "campionato")
            & (DirectorAssignment.entity_id == Campionato.id)
            & (DirectorAssignment.user_id == user_id),
        )
        .options(joinedload(getattr(Campionato, "gare")))
        .order_by(Campionato.created_at.desc())
    )


def standalone_q():
    """Standalone gare (no campionato) ordered by date."""
    return (
        db.session.query(Gara)
        .filter(Gara.campionato_id.is_(None))
        .order_by(Gara.date.asc().nullslast(), Gara.name.asc())
    )


def annotate_garas_with_flags(provas: Optional[List[Gara]]) -> List[Gara]:
    """Arricchisce le Gare per la UI con flag derivati (no logica in Jinja)."""
    if not provas:
        return []
    for p in provas:
        p.is_inscription_open = p.get_real_status() == GaraStatus.INSCRIPTION.value
    return provas


def standalone_available_for_user(
    user_id: int, *, exclude_director_id: Optional[int] = None
) -> List[Gara]:
    """
    Standalone disponibili per iscrizione:
    - stato = INSCRIPTION o SETUP
    - utente NON già iscritto
    - opzionale: escludi quelle gestite da exclude_director_id
    """
    subq_all_my_gara_ids = (
        select(Inscription.gara_id)
        .where(Inscription.user_id == user_id)
        .scalar_subquery()
    )

    # B22: SETUP gare with a past date are zombie (forgotten) — hide from
    # player dashboard. INSCRIPTION/PLAYING/AWAITING_SSR are always shown
    # regardless of date.
    from datetime import date as _date

    today = _date.today()
    q = standalone_q().filter(
        or_(
            Gara.status == GaraStatus.INSCRIPTION.value,
            and_(
                Gara.status == GaraStatus.SETUP.value,
                or_(Gara.date.is_(None), Gara.date >= today),
            ),
        ),
        ~Gara.id.in_(subq_all_my_gara_ids),
    )

    if exclude_director_id is not None and hasattr(Gara, "director_id"):
        q = q.filter(
            or_(
                Gara.director_id.is_(None),
                Gara.director_id != exclude_director_id,
            )
        )

        co_director_gara_ids = (
            db.session.query(DirectorAssignment.entity_id)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.user_id == exclude_director_id,
            )
            .scalar_subquery()
        )
        q = q.filter(~Gara.id.in_(co_director_gara_ids))

    gare = q.all()

    for p in gare:
        p.is_inscription_open = p.get_real_status() == GaraStatus.INSCRIPTION.value

    return gare
