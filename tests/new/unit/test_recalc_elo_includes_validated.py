"""Regressione: il backfill ELO deve includere i match `validated`.

Bug (produzione 2026-06-18): `recalc_elo.py` selezionava i match da
riprocessare con `filter_by(status=COMPLETED.value)`, saltando quelli in stato
`validated` — lo stato finale normale dopo la conferma bilaterale dei due
giocatori. Poiché lo script prima AZZERA tutti gli ELO e poi riprocessa, dopo
un `recalc_elo.py --commit` i giocatori i cui match erano `validated`
restavano con `elo_rating = NULL` (sintomo: ELO dell'avversario non visibile
nella schermata di scoring).

Fix: `matches_to_process()` usa `MatchStatus.finished_values()`
(`completed` + `validated`).
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara
from models.match.models import Match
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import GaraStatus, MatchStatus
from models.rating.calculation_service import RatingCalculationService
from scripts.recalc_elo import matches_to_process


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    return u


def _gara_id(suffix):
    gara = Gara(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    db.session.add(gara)
    db.session.flush()
    return gara.id


def _match(gara_id, p1, p2, status):
    m = Match(
        gara_id=gara_id,
        round_number=1,
        player1_id=p1,
        player2_id=p2,
        player1_score=5,
        player2_score=2,
        winner_id=p1,
        status=status,
    )
    db.session.add(m)
    db.session.flush()
    return m


@pytest.mark.unit
def test_matches_to_process_includes_validated(db_session):
    """Un match `validated` deve comparire tra quelli da riprocessare."""
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "val_p1"), _user(suffix, "val_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara_id = _gara_id(suffix)

    validated = _match(gara_id, p1.id, p2.id, MatchStatus.VALIDATED.value)
    completed = _match(gara_id, p1.id, p2.id, MatchStatus.COMPLETED.value)

    ids = {m.id for m in matches_to_process()}
    assert validated.id in ids, "il match validated va riprocessato dal backfill"
    assert completed.id in ids, "il match completed resta incluso (regressione)"


@pytest.mark.unit
def test_matches_to_process_excludes_unfinished(db_session):
    """I match non conclusi (playing/pending) restano esclusi."""
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "unf_p1"), _user(suffix, "unf_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara_id = _gara_id(suffix)

    playing = _match(gara_id, p1.id, p2.id, MatchStatus.PLAYING.value)

    ids = {m.id for m in matches_to_process()}
    assert playing.id not in ids


@pytest.mark.unit
def test_validated_match_produces_elo(db_session):
    """End-to-end: processare un match `validated` popola l'ELO dei giocatori.

    È il cuore del bug: prima del fix questi giocatori restavano a NULL.
    """
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "elo_v1"), _user(suffix, "elo_v2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara_id = _gara_id(suffix)
    match = _match(gara_id, p1.id, p2.id, MatchStatus.VALIDATED.value)

    for m in matches_to_process():
        if m.id == match.id:
            RatingCalculationService.process_match_result(m)
    db.session.flush()

    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).rating_value > 1200
    assert PlayerRating.get_user_rating(p2.id, RatingSystem.ELO).rating_value < 1200
