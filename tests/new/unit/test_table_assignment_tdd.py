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
        """Create test players - 10 players for 5 non-overlapping matches"""
        players = []
        for i in range(10):  # 10 players for 5 matches
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
        """Create 5 non-overlapping matches (more matches than available tables).

        Each player is in exactly ONE match to avoid player-busy conflicts:
        - Match 0: player[0] vs player[1]
        - Match 1: player[2] vs player[3]
        - Match 2: player[4] vs player[5]
        - Match 3: player[6] vs player[7]
        - Match 4: player[8] vs player[9]
        """
        matches = []
        for i in range(5):  # 5 matches > 3 tables available
            match = Match(
                gara_id=gara_with_venue.id,
                round_number=1,
                player1_id=players[i * 2].id,  # 0, 2, 4, 6, 8
                player2_id=players[i * 2 + 1].id,  # 1, 3, 5, 7, 9
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

    def test_release_table_when_match_completes(
        self, db_session, gara_with_venue, matches_without_tables
    ):
        """
        TEST 3: When a match completes, its table should be released and reassigned

        Given: A match with table assignment
        When: Match is completed and table is released
        Then: Completed match should have no table (released)
              And next PENDING match should get the table and become PLAYING
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
        first_match.status = MatchStatus.CLOSED_UNILATERALLY.value
        first_match.winner_id = first_match.player1_id
        db_session.commit()

        # Act - Release the table and reassign to waiting match
        TableAssignmentService.release_and_reassign_table(first_match.id)

        # Assert
        db_session.refresh(first_match)
        waiting_match = matches[3]  # First match without table (was PENDING)
        db_session.refresh(waiting_match)

        # Completed match should no longer have the table (released)
        assert first_match.table_assignment is None

        # Waiting match should now have the freed table and be PLAYING
        assert waiting_match.table_assignment == "Tavolo A"
        assert waiting_match.status == MatchStatus.PLAYING.value

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

    def test_reassign_to_any_pending_match_across_rounds(
        self, db_session, gara_with_venue, players
    ):
        """
        TEST 5: When releasing a table, assign to first pending match across all rounds

        Given: Completed match in round 1, pending match in round 2
        When: Table is released
        Then: Table SHOULD be assigned to round 2 match (first pending)
              And completed match should have no table

        NOTE: Cross-round assignment maximizes table utilization. Matches are
        ordered by round_number, so earlier rounds get priority.
        """
        # Round 1 match with table
        match_r1 = Match(
            gara_id=gara_with_venue.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
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
        TableAssignmentService.release_and_reassign_table(match_r1.id)

        # Assert - Round 2 match SHOULD get a table (cross-round assignment)
        db_session.refresh(match_r2)
        # With pull strategy, we can't guarantee WHICH table gets assigned,
        # only that ONE of the available tables is assigned
        assert match_r2.table_assignment in ["Tavolo A", "Tavolo B", "Tavolo C"]
        assert match_r2.status == MatchStatus.PLAYING.value

        # Completed match should have table released
        db_session.refresh(match_r1)
        assert match_r1.table_assignment is None

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

    def test_lost_table_recovered_when_players_free(
        self, db_session, gara_with_venue, players
    ):
        """
        TEST 8: Tables should NOT be lost when no eligible match exists

        This test verifies the fix for the bug where tables were "lost" when:
        1. A match completes and frees its table
        2. But no pending match is eligible (players busy)
        3. The table was removed from completed match but never reassigned

        Scenario:
        - 2 tables: "Tavolo A", "Tavolo B"
        - Match 1: A vs B (playing on Tavolo A)
        - Match 2: C vs D (playing on Tavolo B)
        - Match 3: A vs C (pending - both busy!)
        - Match 4: B vs D (pending - both busy!)

        When Match 1 completes:
        - Tavolo A is freed
        - Match 3 can't use it (A is free but C is still playing)
        - Match 4 can't use it (B is free but D is still playing)
        - OLD BUG: Tavolo A is "lost"

        When Match 2 completes:
        - Tavolo B is freed
        - NOW both A and C are free → Match 3 should get a table
        - NOW both B and D are free → Match 4 should get a table
        - With pull strategy, BOTH freed tables should be used
        """
        # Setup: Create 4 players (A, B, C, D)
        player_a, player_b, player_c, player_d = (
            players[0],
            players[1],
            players[2],
            players[3],
        )

        # Limit available tables to 2
        gara_with_venue.set_available_tables(["Tavolo A", "Tavolo B"])
        db_session.commit()

        # Match 1: A vs B (playing on Tavolo A)
        match1 = Match(
            gara_id=gara_with_venue.id,
            round_number=1,
            player1_id=player_a.id,
            player2_id=player_b.id,
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo A",
        )
        db_session.add(match1)

        # Match 2: C vs D (playing on Tavolo B)
        match2 = Match(
            gara_id=gara_with_venue.id,
            round_number=1,
            player1_id=player_c.id,
            player2_id=player_d.id,
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo B",
        )
        db_session.add(match2)

        # Match 3: A vs C (pending - cross-pairing, BOTH busy!)
        match3 = Match(
            gara_id=gara_with_venue.id,
            round_number=2,
            player1_id=player_a.id,
            player2_id=player_c.id,
            status=MatchStatus.PENDING.value,
            table_assignment=None,
        )
        db_session.add(match3)

        # Match 4: B vs D (pending - cross-pairing, BOTH busy!)
        match4 = Match(
            gara_id=gara_with_venue.id,
            round_number=2,
            player1_id=player_b.id,
            player2_id=player_d.id,
            status=MatchStatus.PENDING.value,
            table_assignment=None,
        )
        db_session.add(match4)
        db_session.commit()

        # Act 1: Complete Match 1 (A vs B) - frees A and B
        match1.status = MatchStatus.CLOSED_UNILATERALLY.value
        match1.winner_id = player_a.id
        db_session.commit()

        result1 = TableAssignmentService.release_and_reassign_table(match1.id)

        # Assert 1: No match should get the table (C and D still busy)
        db_session.refresh(match3)
        db_session.refresh(match4)
        assert result1 is None, "No match should be eligible yet"
        assert match3.table_assignment is None
        assert match4.table_assignment is None

        # Act 2: Complete Match 2 (C vs D) - frees C and D
        match2.status = MatchStatus.CLOSED_UNILATERALLY.value
        match2.winner_id = player_c.id
        db_session.commit()

        TableAssignmentService.release_and_reassign_table(match2.id)

        # Assert 2: NOW both pending matches should have tables!
        db_session.refresh(match3)
        db_session.refresh(match4)

        # With pull strategy, BOTH tables should be recovered
        assert match3.table_assignment is not None, "Match 3 should have a table"
        assert match3.status == MatchStatus.PLAYING.value
        assert match4.table_assignment is not None, "Match 4 should have a table"
        assert match4.status == MatchStatus.PLAYING.value

        # Verify both tables are in use
        assigned_tables = {match3.table_assignment, match4.table_assignment}
        assert assigned_tables == {"Tavolo A", "Tavolo B"}
