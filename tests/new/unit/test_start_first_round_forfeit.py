"""Regression tests for forfeit routing in RoundService.start_first_round.

Spec: `_bmad-output/implementation-artifacts/spec-fix-forfeit-first-round.md`

Bug (deferred-work.md, 2026-04-19 ECH #2): `start_first_round` invoked
`create_matches_from_pairings` WITHOUT `forfeit_user_ids` in both the
`random`-strategy branch (multi-round loop) and the single-round branch
for other strategies. Pre-existing players marked `is_forfeit=True` were
paired normally instead of producing walkovers (2-player) or being
converted to 2-player matches / trio walkovers (trio branches).

These tests assert the fix routes forfeit players correctly from
`RoundService.start_first_round` — covering the path `_create_round_impl`
already handles for subsequent rounds. We pick strategy+players combos
that satisfy per-strategy `min_players` validation: amalfi/round_robin
need >=3, random_anti_rematch accepts >=2.
"""

from __future__ import annotations

from datetime import date
from typing import List

import pytest

from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.match.models import Match, TrioMatch


def _make_gara(
    db_session,
    *,
    strategy: str = "amalfi",
    rounds_count: int = 1,
    min_participants: int = 2,
    odd_number_policy: str = "bye",
) -> Gara:
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Start-first-round forfeit gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy=strategy,
        status="inscription",
        is_race_to=True,
        rounds_count=rounds_count,
        min_participants=min_participants,
        odd_number_policy=odd_number_policy,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscribe(
    db_session, gara_id: int, user_id: int, *, is_forfeit: bool = False
) -> Inscription:
    ins = Inscription(gara_id=gara_id, user_id=user_id, is_forfeit=is_forfeit)
    db_session.add(ins)
    db_session.flush()
    return ins


def _round_matches(db_session, gara_id: int, round_number: int) -> List[Match]:
    return (
        db_session.query(Match)
        .filter_by(gara_id=gara_id, round_number=round_number)
        .all()
    )


@pytest.mark.unit
class TestStartFirstRoundForfeit:
    """Coverage for both branches of start_first_round (amalfi + random)."""

    def test_amalfi_non_random_branch_forfeit_creates_walkover(
        self, db_session, isolated_players
    ):
        """Non-random branch: 4 players con 1 forfeit; amalfi genera 2 match, quello col forfeiter è walkover.

        We assert the end-state invariant: any match whose player set contains
        the forfeiter must be walkover-completed with the non-forfeit player
        as winner. This is stable under amalfi's arbitrary pairing choices.
        """
        gara = _make_gara(db_session, min_participants=4)
        p0, p1, p2, p3 = (p.id for p in isolated_players[:4])
        forfeiter = p0
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)
        _inscribe(db_session, gara.id, p2)
        _inscribe(db_session, gara.id, p3)
        db_session.commit()

        RoundService.start_first_round(gara.id)

        matches = _round_matches(db_session, gara.id, 1)
        assert len(matches) == 2
        forfeit_match = next(
            m for m in matches if forfeiter in (m.player1_id, m.player2_id)
        )
        assert (
            forfeit_match.status == "completed"
        ), "Forfeiter's match was left as pending — forfeit_user_ids not routed"
        assert forfeit_match.is_walkover is True
        assert forfeit_match.winner_id != forfeiter
        # Non-forfeit match is unchanged: pending
        non_forfeit_match = next(m for m in matches if m.id != forfeit_match.id)
        assert non_forfeit_match.status == "pending"

    def test_trio_one_forfeit_converts_to_two_player_pending(
        self, db_session, isolated_players
    ):
        """Non-random branch: 3 iscritti, odd_policy=trio, 1 forfeit → 1 match 2p pending tra survivors, no TrioMatch row."""
        gara = _make_gara(db_session, min_participants=3, odd_number_policy="trio")
        p0, p1, p2 = (p.id for p in isolated_players[:3])
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)
        _inscribe(db_session, gara.id, p2)
        db_session.commit()

        RoundService.start_first_round(gara.id)

        matches = _round_matches(db_session, gara.id, 1)
        assert len(matches) == 1, "Expected a single 2-player match, not trio"
        m = matches[0]
        assert m.is_trio is False
        assert m.status == "pending"
        assert {m.player1_id, m.player2_id} == {p1, p2}
        assert db_session.query(TrioMatch).filter_by(match_id=m.id).count() == 0

    def test_trio_two_forfeit_creates_walkover(self, db_session, isolated_players):
        """Non-random branch: 3 iscritti, odd_policy=trio, 2 forfeit → trio walkover completato, winner = survivor."""
        gara = _make_gara(db_session, min_participants=3, odd_number_policy="trio")
        p0, p1, p2 = (p.id for p in isolated_players[:3])
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1, is_forfeit=True)
        _inscribe(db_session, gara.id, p2)
        db_session.commit()

        RoundService.start_first_round(gara.id)

        matches = _round_matches(db_session, gara.id, 1)
        assert len(matches) == 1
        m = matches[0]
        assert m.is_trio is True
        assert m.status == "completed"
        assert m.winner_id == p2
        assert m.is_walkover is True
        trio = db_session.query(TrioMatch).filter_by(match_id=m.id).one()
        assert trio.winner_id == p2
        assert trio.is_completed is True

    def test_random_strategy_forfeit_propagates_to_all_rounds(
        self, db_session, isolated_players
    ):
        """Random branch: forfeiter deve essere walkover IN OGNI round generato."""
        gara = _make_gara(
            db_session, strategy="random", rounds_count=3, min_participants=2
        )
        p0, p1 = isolated_players[0].id, isolated_players[1].id
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)
        db_session.commit()

        RoundService.start_first_round(gara.id)

        for round_number in range(1, 4):
            matches = _round_matches(db_session, gara.id, round_number)
            assert len(matches) >= 1, f"Round {round_number} has no matches"
            for m in matches:
                if m.player2_id is not None and not m.is_bye:
                    assert (
                        m.status == "completed"
                    ), f"Round {round_number}: forfeit match left as pending"
                    assert m.winner_id == p1
                    assert m.is_walkover is True

    def test_no_forfeit_creates_pending_matches_unchanged(
        self, db_session, isolated_players
    ):
        """Happy path invariance: nessun forfeit → comportamento invariato (match pending)."""
        gara = _make_gara(db_session, min_participants=4)
        p0, p1, p2, p3 = (p.id for p in isolated_players[:4])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        _inscribe(db_session, gara.id, p2)
        _inscribe(db_session, gara.id, p3)
        db_session.commit()

        RoundService.start_first_round(gara.id)

        matches = _round_matches(db_session, gara.id, 1)
        assert len(matches) == 2
        for m in matches:
            assert m.status == "pending"
            assert m.is_walkover is False
            assert m.winner_id is None
