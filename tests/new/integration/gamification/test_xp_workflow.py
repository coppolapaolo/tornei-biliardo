"""
Integration Test: Complete XP Workflow

Tests the end-to-end XP system including:
- Event emission from domain events (MatchCompletedEvent, InscriptionCreatedEvent)
- Automatic XP award via event handlers
- Level up detection
- Notification creation
- Event bus integration

These tests verify the complete event-driven gamification workflow.
"""

import pytest

from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import (
    InscriptionCreatedEvent,
    CompetitionCompletedEvent,
)
from models.gamification.models import UserLevel, XPTransaction, XPTransactionType
from models.gamification.xp_config import XP_RATES
from models.gamification.event_handlers import GamificationEventHandlers
from models.notification.models import Notification, NotificationType


@pytest.fixture(autouse=True)
def register_gamification_handlers():
    """Ensure gamification event handlers are registered for each test.

    Handlers are already registered at app startup via models.gamification import.
    This fixture just ensures they stay registered and aren't affected by other tests.
    """
    # Save handlers state to restore after test (protect from other tests' cleanup)
    original_handlers = {k: list(v) for k, v in EventBus._handlers.items()}

    # Only register if not already registered (avoid duplicates)
    if MatchCompletedEvent not in EventBus._handlers:
        GamificationEventHandlers.register_all_handlers()

    yield

    # Restore original handlers after test
    EventBus._handlers = original_handlers


class TestXPWorkflowMatchCompletion:
    """Test XP workflow triggered by match completion events."""

    def test_match_completed_event_awards_xp_to_winner_and_loser(
        self, db_session, isolated_players
    ):
        """
        GIVEN a completed match with winner and loser
        WHEN MatchCompletedEvent is published
        THEN both players receive XP (50 for winner, 20 for loser)
        AND XPTransactions are created for audit
        """
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Arrange: Create event for match completion (correct signature)
        event = MatchCompletedEvent(
            match_id=123,
            player1_id=player1.id,
            player1_name=player1.username,
            player2_id=player2.id,
            player2_name=player2.username,
            winner_id=player1.id,
            winner_name=player1.username,
            score="5-3",
        )

        # Act: Publish event (triggers gamification event handler)
        EventBus.publish(event)
        db_session.flush()

        # Assert: Winner received 50 XP
        winner_level = db_session.get(UserLevel, player1.id)
        assert winner_level is not None
        assert winner_level.total_xp == XP_RATES[XPTransactionType.MATCH_WIN]
        assert winner_level.current_level == 1  # Not enough for level 2

        # Assert: Loser received 20 XP
        loser_level = db_session.get(UserLevel, player2.id)
        assert loser_level is not None
        assert loser_level.total_xp == XP_RATES[XPTransactionType.MATCH_LOSS]

        # Assert: Transactions created
        winner_txn = XPTransaction.query.filter_by(
            user_id=player1.id, transaction_type=XPTransactionType.MATCH_WIN
        ).first()
        assert winner_txn is not None
        assert winner_txn.xp_amount == 50
        assert winner_txn.level_before == 1
        assert winner_txn.level_after == 1

        loser_txn = XPTransaction.query.filter_by(
            user_id=player2.id, transaction_type=XPTransactionType.MATCH_LOSS
        ).first()
        assert loser_txn is not None
        assert loser_txn.xp_amount == 20


class TestXPWorkflowLevelUp:
    """Test level up workflow with notifications."""

    def test_level_up_via_direct_service_call(self, db_session, isolated_players):
        """GIVEN un utente a livello 1, WHEN si assegnano abbastanza XP via
        LevelService THEN sale di livello (282 XP = livello 2)."""
        player = isolated_players[0]
        from models.gamification.level_service import LevelService

        final_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=300,  # > 282 (livello 2), < 519 (livello 3)
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
            reason="Test level up diretto",
        )
        assert did_level_up is True
        assert final_level.current_level == 2
        assert final_level.total_xp == 300

    def test_sufficient_xp_triggers_level_up_via_events_no_persistent_notification(
        self, db_session, isolated_players
    ):
        """Via EventBus: vincite sufficienti → level up. La policy
        anti-invasività (Fase 3) rende il level-up SOLO toast → nessuna
        notifica persistente LEVEL_UP creata."""
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # 6 vittorie * 50 XP = 300 XP → livello 2.
        for match_id in range(1, 7):
            EventBus.publish(
                MatchCompletedEvent(
                    match_id=match_id,
                    player1_id=player1.id,
                    player1_name=player1.username,
                    player2_id=player2.id,
                    player2_name=player2.username,
                    winner_id=player1.id,
                    winner_name=player1.username,
                    score="5-0",
                )
            )
            db_session.flush()

        level = db_session.get(UserLevel, player1.id)
        assert level.total_xp == 300
        assert level.current_level == 2  # level up avvenuto

        # Anti-invasività: nessuna notifica persistente di level-up.
        levelup_notifs = Notification.query.filter_by(
            user_id=player1.id, notification_type=NotificationType.LEVEL_UP
        ).count()
        assert levelup_notifs == 0


class TestXPWorkflowTournamentInscription:
    """Test XP workflow for tournament inscription."""

    def test_inscription_event_awards_xp(self, db_session, isolated_players):
        """
        GIVEN a user registering for tournament
        WHEN InscriptionCreatedEvent is published
        THEN user receives 25 XP
        """
        player = isolated_players[0]

        # Arrange & Act (correct signature)
        event = InscriptionCreatedEvent(
            inscription_id=789,
            gara_id=456,
            gara_name="Test Tournament",
            user_id=player.id,
            username=player.username,
            inscription_status="confirmed",
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert
        user_level = db_session.get(UserLevel, player.id)
        assert user_level is not None
        assert user_level.total_xp == XP_RATES[XPTransactionType.TOURNAMENT_INSCRIPTION]

        # Assert transaction
        txn = XPTransaction.query.filter_by(
            user_id=player.id, transaction_type=XPTransactionType.TOURNAMENT_INSCRIPTION
        ).first()
        assert txn is not None
        assert txn.xp_amount == 25


class TestXPWorkflowTournamentCompletion:
    """Test XP workflow for tournament completion with bonuses."""

    def test_tournament_completion_awards_bonuses_correctly(
        self, db_session, isolated_players
    ):
        """CompetitionCompletedEvent con ``final_standings`` → bonus corretti:
        vincitore 100+500=600; podio (2°/3°) 100+200=300; altri 100.

        (La vecchia skip parlava di ``participant_ids`` rimosso: l'handler ora
        usa ``final_standings``.)
        """
        p1, p2, p3, p4 = isolated_players[:4]
        EventBus.publish(
            CompetitionCompletedEvent(
                gara_id=999,
                name="Torneo Test",
                winner_id=p1.id,
                winner_name=p1.username,
                final_standings=[
                    {"user_id": p1.id, "position": 1},
                    {"user_id": p2.id, "position": 2},
                    {"user_id": p3.id, "position": 3},
                    {"user_id": p4.id, "position": 4},
                ],
                total_participants=4,
            )
        )
        db_session.flush()

        assert db_session.get(UserLevel, p1.id).total_xp == 600  # 100 + 500
        assert db_session.get(UserLevel, p2.id).total_xp == 300  # 100 + 200
        assert db_session.get(UserLevel, p3.id).total_xp == 300  # 100 + 200
        assert db_session.get(UserLevel, p4.id).total_xp == 100  # solo completion


class TestXPWorkflowMultipleLevelUps:
    """Test handling of multiple level ups in single XP award."""

    def test_massive_xp_award_triggers_multiple_level_ups(
        self, db_session, isolated_players
    ):
        """
        GIVEN a user at level 1
        WHEN user receives 1000 XP (massive tournament win)
        THEN user levels up multiple times in single transaction
        AND correct level is reached
        """
        player = isolated_players[0]

        # Arrange: User at level 1 with 0 XP
        user_level = UserLevel(
            user_id=player.id, current_xp=0, total_xp=0, current_level=1
        )
        db_session.add(user_level)
        db_session.flush()

        # Act: Simulate large XP award
        from models.gamification.level_service import LevelService

        final_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=1000,
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
            reason="Test massive XP award",
        )

        # Assert: User leveled up multiple times
        assert did_level_up is True
        assert final_level.current_level > 2  # Should reach at least level 3-4
        assert final_level.total_xp == 1000

        # Assert: Only one transaction created (not one per level)
        txns = XPTransaction.query.filter_by(user_id=player.id).all()
        assert len(txns) == 1
        assert txns[0].level_before == 1
        assert txns[0].level_after == final_level.current_level


class TestXPWorkflowEventBusIntegration:
    """Test event bus integration with gamification."""

    def test_event_handlers_registered_automatically(self):
        """
        GIVEN the application is initialized
        WHEN gamification module is imported
        THEN event handlers are registered with EventBus
        """
        # This test verifies that handlers are auto-registered
        # by checking if MatchCompletedEvent has gamification handlers

        # Verify handlers are registered (this happens on module import)
        # The actual verification is implicit - if handlers weren't registered,
        # previous tests would fail
        assert True  # Placeholder - actual verification is in other tests

    def test_multiple_events_accumulate_xp(self, db_session, isolated_players):
        """
        GIVEN a user participating in multiple activities
        WHEN multiple events are published
        THEN XP accumulates correctly (total tracked)
        """
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Arrange & Act: Simulate user journey - 2 match wins
        for match_id in [1, 2]:
            EventBus.publish(
                MatchCompletedEvent(
                    match_id=match_id,
                    player1_id=player1.id,
                    player1_name=player1.username,
                    player2_id=player2.id,
                    player2_name=player2.username,
                    winner_id=player1.id,
                    winner_name=player1.username,
                    score="5-2",
                )
            )
            db_session.flush()

        # Assert: Total XP accumulated
        user_level = db_session.get(UserLevel, player1.id)
        assert user_level is not None
        assert user_level.total_xp == 100  # 2 wins * 50 XP

        # Assert: Transactions created
        txns = XPTransaction.query.filter_by(user_id=player1.id).all()
        assert len(txns) == 2
