"""Regression tests for reset blocked by active tiebreaker.

Source: ADR-026 residual (2026-04-19). Spec:
`_bmad-output/implementation-artifacts/spec-reset-blocked-by-tiebreaker.md`.

Lo SSR certifica implicitamente l'integrità dei risultati. Un tiebreaker
in stato non-CANCELLED sulla gara blocca il reset di QUALSIASI match
della gara — il director deve prima cancellare lo spareggio.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.tiebreaker.models import Tiebreaker, TiebreakerStatus, TiebreakerType


def _make_playing_gara(db_session) -> Gara:
    """Gara Random (round lock sempre UNLOCKED) in stato PLAYING."""
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Reset-tiebreaker gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="random",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _make_completed_match(db_session, gara, player1, player2) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1,
        status=MatchStatus.COMPLETED.value,
        player1_score=5,
        player2_score=3,
        winner_id=player1.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=player2.id))
    db_session.flush()
    return match


def _make_tiebreaker(
    db_session, gara, player1, player2, status_value: str
) -> Tiebreaker:
    tb = Tiebreaker(
        match_id=_any_match_id(db_session, gara),
        gara_id=gara.id,
        tiebreaker_type=TiebreakerType.SPOT_SHOT.value,
        status=status_value,
        player1_id=player1.id,
        player2_id=player2.id,
    )
    db_session.add(tb)
    db_session.flush()
    return tb


def _any_match_id(db_session, gara) -> int:
    match = db_session.query(Match).filter(Match.gara_id == gara.id).first()
    assert match is not None, "Test setup: gara must have at least one match"
    return match.id


@pytest.mark.unit
class TestResetBlockedByActiveTiebreaker:
    def test_can_modify_blocked_by_pending_tiebreaker(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.PENDING.value)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()

    def test_can_modify_blocked_by_in_progress_tiebreaker(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.IN_PROGRESS.value)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()

    def test_can_modify_blocked_by_completed_tiebreaker(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.COMPLETED.value)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()

    def test_can_modify_allowed_with_only_cancelled_tiebreakers(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.CANCELLED.value)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is True
        assert reason == ""

    def test_can_modify_allowed_without_tiebreakers(self, db_session, isolated_players):
        """No regression: gare standard without tiebreaker still modifiable."""
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is True
        assert reason == ""

    def test_can_modify_allowed_for_standalone_match(
        self, db_session, isolated_players
    ):
        """Match senza gara_id (individual_match): skip tiebreaker check."""
        p1, p2 = isolated_players[:2]
        match = Match(
            gara_id=None,
            player1_id=p1.id,
            player2_id=p2.id,
            round_number=1,
            status=MatchStatus.COMPLETED.value,
            player1_score=5,
            player2_score=3,
            winner_id=p1.id,
        )
        db_session.add(match)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is True
        assert reason == ""

    def test_can_modify_blocked_by_mixed_tiebreakers(
        self, db_session, isolated_players
    ):
        """Gara con 1 CANCELLED + 1 COMPLETED: il COMPLETED blocca."""
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.CANCELLED.value)
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.COMPLETED.value)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()
