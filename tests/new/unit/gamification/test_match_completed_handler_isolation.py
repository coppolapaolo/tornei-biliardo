"""Isolation tests for GamificationEventHandlers.handle_match_completed_for_xp.

Source: deferred-work.md (2026-04-19 walkover-unified review residuals).

A2 — Each AchievementService.check_and_award_achievement call must be
isolated so that a failure in one does not skip the remaining ones (nor
the streak/quest side effects that follow).

A1 — Failures in the walkover detection path (match lookup, forfeit set)
must propagate to EventBus rather than be silently caught — otherwise
`forfeit_ids` stays empty and XP is awarded to forfeiters.

A4 — `MatchCompletedEvent.player_ids` must carry all participant ids so
that trio handlers can iterate the full roster (p3 included) for streak
and quest side effects.
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
        discipline="9_ball",
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
    """A2 — un errore nella riconciliazione achievement non deve bloccare gli
    effetti collaterali (streak/quest) né gli altri partecipanti.

    Con il modello metric-driven l'handler chiama
    `AchievementService.reconcile_achievements(player_id)` per ogni partecipante
    (isolato in try/except); la riconciliazione a sua volta isola ogni singolo
    achievement. Qui verifichiamo l'isolamento a livello di handler.
    """

    def test_reconcile_failure_does_not_block_streak_and_quest(
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
            player_ids=[winner_id, loser_id],
            gara_id=gara.id,
        )

        reconciled: List[int] = []
        streak_calls: List[int] = []
        quest_calls: List[int] = []

        def boom(user_id):
            reconciled.append(user_id)
            raise RuntimeError("boom")

        def registra_quest(user_id, activity_type, activity_count):
            quest_calls.append(user_id)

        with patch(
            "models.gamification.event_handlers.AchievementService."
            "reconcile_achievements",
            side_effect=boom,
        ), patch(
            "models.gamification.event_handlers.StreakService.record_activity",
            side_effect=lambda user_id, streak_type: streak_calls.append(user_id),
        ), patch(
            "models.gamification.event_handlers.QuestService."
            "record_activity_for_quests",
            side_effect=registra_quest,
        ):
            GamificationEventHandlers.handle_match_completed_for_xp(event)

        # Entrambi i partecipanti sono stati riconciliati (loop non interrotto
        # dal primo errore) e streak/quest sono comunque avvenuti.
        assert set(reconciled) >= {winner_id, loser_id}
        assert winner_id in streak_calls and loser_id in streak_calls
        assert winner_id in quest_calls


@pytest.mark.unit
class TestWalkoverDetectionErrorsPropagate:
    """A1 — Walkover detection failures must raise (caught by EventBus)."""

    def test_walkover_detection_failure_propagates(self, db_session, isolated_players):
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
            "models.competition.withdraw_policy_service.WithdrawPolicyService."
            "get_forfeit_user_ids",
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


@pytest.mark.unit
class TestTrioPlayerIds:
    """A4 — `player_ids` carries the full roster so trio p3 is reachable."""

    def test_streak_and_quest_include_trio_p3_when_event_has_player_ids(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = (isolated_players[i].id for i in range(3))
        m = _make_completed_match(db_session, gara, winner_id=p2, loser_id=p0)
        event = MatchCompletedEvent(
            match_id=m.id,
            winner_id=p2,
            player1_id=p0,
            player2_id=p1,
            player1_name="P0",
            player2_name="P1",
            player_ids=[p0, p1, p2],
            gara_id=gara.id,
        )

        streak_calls: List[int] = []
        quest_calls: List[int] = []

        def registra_quest(user_id, activity_type, activity_count):
            quest_calls.append(user_id)

        with patch(
            "models.gamification.event_handlers.StreakService.record_activity",
            side_effect=lambda user_id, streak_type: streak_calls.append(user_id),
        ), patch(
            "models.gamification.event_handlers.QuestService."
            "record_activity_for_quests",
            side_effect=registra_quest,
        ):
            GamificationEventHandlers.handle_match_completed_for_xp(event)

        assert p2 in streak_calls, "trio p3 missing from streak recording"
        assert p2 in quest_calls, "trio p3 missing from quest recording"

    def test_player_ids_absent_falls_back_to_pair(self, db_session, isolated_players):
        """Backward-compat: events without player_ids still cover the 2-player case."""
        gara = _make_gara(db_session)
        p0, p1 = (isolated_players[i].id for i in range(2))
        m = _make_completed_match(db_session, gara, winner_id=p0, loser_id=p1)
        event = MatchCompletedEvent(
            match_id=m.id,
            winner_id=p0,
            player1_id=p0,
            player2_id=p1,
            player1_name="P0",
            player2_name="P1",
            gara_id=gara.id,
        )

        streak_calls: List[int] = []

        with patch(
            "models.gamification.event_handlers.StreakService.record_activity",
            side_effect=lambda user_id, streak_type: streak_calls.append(user_id),
        ), patch(
            "models.gamification.event_handlers.QuestService.record_activity_for_quests"
        ):
            GamificationEventHandlers.handle_match_completed_for_xp(event)

        assert set(streak_calls) >= {p0, p1}
        assert all(uid in {p0, p1} for uid in streak_calls)
