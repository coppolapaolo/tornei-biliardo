"""
TDD Test Suite for Table Assignment System

Requirements:
1. Assign tables in order to matches when round starts
2. If not enough tables, put remaining matches in waiting state
3. A match cannot start without a table assigned
4. When a match completes, free the table and assign to next waiting match
5. Table assignment should respect venue's available tables
"""

import pytest
from datetime import date

from models import Gara, Match, User, BilliardHall
from models.status_enum import GaraStatus, MatchStatus, Discipline
from models.match.table_assignment_service import TableAssignmentService


@pytest.mark.unit
class TestTableAssignmentTDD:
    """Test-Driven Development for Table Assignment System"""

    @pytest.fixture
    def venue_with_tables(self, db_session):
        """Create a billiard hall with limited tables"""
        venue = BilliardHall(
            name="Test Venue",
            number_of_tables=3,  # Limited to 3 tables
            is_active=True,
            verified=True,
        )
        # Set custom table names
        venue.set_table_names(["Tavolo A", "Tavolo B", "Tavolo C"])
        db_session.add(venue)
        db_session.commit()
        return venue

    @pytest.fixture
    def gara_with_venue(self, db_session, venue_with_tables):
        """Create a gara at a specific venue"""
        gara = Gara(
            number=1,
            name="Test Gara with Tables",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            location=venue_with_tables.name,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
            min_participants=6,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    @pytest.fixture
    def players(self, db_session):
        """Create test players"""
        players = []
        for i in range(6):
            user = User(
                username=f"player{i + 1}",
                email=f"player{i + 1}@test.com",
                password_hash="test",
            )
            db_session.add(user)
            players.append(user)
        db_session.commit()
        return players

    @pytest.fixture
    def matches_without_tables(self, db_session, gara_with_venue, players):
        """Create 5 matches without table assignment (more than available tables)"""
        matches = []
        for i in range(0, 5):  # 5 matches > 3 tables available
            match = Match(
                gara_id=gara_with_venue.id,
                round_number=1,
                player1_id=players[i].id if i < len(players) else None,
                player2_id=players[i + 1].id if i + 1 < len(players) else None,
                status=MatchStatus.PENDING.value,
                table_assignment=None,  # No table assigned yet
            )
            db_session.add(match)
            matches.append(match)
        db_session.commit()
        return matches

    def test_assign_tables_to_pending_matches_in_order(
        self, db_session, gara_with_venue, venue_with_tables, matches_without_tables
    ):
        """
        TEST 1: Tables should be assigned in order to pending matches

        Given: 5 pending matches and 3 available tables
        When: assign_tables_to_round is called
        Then: First 3 matches get tables 1, 2, 3
              Last 2 matches remain without table assignment
        """
        # Act
        TableAssignmentService.assign_tables_to_round(
            gara_with_venue.id, round_number=1
        )

        # Assert
        matches = (
            Match.query.filter_by(gara_id=gara_with_venue.id, round_number=1)
            .order_by(Match.id)
            .all()
        )

        # First 3 matches should have tables with custom names
        assert matches[0].table_assignment == "Tavolo A"
        assert matches[1].table_assignment == "Tavolo B"
        assert matches[2].table_assignment == "Tavolo C"

        # Last 2 matches should not have tables
        assert matches[3].table_assignment is None
        assert matches[4].table_assignment is None

    def test_match_status_playing_only_with_table(
        self, db_session, gara_with_venue, matches_without_tables
    ):
        """
        TEST 2: Match status should only change to PLAYING if table is assigned

        Given: A match without table assignment
        When: Attempting to start the match
        Then: Match should remain PENDING
              And error should be raised
        """
        match = matches_without_tables[0]

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot start match without table"):
            TableAssignmentService.start_match(match.id)

        # Match should still be pending
        db_session.refresh(match)
        assert match.status == MatchStatus.PENDING.value

    def test_free_table_when_match_completes(
        self, db_session, gara_with_venue, matches_without_tables
    ):
        """
        TEST 3: When a match completes, its table should be freed

        Given: A match with table assignment
        When: Match is completed
        Then: Table assignment should be marked as available
              And next waiting match should get the table
        """
        # Assign tables first
        TableAssignmentService.assign_tables_to_round(
            gara_with_venue.id, round_number=1
        )

        matches = (
            Match.query.filter_by(gara_id=gara_with_venue.id, round_number=1)
            .order_by(Match.id)
            .all()
        )

        # Complete first match
        first_match = matches[0]
        first_match.status = MatchStatus.COMPLETED.value
        first_match.winner_id = first_match.player1_id
        db_session.commit()

        # Act - Free the table and reassign to waiting match
        TableAssignmentService.free_table_and_reassign(first_match.id)

        # Assert
        db_session.refresh(first_match)
        waiting_match = matches[3]  # First match without table
        db_session.refresh(waiting_match)

        # Completed match keeps its table for record
        assert first_match.table_assignment == "Tavolo A"

        # Waiting match should now have the freed table
        assert waiting_match.table_assignment == "Tavolo A"

    def test_no_table_assignment_if_venue_not_found(self, db_session, players):
        """
        TEST 4: If venue is not found in database, skip table assignment

        Given: A gara with a location that doesn't exist in BilliardHall
        When: assign_tables_to_round is called
        Then: No tables should be assigned (fail gracefully)
        """
        # Create gara with non-existent venue
        gara = Gara(
            number=2,
            name="Gara without venue",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            location="Non-existent venue",
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            current_round=1,
        )
        db_session.add(gara)
        db_session.commit()  # Commit gara first to get ID

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            status=MatchStatus.PENDING.value,
        )
        db_session.add(match)
        db_session.commit()

        # Act
        TableAssignmentService.assign_tables_to_round(gara.id, round_number=1)

        # Assert - No table assigned
        db_session.refresh(match)
        assert match.table_assignment is None

    def test_reassign_only_to_same_round_matches(
        self, db_session, gara_with_venue, players
    ):
        """
        TEST 5: When freeing a table, only assign to matches from the same round

        Given: Completed match in round 1, pending match in round 2
        When: Table is freed
        Then: Table should not be assigned to round 2 match
        """
        # Round 1 match with table
        match_r1 = Match(
            gara_id=gara_with_venue.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            status=MatchStatus.COMPLETED.value,
            table_assignment="Tavolo A",
            winner_id=players[0].id,
        )
        db_session.add(match_r1)

        # Round 2 match without table
        match_r2 = Match(
            gara_id=gara_with_venue.id,
            round_number=2,
            player1_id=players[2].id,
            player2_id=players[3].id,
            status=MatchStatus.PENDING.value,
            table_assignment=None,
        )
        db_session.add(match_r2)
        db_session.commit()

        # Act
        TableAssignmentService.free_table_and_reassign(match_r1.id)

        # Assert - Round 2 match should not get the table
        db_session.refresh(match_r2)
        assert match_r2.table_assignment is None

    def test_get_available_tables_count(self, db_session, venue_with_tables):
        """
        TEST 6: Should correctly retrieve number of available tables from venue

        Given: A venue with 3 tables
        When: Getting available tables
        Then: Should return 3
        """
        count = TableAssignmentService.get_available_tables_count("Test Venue")
        assert count == 3

    def test_get_available_tables_count_none_if_venue_not_found(self, db_session):
        """
        TEST 7: Should return None if venue doesn't exist

        Given: A non-existent venue name
        When: Getting available tables
        Then: Should return None
        """
        count = TableAssignmentService.get_available_tables_count("Ghost Venue")
        assert count is None
