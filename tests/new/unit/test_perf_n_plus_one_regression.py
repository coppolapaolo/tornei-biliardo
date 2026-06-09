"""Regression performance (review 2026-06-09): N+1 eliminati.

- campionato/statistics_service.py:_aggregate_player_totals — sulla homepage
  anonima costruiva la classifica generale eseguendo 1 query
  RoundClassification (+ GaraClassification per Random) e un lazy-load user PER
  OGNI gara. Ora batcha in 2 query indipendenti dal numero di gare.
- dashboard/item_builders.py — ri-interrogava Gara per ogni campionato,
  vanificando joinedload(gare). Ora usa la relationship eager-loaded.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy import event

from models.base import db
from models.user.models import User
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.classification.models import RoundClassification
from models.campionato.statistics_service import TournamentStatisticsService
from models.status_enum import GaraStatus


class _QueryCounter:
    def __init__(self):
        self.count = 0

    def __enter__(self):
        event.listen(db.engine, "before_cursor_execute", self._cb)
        return self

    def __exit__(self, *a):
        event.remove(db.engine, "before_cursor_execute", self._cb)

    def _cb(self, conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


def _make_campionato(suffix, n_gare, n_players=3):
    camp = Campionato(name=f"Camp {suffix}", campionato_type="amalfi")
    db.session.add(camp)
    db.session.flush()
    players = []
    for i in range(n_players):
        u = User(
            username=f"p{i}_{suffix}", email=f"p{i}_{suffix}@test.com", role="player"
        )
        u.set_password("x")
        db.session.add(u)
        players.append(u)
    db.session.flush()
    for gi in range(n_gare):
        gara = Gara(
            number=gi + 1,
            name=f"G{gi}_{suffix}",
            date=date(2026, 1, 1 + gi),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=2,
            current_round=2,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="amalfi",
            status=GaraStatus.COMPLETED.value,
            campionato_id=camp.id,
        )
        db.session.add(gara)
        db.session.flush()
        for pos, u in enumerate(players, 1):
            db.session.add(
                RoundClassification(
                    gara_id=gara.id,
                    round_number=2,
                    user_id=u.id,
                    position=pos,
                    matches_won=n_players - pos,
                    rack_difference=(n_players - pos) * 2,
                )
            )
    db.session.flush()
    return camp, players


@pytest.mark.unit
def test_aggregate_player_totals_is_not_n_plus_one(db_session):
    suffix = uuid.uuid4().hex[:8]
    svc = TournamentStatisticsService()

    # 2 gare
    camp2, _ = _make_campionato(suffix + "a", n_gare=2)
    db.session.commit()
    with _QueryCounter() as qc2:
        svc.calculate_general_classification(camp2.id)

    # 5 gare
    camp5, _ = _make_campionato(suffix + "b", n_gare=5)
    db.session.commit()
    with _QueryCounter() as qc5:
        svc.calculate_general_classification(camp5.id)

    # Il conteggio query NON deve crescere con il numero di gare (no N+1).
    assert (
        qc5.count == qc2.count
    ), f"N+1: {qc2.count} query con 2 gare vs {qc5.count} con 5 gare"


@pytest.mark.unit
def test_general_classification_correctness(db_session):
    suffix = uuid.uuid4().hex[:8]
    svc = TournamentStatisticsService()
    camp, players = _make_campionato(suffix, n_gare=3, n_players=3)
    db.session.commit()

    result = svc.calculate_general_classification(camp.id)
    # 3 giocatori in classifica; il player in pos.1 di ogni gara è primo.
    assert len(result) == 3
    positions = [pos for pos, _ in result]
    assert positions == [1, 2, 3]
