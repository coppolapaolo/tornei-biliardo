"""Regression: direct elimination deve considerare i match 'validated' finiti.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/matchmaking/strategies/direct_elimination.py:151`:

`_generate_subsequent_round_pairings` filtrava i vincitori del turno
precedente con `status="completed"`, mentre `total_previous_matches` contava
TUTTI i match del turno senza filtro stato. Se anche un solo match precedente
era 'validated' (conferma bilaterale → stato finale legittimo), veniva escluso
dal numeratore ma contato nel denominatore: `len(previous_matches) !=
total_previous_matches` → ritorno `[]` → il turno successivo non veniva mai
generato e il torneo si bloccava.

Il fix usa `MatchStatus.finished_values()` (completed + validated).
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara
from models.match.models import Match
from models.matchmaking.strategies.direct_elimination import (
    DirectEliminationStrategy,
)
from models.status_enum import GaraStatus, MatchStatus


def _make_de_gara(db_session) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"DE gara {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="direct_elimination",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=3,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _finished_match(
    db_session, gara: Gara, p1, p2, winner, round_number: int, status: str
) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=p1.id,
        player2_id=p2.id,
        round_number=round_number,
        is_bye=False,
        status=status,
        winner_id=winner.id,
        player1_score=5 if winner is p1 else 3,
        player2_score=5 if winner is p2 else 3,
        match_distance=5,
    )
    db_session.add(match)
    db_session.flush()
    return match


@pytest.mark.unit
def test_round2_generated_when_round1_validated(db_session, isolated_players):
    """Tutti i match del round 1 in 'validated': il round 2 viene generato."""
    gara = _make_de_gara(db_session)
    p = isolated_players[:4]

    _finished_match(db_session, gara, p[0], p[3], p[0], 1, MatchStatus.VALIDATED.value)
    _finished_match(db_session, gara, p[1], p[2], p[1], 1, MatchStatus.VALIDATED.value)

    strategy = DirectEliminationStrategy()
    pairings = strategy._generate_round_pairings(gara, 2)

    pairs = {frozenset(pr.players) for pr in pairings if len(pr.players) == 2}
    # Prima del fix: pairings == [] (torneo bloccato).
    assert frozenset((p[0].id, p[1].id)) in pairs, "i due vincitori si affrontano"
    assert len(pairs) == 1


@pytest.mark.unit
def test_round2_generated_when_round1_mixed_completed_and_validated(
    db_session, isolated_players
):
    """Mix di 'completed' e 'validated' nel round 1: il round 2 viene generato."""
    gara = _make_de_gara(db_session)
    p = isolated_players[:4]

    _finished_match(db_session, gara, p[0], p[3], p[0], 1, MatchStatus.COMPLETED.value)
    _finished_match(db_session, gara, p[1], p[2], p[1], 1, MatchStatus.VALIDATED.value)

    strategy = DirectEliminationStrategy()
    pairings = strategy._generate_round_pairings(gara, 2)

    pairs = {frozenset(pr.players) for pr in pairings if len(pr.players) == 2}
    assert frozenset((p[0].id, p[1].id)) in pairs
    assert len(pairs) == 1


@pytest.mark.unit
def test_round2_blocked_when_round1_not_all_finished(db_session, isolated_players):
    """Se un match del round 1 è ancora 'playing', il round 2 NON viene generato."""
    gara = _make_de_gara(db_session)
    p = isolated_players[:4]

    _finished_match(db_session, gara, p[0], p[3], p[0], 1, MatchStatus.VALIDATED.value)
    # Secondo match ancora in corso (nessun vincitore certificato).
    pending = Match(
        gara_id=gara.id,
        player1_id=p[1].id,
        player2_id=p[2].id,
        round_number=1,
        is_bye=False,
        status=MatchStatus.PLAYING.value,
        match_distance=5,
    )
    db_session.add(pending)
    db_session.flush()

    strategy = DirectEliminationStrategy()
    pairings = strategy._generate_round_pairings(gara, 2)

    assert pairings == [], "round 2 non deve partire finché il round 1 non è finito"
