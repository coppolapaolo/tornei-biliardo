"""
Test TDD for TableAssignmentService.reassign_table() functionality.

Tests cover:
1. Simple table assignment to match without table
2. Table reassignment (changing table)
3. Table removal (set to None)
4. Automatic swap when new table is occupied
5. Round locking validation
6. Cross-round table sharing (same table, different rounds)
"""

import pytest
from datetime import datetime
from models import db
from models.match.table_assignment_service import TableAssignmentService
from models.match.models import Match
from models.competition.models import Gara, WithdrawPolicy
from models.user.models import User
from models.location.models import BilliardHall
from models.status_enum import GaraStatus, MatchStatus, Discipline


class TestTableAssignmentReassign:
    """Test suite for table reassignment functionality."""

    @pytest.fixture
    def venue(self, db_session):
        """Create a billiard hall with 3 tables."""
        hall = BilliardHall(
            name="Test Hall",
            number_of_tables=3,
            table_names='["1", "2", "3"]',
        )
        db_session.add(hall)
        db_session.commit()
        return hall

    @pytest.fixture
    def gara(self, db_session, venue):
        """Create a gara at the test venue."""
        gara = Gara(
            number=1,
            date=datetime(2025, 10, 15, 19, 0),
            location=venue.name,
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            best_of=True,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    @pytest.fixture
    def players(self, db_session):
        """Create 4 test players."""
        players = []
        for i in range(1, 5):
            player = User(
                username=f"player{i}",
                email=f"player{i}@test.com",
                password_hash="hashed_password",
            )
            db_session.add(player)
            players.append(player)
        db_session.commit()
        return players

    def test_assign_table_to_match_without_table(self, db_session, gara, players):
        """Test assigning a table to a match that has no table."""
        # Create match without table
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment=None,
        )
        db_session.add(match)
        db_session.commit()

        # Assign table "1"
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match.id, "1"
        )

        assert success is True
        assert "Tavolo assegnato" in message
        assert swapped_id is None

        # Verify table assignment
        match = db_session.get(Match, match.id)
        assert match.table_assignment == "1"

    def test_reassign_table_to_different_table(self, db_session, gara, players):
        """Test changing table assignment from one table to another."""
        # Create match with table "1"
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
        )
        db_session.add(match)
        db_session.commit()

        # Reassign to table "2"
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match.id, "2"
        )

        assert success is True
        assert "Tavolo assegnato" in message
        assert swapped_id is None

        # Verify table changed
        match = db_session.get(Match, match.id)
        assert match.table_assignment == "2"

    def test_remove_table_assignment(self, db_session, gara, players):
        """Test removing table assignment (set to None)."""
        # Create match with table "1"
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
        )
        db_session.add(match)
        db_session.commit()

        # Remove table assignment
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match.id, None
        )

        assert success is True
        assert "rimosso" in message
        assert swapped_id is None

        # Verify table removed
        match = db_session.get(Match, match.id)
        assert match.table_assignment is None

    def test_no_change_when_assigning_same_table(self, db_session, gara, players):
        """Test that assigning the same table returns success with no change."""
        # Create match with table "1"
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
        )
        db_session.add(match)
        db_session.commit()

        # "Reassign" to same table "1"
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match.id, "1"
        )

        assert success is True
        assert "Nessuna modifica" in message
        assert swapped_id is None

    def test_automatic_swap_when_table_occupied_same_round(
        self, db_session, gara, players
    ):
        """Test automatic swap when new table is occupied by another match in same round."""
        # Match 1: has table "1"
        match1 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
        )
        # Match 2: has table "2"
        match2 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            table_assignment="2",
        )
        db_session.add_all([match1, match2])
        db_session.commit()

        # Reassign match1 to table "2" (occupied by match2)
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match1.id, "2"
        )

        assert success is True
        assert "scambiato" in message
        assert swapped_id == match2.id

        # Verify swap occurred
        match1 = db_session.get(Match, match1.id)
        match2 = db_session.get(Match, match2.id)
        assert match1.table_assignment == "2"
        assert match2.table_assignment == "1"

    def test_automatic_swap_with_match_without_table(
        self, db_session, gara, players
    ):
        """Test swap when match without table is assigned to occupied table."""
        # Match 1: no table
        match1 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment=None,
        )
        # Match 2: has table "1"
        match2 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            table_assignment="1",
        )
        db_session.add_all([match1, match2])
        db_session.commit()

        # Assign match1 to table "1" (occupied by match2)
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match1.id, "1"
        )

        assert success is True
        assert "assegnato" in message
        assert swapped_id == match2.id

        # Verify: match1 gets table "1", match2 loses table
        match1 = db_session.get(Match, match1.id)
        match2 = db_session.get(Match, match2.id)
        assert match1.table_assignment == "1"
        assert match2.table_assignment is None

    def test_cross_round_table_sharing_allowed(self, db_session, gara, players):
        """Test that same table can be assigned to matches in different rounds."""
        # Match in round 1: has table "1"
        match_r1 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
        )
        # Match in round 2: no table yet
        match_r2 = Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=players[2].id,
            player2_id=players[3].id,
            table_assignment=None,
        )
        db_session.add_all([match_r1, match_r2])
        db_session.commit()

        # Assign match_r2 to table "1" (same as match_r1, but different round)
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match_r2.id, "1"
        )

        assert success is True
        assert "Tavolo assegnato" in message
        assert swapped_id is None  # No swap because different rounds

        # Verify both matches have table "1"
        match_r1 = db_session.get(Match, match_r1.id)
        match_r2 = db_session.get(Match, match_r2.id)
        assert match_r1.table_assignment == "1"
        assert match_r2.table_assignment == "1"

    def test_round_locking_prevents_reassignment(self, db_session, gara, players):
        """Test that round locking prevents table reassignment."""
        # Match in round 1
        match_r1 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            table_assignment="1",
            status=MatchStatus.COMPLETED.value,
        )
        # Match in round 2 (creates subsequent round, locking round 1)
        match_r2 = Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=players[2].id,
            player2_id=players[3].id,
            table_assignment=None,
        )
        db_session.add_all([match_r1, match_r2])
        db_session.commit()

        # Try to reassign match_r1 table (should fail due to locking)
        success, message, swapped_id = TableAssignmentService.reassign_table(
            match_r1.id, "2"
        )

        assert success is False
        assert "bloccato" in message.lower()
        assert swapped_id is None

        # Verify table unchanged
        match_r1 = db_session.get(Match, match_r1.id)
        assert match_r1.table_assignment == "1"

    def test_match_not_found_returns_error(self, db_session):
        """Test that reassigning non-existent match returns error."""
        success, message, swapped_id = TableAssignmentService.reassign_table(
            99999, "1"
        )

        assert success is False
        assert "non trovato" in message
        assert swapped_id is None
