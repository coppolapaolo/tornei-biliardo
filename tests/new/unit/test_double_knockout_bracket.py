"""Regression: double knockout non deve dipendere da Match.notes (inesistente).

Bug (code review 2026-06-09, HIGH correttezza) —
`models/matchmaking/strategies/double_knockout.py:245/347/372`:

La distinzione winners/losers bracket si basava su `Match.notes`
('losers_bracket'), ma il modello Match NON ha alcuna colonna `notes`
(esiste solo su Set). Conseguenze:
  (a) `.filter(Match.notes != ...)` solleva AttributeError appena si genera
      un round >= 2 → strategia non utilizzabile oltre il primo turno;
  (b) anche senza crash il tag non è mai persistito → bracket sempre vuoto.

Inoltre le query filtravano solo `status="completed"`, ignorando i match
"validated" (stesso problema del finding direct_elimination): con conferma
bilaterale i match del round 1 diventano validated e il round 2 non li vede.

Il fix deriva l'appartenenza al bracket dallo storico sconfitte (un match è
winners bracket se entrambi i giocatori vi sono entrati imbattuti) e usa
MatchStatus.finished_values() (completed + validated).
"""

from __future__ import annotations

from datetime import date
from typing import List

import pytest

from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy
from models.status_enum import GaraStatus, MatchStatus


def _make_dk_gara(db_session) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"DK gara {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="double_knockout",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=6,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscribe(db_session, gara: Gara, players: List) -> None:
    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.flush()


def _finished_match(
    db_session,
    gara: Gara,
    p1,
    p2,
    winner,
    round_number: int,
    status: str = MatchStatus.VALIDATED.value,
) -> Match:
    """Crea un match a 2 giocatori già finito (default: validated)."""
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
def test_round2_does_not_crash_and_splits_brackets(db_session, isolated_players):
    """Round 2 con round 1 VALIDATED: nessun AttributeError, mixed bracket.

    4 giocatori. Round 1 (winners bracket): p0>p3, p1>p2. Round 2 atteso:
    winners (p0 vs p1) + losers (p2 vs p3).
    """
    gara = _make_dk_gara(db_session)
    p = isolated_players[:4]
    _inscribe(db_session, gara, p)

    _finished_match(db_session, gara, p[0], p[3], p[0], 1)
    _finished_match(db_session, gara, p[1], p[2], p[1], 1)

    strategy = DoubleKnockoutStrategy()
    # Prima del fix: AttributeError 'Match' has no attribute 'notes'.
    pairings = strategy._generate_round_pairings(gara, 2)

    pairs = {frozenset(pr.players) for pr in pairings if len(pr.players) == 2}
    assert frozenset((p[0].id, p[1].id)) in pairs, "winners bracket: p0 vs p1"
    assert frozenset((p[2].id, p[3].id)) in pairs, "losers bracket: p2 vs p3"
    assert len(pairs) == 2


@pytest.mark.unit
def test_losers_bracket_survivor_recovered_in_round3(db_session, isolated_players):
    """Round 3: il survivor del losers bracket precedente è recuperato.

    Esercita la derivazione del bracket dallo storico (sostituisce il vecchio
    filtro Match.not=='losers_bracket' mai funzionante).

    Round 1: p0>p3, p1>p2. Round 2: p0>p1 (winners), p2>p3 (losers).
    Round 3 atteso (losers bracket): p1 (perdente winners r2) vs p2
    (survivor losers r2).
    """
    gara = _make_dk_gara(db_session)
    p = isolated_players[:4]
    _inscribe(db_session, gara, p)

    # Round 1 (winners bracket)
    _finished_match(db_session, gara, p[0], p[3], p[0], 1)
    _finished_match(db_session, gara, p[1], p[2], p[1], 1)
    # Round 2: p0 vs p1 (winners), p2 vs p3 (losers)
    _finished_match(db_session, gara, p[0], p[1], p[0], 2)
    _finished_match(db_session, gara, p[2], p[3], p[2], 2)

    strategy = DoubleKnockoutStrategy()
    pairings = strategy._generate_round_pairings(gara, 3)

    pairs = {frozenset(pr.players) for pr in pairings if len(pr.players) == 2}
    assert (
        frozenset((p[1].id, p[2].id)) in pairs
    ), "losers bracket round 3: p1 (perdente winners) vs p2 (survivor losers)"


@pytest.mark.unit
def test_completed_status_still_works(db_session, isolated_players):
    """Retro-compatibilità: round 1 con status 'completed' continua a funzionare."""
    gara = _make_dk_gara(db_session)
    p = isolated_players[:4]
    _inscribe(db_session, gara, p)

    _finished_match(
        db_session, gara, p[0], p[3], p[0], 1, status=MatchStatus.COMPLETED.value
    )
    _finished_match(
        db_session, gara, p[1], p[2], p[1], 1, status=MatchStatus.COMPLETED.value
    )

    strategy = DoubleKnockoutStrategy()
    pairings = strategy._generate_round_pairings(gara, 2)

    pairs = {frozenset(pr.players) for pr in pairings if len(pr.players) == 2}
    assert frozenset((p[0].id, p[1].id)) in pairs
    assert frozenset((p[2].id, p[3].id)) in pairs
