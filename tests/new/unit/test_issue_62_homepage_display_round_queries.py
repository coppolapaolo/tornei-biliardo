"""Regressione performance per il fix #62.

`Gara.display_round` scorre `gara.matches` (relationship lazy): usata sulle
card di homepage senza eager-load produrrebbe una query per gara live,
vanificando lo stesso N+1 che `_live_matches_by_gara` evita per i match ai
tavoli. `HomepageService._preload_matches` le carica in un colpo solo.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import event

from models.base import db
from models.campionato.homepage_service import HomepageService
from models.competition.models import Gara
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
                status=MatchStatus.COMPLETED.value,
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


@pytest.mark.unit
def test_preload_matches_makes_display_round_query_free(db_session):
    """Dopo `_preload_matches`, leggere display_round non emette query."""
    suffix = uuid.uuid4().hex[:8]
    players = _make_players(suffix)
    garas = _make_live_garas(suffix, n_gare=4, players=players)
    db.session.commit()
    db.session.expire_all()

    # Ricarica le gare senza i match (identity map svuotata dagli expire).
    fresh = Gara.query.filter(Gara.id.in_([g.id for g in garas])).all()

    HomepageService._preload_matches(fresh)
    with _QueryCounter() as qc:
        rounds = [HomepageService._display_round(g) for g in fresh]

    assert rounds == [2, 2, 2, 2]
    assert qc.count == 0, f"display_round ha emesso {qc.count} query dopo il preload"


@pytest.mark.unit
def test_homepage_display_round_is_not_n_plus_one(db_session):
    """Il costo in query non cresce con il numero di gare live."""
    suffix = uuid.uuid4().hex[:8]
    players = _make_players(suffix)

    small = _make_live_garas(suffix + "a", n_gare=2, players=players)
    db.session.commit()
    db.session.expire_all()
    fresh_small = Gara.query.filter(Gara.id.in_([g.id for g in small])).all()
    with _QueryCounter() as qc_small:
        HomepageService._preload_matches(fresh_small)
        [HomepageService._display_round(g) for g in fresh_small]

    big = _make_live_garas(suffix + "b", n_gare=6, players=players)
    db.session.commit()
    db.session.expire_all()
    fresh_big = Gara.query.filter(Gara.id.in_([g.id for g in big])).all()
    with _QueryCounter() as qc_big:
        HomepageService._preload_matches(fresh_big)
        [HomepageService._display_round(g) for g in fresh_big]

    assert qc_big.count == qc_small.count, (
        f"N+1: {qc_small.count} query con 2 gare live " f"vs {qc_big.count} con 6"
    )
