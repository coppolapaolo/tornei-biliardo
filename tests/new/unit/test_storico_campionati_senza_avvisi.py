"""Lo storico campionati non emette `SAWarning` e trova i campionati giusti.

GlitchTip, 2026-09-15 — `models/player/history_service.py:1132` e `:1141`:

`get_campionato_history` passava a `.in_()` due oggetti `.subquery()`.
SQLAlchemy 2.0 li converte da solo in un `select()`, e ogni volta scrive
«SAWarning: Coercing Subquery object into a select() for use in IN()».
Il risultato era corretto, ma ogni apertura della pagina produceva due voci su
GlitchTip, e una versione futura della libreria potrebbe smettere di fare la
conversione e rompere la pagina.

Il test trasforma l'avviso in errore, e controlla che la correzione non cambi
quali campionati compaiono.
"""

from __future__ import annotations

import uuid
import warnings
from datetime import date, time

import pytest
from sqlalchemy.exc import SAWarning

from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.matchmaking.configuration import MatchmakingStrategy
from models.player.history_service import PlayerHistoryService
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"sc_{uid}", email=f"sc_{uid}@test.local", role=UserRole.PLAYER.value
    )
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _gara(db_session, campionato_id: int | None) -> Gara:
    gara = Gara(
        number=1,
        name=f"G_{uuid.uuid4().hex[:8]}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        rounds_count=2,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
        status=GaraStatus.COMPLETED.value,
        campionato_id=campionato_id,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _campionato(db_session, **kwargs) -> Campionato:
    camp = Campionato(name=f"C_{uuid.uuid4().hex[:8]}", **kwargs)
    db_session.add(camp)
    db_session.flush()
    return camp


@pytest.mark.unit
def test_storico_campionati_non_emette_sawarning(db_session):
    user = _user(db_session)
    camp = _campionato(db_session)
    gara = _gara(db_session, camp.id)
    db_session.add(Inscription(user_id=user.id, gara_id=gara.id))
    db_session.flush()

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        pagination = PlayerHistoryService.get_campionato_history(user.id)

    assert [c.id for c in pagination.items] == [camp.id]


@pytest.mark.unit
def test_storico_campionati_esclude_ritiri_gare_singole_ed_eliminati(db_session):
    user = _user(db_session)

    partecipato = _campionato(db_session)
    db_session.add(
        Inscription(user_id=user.id, gara_id=_gara(db_session, partecipato.id).id)
    )

    ritirato = _campionato(db_session)
    db_session.add(
        Inscription(
            user_id=user.id,
            gara_id=_gara(db_session, ritirato.id).id,
            is_withdrawn=True,
        )
    )

    eliminato = _campionato(db_session, is_deleted=True)
    db_session.add(
        Inscription(user_id=user.id, gara_id=_gara(db_session, eliminato.id).id)
    )

    # Gara fuori da ogni campionato: non deve far comparire niente.
    db_session.add(Inscription(user_id=user.id, gara_id=_gara(db_session, None).id))

    # Campionato a cui partecipa solo un altro giocatore.
    altro = _user(db_session)
    estraneo = _campionato(db_session)
    db_session.add(
        Inscription(user_id=altro.id, gara_id=_gara(db_session, estraneo.id).id)
    )
    db_session.flush()

    pagination = PlayerHistoryService.get_campionato_history(user.id)

    assert [c.id for c in pagination.items] == [partecipato.id]


@pytest.mark.unit
def test_scheda_campionati_dello_storico_si_apre(db_session, client):
    """La pagina che GlitchTip segnalava: nessun altro test la apre."""
    user = _user(db_session)
    camp = _campionato(db_session)
    db_session.add(Inscription(user_id=user.id, gara_id=_gara(db_session, camp.id).id))
    db_session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        response = client.get("/player/history?tab=campionati")

    assert response.status_code == 200
    assert camp.name in response.get_data(as_text=True)
