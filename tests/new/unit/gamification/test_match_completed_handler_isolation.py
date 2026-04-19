"""Isolation tests for GamificationEventHandlers.handle_match_completed_for_xp.

Source: deferred-work.md (2026-04-19 walkover-unified review residuals).

A2 — Each AchievementService.check_and_award_achievement call must be
isolated so that a failure in one does not skip the remaining ones (nor
the streak/quest side effects that follow).

A1 — Failures in the walkover detection path (match lookup, forfeit set)
must propagate to EventBus rather than be silently caught — otherwise
`forfeit_ids` stays empty and XP is awarded to forfeiters.
"""

from __future__ import annotations

from datetime import date
from typing import List
from unittest.mock import patch

import pytest

from models.competition.models import Gara, Inscription
from models.events.match_events import MatchCompletedEvent
from models.gamification.event_handlers import GamificationEventHandlers
from models.match.models import Match


def _make_gara(db_session) -> Gara:
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Gamif-isolation gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="amalfi",
        status="playing",
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _make_completed_match(db_session, gara, winner_id, loser_id) -> Match:
    db_session.add(Inscription(gara_id=gara.id, user_id=winner_id))
    db_session.add(Inscription(gara_id=gara.id, user_id=loser_id))
    m = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=winner_id,
        player2_id=loser_id,
        match_distance=5,
        status="completed",
        winner_id=winner_id,
        player1_score=5,
        player2_score=3,
    )
    db_session.add(m)
    db_session.flush()
    from models.match.models import Rack

    for i in range(1, 6):
        db_session.add(Rack(match_id=m.id, rack_number=i, winner_id=winner_id))
    for i in range(6, 9):
        db_session.add(Rack(match_id=m.id, rack_number=i, winner_id=loser_id))
    db_session.commit()
    return m


@pytest.mark.unit
class TestAchievementIsolation:
    """A2 — One achievement raising must not cancel the other three."""

    def test_first_blood_failure_does_not_block_other_achievements(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        winner_id = isolated_players[0].id
        loser_id = isolated_players[1].id
        m = _make_completed_match(db_session, gara, winner_id, loser_id)
        event = MatchCompletedEvent(
            match_id=m.id,
            winner_id=winner_id,
            player1_id=winner_id,
            player2_id=loser_id,
            player1_name="W",
            player2_name="L",
            gara_id=gara.id,
        )

        calls: List[str] = []

        def fake_check(user_id, code, **kwargs):
            calls.append(code)
            if code == "first_blood":
                raise RuntimeError("boom")

        with patch(
            "models.gamification.event_handlers.AchievementService.check_and_award_achievement",
            side_effect=fake_check,
        ):
            GamificationEventHandlers.handle_match_completed_for_xp(event)

        assert "first_blood" in calls, "first_blood was not attempted"
        for expected in ("veteran_player", "century_club", "match_marathon"):
            assert expected in calls, (
                f"{expected} skipped after first_blood failed — achievements "
                f"are not isolated"
            )


@pytest.mark.unit
class TestWalkoverDetectionErrorsPropagate:
    """A1 — Walkover detection failures must raise (caught by EventBus)."""

    def test_walkover_detection_failure_propagates(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        winner_id = isolated_players[0].id
        loser_id = isolated_players[1].id
        m = _make_completed_match(db_session, gara, winner_id, loser_id)
        event = MatchCompletedEvent(
            match_id=m.id,
            winner_id=winner_id,
            player1_id=winner_id,
            player2_id=loser_id,
            player1_name="W",
            player2_name="L",
            gara_id=gara.id,
        )

        class Boom(Exception):
            pass

        with patch(
            "models.competition.withdraw_policy_service.WithdrawPolicyService.get_forfeit_user_ids",
            side_effect=Boom("db error"),
        ):
            # is_walkover is False on this match (has racks), so the forfeit
            # lookup is NOT called. Force is_walkover=True by patching the
            # property so the walkover detection branch runs.
            with patch(
                "models.match.models.Match.is_walkover",
                new_callable=lambda: property(lambda self: True),
            ):
                with pytest.raises(Boom):
                    GamificationEventHandlers.handle_match_completed_for_xp(event)
