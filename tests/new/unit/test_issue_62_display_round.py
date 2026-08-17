"""Regressione issue #62 — "Turno corrente: 1 / 3" a gara al terzo turno.

Il riquadro pubblico leggeva `gara.current_round`, che avanza solo quando
*tutti* i match del turno sono conclusi. Le strategie che pre-generano i
turni (random, round robin) creano i match di tutti i turni all'avvio: la
gara gioca il turno 3 mentre `current_round` è ancora 1.
"""

import uuid
from datetime import date

import pytest

from models.base import db
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


def _make_gara(db_session, *, status=GaraStatus.PLAYING.value, current_round=1):
    gara = Gara(
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date(2026, 3, 1),
        discipline="nine_ball",
        status=status,
        rounds_count=3,
        current_round=current_round,
        distance=5,
        matchmaking_strategy="random",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _make_players(db_session, count=2):
    players = []
    for i in range(count):
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"p{i}_{uid}", email=f"p{i}_{uid}@example.com")
        user.set_password("pw")
        db_session.add(user)
        players.append(user)
    db_session.flush()
    return players


def _make_match(db_session, gara, round_number, players, status):
    match = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=players[0].id,
        player2_id=players[1].id,
        status=status,
    )
    db_session.add(match)
    db_session.flush()
    return match


@pytest.mark.unit
class TestGaraDisplayRound:

    def test_shows_round_in_play_with_pregenerated_rounds(self, db_session):
        """Turni 1-2 conclusi, turno 3 aperto, current_round fermo a 1."""
        gara = _make_gara(db_session, current_round=1)
        players = _make_players(db_session)
        _make_match(db_session, gara, 1, players, MatchStatus.CLOSED_UNILATERALLY.value)
        _make_match(db_session, gara, 2, players, MatchStatus.CONFIRMED_BY_BOTH.value)
        _make_match(db_session, gara, 3, players, MatchStatus.PLAYING.value)
        db_session.commit()

        assert db.session.get(Gara, gara.id).display_round == 3

    def test_lowest_open_round_wins(self, db_session):
        """Con turni pre-generati il turno mostrato è il più basso ancora
        aperto, non il più alto che ha match."""
        gara = _make_gara(db_session, current_round=1)
        players = _make_players(db_session)
        _make_match(db_session, gara, 1, players, MatchStatus.CLOSED_UNILATERALLY.value)
        _make_match(db_session, gara, 2, players, MatchStatus.PENDING.value)
        _make_match(db_session, gara, 3, players, MatchStatus.PENDING.value)
        db_session.commit()

        assert db.session.get(Gara, gara.id).display_round == 2

    def test_all_matches_finished_shows_last_round(self, db_session):
        gara = _make_gara(db_session, current_round=3)
        players = _make_players(db_session)
        for round_number in (1, 2, 3):
            _make_match(
                db_session,
                gara,
                round_number,
                players,
                MatchStatus.CLOSED_UNILATERALLY.value,
            )
        db_session.commit()

        assert db.session.get(Gara, gara.id).display_round == 3

    def test_playing_gara_without_matches_shows_one(self, db_session):
        """Edge case di avvio: gara PLAYING senza match ancora creati."""
        gara = _make_gara(db_session, current_round=0)
        db_session.commit()

        assert db.session.get(Gara, gara.id).display_round == 1

    def test_gara_in_inscription_shows_zero(self, db_session):
        gara = _make_gara(
            db_session, status=GaraStatus.INSCRIPTION.value, current_round=0
        )
        db_session.commit()

        assert db.session.get(Gara, gara.id).display_round == 0
