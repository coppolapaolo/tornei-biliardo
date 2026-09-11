"""Regressione performance per il fix #62.

`Gara.display_round` scorre `gara.matches` (relationship lazy): letta sulle
tessere delle gare in corso senza eager-load produrrebbe una query per gara,
la N+1 che la home aveva già chiuso una volta. Dal 2026-09-10 le tessere
sono le stesse per home e dashboard, e i match li precarica
`enrich_with_progress` (`models/dashboard/gara_cards.py`) in una query sola.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import event

from models.base import db
from models.competition.models import Gara
from models.dashboard.gara_cards import GaraCardVM, enrich_with_progress
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


class _QueryCounter:
    def __init__(self):
        self.count = 0

    def __enter__(self):
        event.listen(db.engine, "before_cursor_execute", self._cb)
        return self

    def __exit__(self, *a):
        event.remove(db.engine, "before_cursor_execute", self._cb)

    def _cb(self, conn, cursor, statement, params, context, executemany):
        head = statement.lstrip().upper()
        if head.startswith("SELECT") or head.startswith("WITH"):
            self.count += 1


def _make_players(suffix, count=2):
    players = []
    for i in range(count):
        user = User(
            username=f"p{i}_{suffix}", email=f"p{i}_{suffix}@test.com", role="player"
        )
        user.set_password("x")
        db.session.add(user)
        players.append(user)
    db.session.flush()
    return players


def _make_live_garas(suffix, n_gare, players):
    """`n_gare` gare PLAYING con i turni pre-generati (turno 1 chiuso,
    turno 2 aperto), lo scenario dell'issue #62."""
    garas = []
    for gi in range(n_gare):
        gara = Gara(
            number=gi + 1,
            name=f"G{gi}_{suffix}",
            date=date.today() + timedelta(days=gi),
            time=time(18, 0),
            discipline="8_ball",
            distance=5,
            rounds_count=2,
            current_round=1,
            min_participants=2,
            matchmaking_strategy="random",
            status=GaraStatus.PLAYING.value,
        )
        db.session.add(gara)
        db.session.flush()
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=players[0].id,
                player2_id=players[1].id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=players[0].id,
                player2_id=players[1].id,
                status=MatchStatus.PLAYING.value,
            )
        )
        garas.append(gara)
    db.session.flush()
    return garas


def _cards(gare):
    return [GaraCardVM(gara=g, name=g.name or "") for g in gare]


@pytest.mark.unit
def test_enrich_with_progress_makes_display_round_query_free(db_session):
    """Dopo `enrich_with_progress`, leggere display_round non emette query."""
    suffix = uuid.uuid4().hex[:8]
    players = _make_players(suffix)
    garas = _make_live_garas(suffix, n_gare=4, players=players)
    db.session.commit()
    db.session.expire_all()

    # Ricarica le gare senza i match (identity map svuotata dagli expire).
    fresh = Gara.query.filter(Gara.id.in_([g.id for g in garas])).all()

    enrich_with_progress(_cards(fresh), None)
    with _QueryCounter() as qc:
        rounds = [g.display_round for g in fresh]

    assert rounds == [2, 2, 2, 2]
    assert qc.count == 0, f"display_round ha emesso {qc.count} query dopo il preload"


@pytest.mark.unit
def test_display_round_is_not_n_plus_one(db_session):
    """Il costo in query non cresce con il numero di gare in corso."""
    suffix = uuid.uuid4().hex[:8]
    players = _make_players(suffix)

    small = _make_live_garas(suffix + "a", n_gare=2, players=players)
    db.session.commit()
    db.session.expire_all()
    fresh_small = Gara.query.filter(Gara.id.in_([g.id for g in small])).all()
    with _QueryCounter() as qc_small:
        enrich_with_progress(_cards(fresh_small), None)
        [g.display_round for g in fresh_small]

    big = _make_live_garas(suffix + "b", n_gare=6, players=players)
    db.session.commit()
    db.session.expire_all()
    fresh_big = Gara.query.filter(Gara.id.in_([g.id for g in big])).all()
    with _QueryCounter() as qc_big:
        enrich_with_progress(_cards(fresh_big), None)
        [g.display_round for g in fresh_big]

    assert (
        qc_big.count == qc_small.count
    ), f"N+1: {qc_small.count} query con 2 gare in corso vs {qc_big.count} con 6"
