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


@pytest.mark.unit
class TestResetBlockedByCampionatoTiebreaker:
    """TB campionato-level (gara_id=NULL, campionato_id=X) bloccano i reset
    dei match delle gare del campionato — il playoff campionato certifica
    il ranking che dipende dagli score dei match sottostanti.
    """

    def _make_campionato(self, db_session):
        from models.campionato.models import Campionato

        existing = db_session.query(Campionato).count()
        c = Campionato(name=f"TB-Campionato {existing + 1}")
        db_session.add(c)
        db_session.flush()
        return c

    def test_campionato_tiebreaker_blocks_reset_of_match_in_gara(
        self, db_session, isolated_players
    ):
        """TB con gara_id=NULL + campionato_id=X blocca reset match in gara di X."""
        from models.tiebreaker.models import Tiebreaker

        campionato = self._make_campionato(db_session)
        gara = _make_playing_gara(db_session)
        gara.campionato_id = campionato.id
        db_session.flush()
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, gara, p1, p2)

        tb = Tiebreaker(
            match_id=match.id,
            gara_id=None,
            campionato_id=campionato.id,
            tiebreaker_type=TiebreakerType.PLAYOFF_MATCH.value,
            status=TiebreakerStatus.PENDING.value,
            player1_id=p1.id,
            player2_id=p2.id,
        )
        db_session.add(tb)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()

    def test_campionato_tiebreaker_does_not_block_unrelated_standalone_gara(
        self, db_session, isolated_players
    ):
        """TB campionato-level non blocca gare standalone (campionato_id=None)."""
        from models.tiebreaker.models import Tiebreaker

        campionato = self._make_campionato(db_session)
        # Standalone gara (no campionato link)
        standalone_gara = _make_playing_gara(db_session)
        assert standalone_gara.campionato_id is None
        p1, p2 = isolated_players[:2]
        match = _make_completed_match(db_session, standalone_gara, p1, p2)

        tb = Tiebreaker(
            match_id=match.id,
            gara_id=None,
            campionato_id=campionato.id,
            tiebreaker_type=TiebreakerType.PLAYOFF_MATCH.value,
            status=TiebreakerStatus.PENDING.value,
            player1_id=p1.id,
            player2_id=p2.id,
        )
        db_session.add(tb)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is True
        assert reason == ""


@pytest.mark.unit
class TestCancelRoundBlockedByTiebreaker:
    """cancel_round bloccato da tiebreaker attivo (coerenza con reset)."""

    def test_cancel_round_blocked_by_active_tiebreaker(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        # Round 1 with a match that has 0 score (no partial results)
        match = Match(
            gara_id=gara.id,
            player1_id=p1.id,
            player2_id=p2.id,
            round_number=1,
            status=MatchStatus.PENDING.value,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.add(Inscription(gara_id=gara.id, user_id=p1.id))
        db_session.add(Inscription(gara_id=gara.id, user_id=p2.id))
        db_session.flush()
        gara.current_round = 1
        _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.PENDING.value)
        db_session.commit()

        success, reason = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "spareggio" in reason.lower()

    def test_cancel_round_succeeds_after_tiebreaker_cancellation(
        self, db_session, isolated_players
    ):
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        match = Match(
            gara_id=gara.id,
            player1_id=p1.id,
            player2_id=p2.id,
            round_number=1,
            status=MatchStatus.PENDING.value,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.add(Inscription(gara_id=gara.id, user_id=p1.id))
        db_session.add(Inscription(gara_id=gara.id, user_id=p2.id))
        db_session.flush()
        gara.current_round = 1
        tb = _make_tiebreaker(db_session, gara, p1, p2, TiebreakerStatus.PENDING.value)
        db_session.commit()

        # Blocked first
        success, _ = AdvancedRoundManager.cancel_round(gara.id, 1)
        assert success is False

        # Cancel TB
        tb.status = TiebreakerStatus.CANCELLED.value
        db_session.commit()

        # Now succeeds
        success, msg = AdvancedRoundManager.cancel_round(gara.id, 1)
        assert success is True, f"cancel_round should succeed after TB cancel: {msg}"
