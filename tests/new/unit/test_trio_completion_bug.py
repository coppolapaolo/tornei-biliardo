"""Unit tests for trio match completion logic.

Tests verify that trio matches complete at the correct rack count
for different distances (3, 4, 5).

Bug being fixed: Trio was completing 1 rack early due to inconsistent
session state when checking total_racks_played.
"""

from datetime import date
from models.match.models import Match, TrioMatch
from models.match.trio_scoring_service import TrioScoringService
from models.competition.models import Gara
from models.campionato.models import Campionato
from models.match.trio_config import TrioConfig


class TestTrioCompletionAtCorrectRack:
    """Test that trio completes at exactly the right rack count."""

    def _create_trio_setup(self, db_session, isolated_players, distance: int):
        """Helper to create a trio match with given distance."""
        # Create campionato and gara with specified distance
        campionato = Campionato(name=f"Test Campionato d{distance}")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            date=date.today(),
            distance=distance,
            discipline="9_ball",
        )
        db_session.add(gara)
        db_session.flush()

        # Create match
        p1, p2, p3 = isolated_players[0], isolated_players[1], isolated_players[2]
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            is_trio=True,
        )
        db_session.add(match)
        db_session.flush()

        # Create trio match
        trio = TrioMatch(
            match_id=match.id,
            player1_id=p1.id,
            player2_id=p2.id,
            player3_id=p3.id,
        )
        db_session.add(trio)
        db_session.commit()

        return trio, [p1, p2, p3]

    def test_distance_3_completes_at_rack_3(self, db_session, isolated_players):
        """Distance 3: 1 round (3 racks) + 1 bonus.

        Should complete at rack 3, not rack 2.
        Round-robin matchups:
        - Rack 1: P0 vs P1, P2 waits
        - Rack 2: P0 vs P2, P1 waits
        - Rack 3: P1 vs P2, P0 waits
        """
        trio, players = self._create_trio_setup(db_session, isolated_players, distance=3)
        config = trio.trio_config

        # Verify config
        assert config.num_rounds == 1
        assert config.total_played_racks == 3
        assert config.bonus_racks == 1

        # Add rack 1 (P0 vs P1) - should NOT complete
        TrioScoringService.add_rack_win(trio.id, players[0].id)
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.total_racks_played == 1
        assert not trio.is_completed, "Should not complete at rack 1"

        # Add rack 2 (P0 vs P2) - should NOT complete
        TrioScoringService.add_rack_win(trio.id, players[0].id)  # P0 wins again
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.total_racks_played == 2
        assert not trio.is_completed, "Should not complete at rack 2"

        # Add rack 3 (P1 vs P2) - SHOULD enter awaiting_confirmation
        TrioScoringService.add_rack_win(trio.id, players[1].id)  # P1 wins
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.total_racks_played == 3
        assert trio.awaiting_confirmation, "Should be awaiting confirmation at rack 3"
        assert not trio.is_completed, "Should not be completed until confirmed"

        # Confirm result - SHOULD complete
        trio.confirm_result_by_admin()
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.is_completed, "Should complete after confirmation"
        assert not trio.awaiting_confirmation, "Should no longer be awaiting confirmation"

    def test_distance_4_completes_at_rack_6(self, db_session, isolated_players):
        """Distance 4: 2 rounds (6 racks) + 0 bonus.

        Should complete at rack 6, not rack 5.
        Round-robin matchups (2 rounds):
        - Rack 1: P0 vs P1, Rack 2: P0 vs P2, Rack 3: P1 vs P2
        - Rack 4: P0 vs P1, Rack 5: P0 vs P2, Rack 6: P1 vs P2
        """
        trio, players = self._create_trio_setup(db_session, isolated_players, distance=4)
        config = trio.trio_config

        # Verify config
        assert config.num_rounds == 2
        assert config.total_played_racks == 6
        assert config.bonus_racks == 0

        # Add racks 1-5 using correct matchups - should NOT complete
        for i in range(5):
            matchup = config.get_matchup_for_rack(i + 1)
            p1_idx, _, _ = matchup
            TrioScoringService.add_rack_win(trio.id, players[p1_idx].id)
            db_session.commit()
            trio = db_session.get(TrioMatch, trio.id)
            assert trio.total_racks_played == i + 1, f"Expected {i+1} racks"
            assert not trio.is_completed, f"Should not complete at rack {i + 1}"

        # Add rack 6 - SHOULD enter awaiting_confirmation
        matchup = config.get_matchup_for_rack(6)
        p1_idx, _, _ = matchup
        TrioScoringService.add_rack_win(trio.id, players[p1_idx].id)
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.total_racks_played == 6
        assert trio.awaiting_confirmation, "Should be awaiting confirmation at rack 6"
        assert not trio.is_completed, "Should not be completed until confirmed"

        # Confirm result - SHOULD complete
        trio.confirm_result_by_admin()
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.is_completed, "Should complete after confirmation"

    def test_distance_5_completes_at_rack_6(self, db_session, isolated_players):
        """Distance 5: 2 rounds (6 racks) + 1 bonus.

        Should complete at rack 6, not rack 5.
        This is the bug from the user report.
        """
        trio, players = self._create_trio_setup(db_session, isolated_players, distance=5)
        config = trio.trio_config

        # Verify config
        assert config.num_rounds == 2
        assert config.total_played_racks == 6
        assert config.bonus_racks == 1

        # Add racks 1-5 - should NOT complete
        for i in range(5):
            # Use correct matchup for each rack
            matchup = config.get_matchup_for_rack(i + 1)
            p1_idx, _, _ = matchup
            winner_id = players[p1_idx].id  # Always first player wins
            TrioScoringService.add_rack_win(trio.id, winner_id)
            db_session.commit()
            trio = db_session.get(TrioMatch, trio.id)
            assert trio.total_racks_played == i + 1, f"Expected {i+1} racks, got {trio.total_racks_played}"
            assert not trio.is_completed, f"Should not complete at rack {i + 1}"

        # Add rack 6 - SHOULD enter awaiting_confirmation
        matchup = config.get_matchup_for_rack(6)
        p1_idx_final, _, _ = matchup
        TrioScoringService.add_rack_win(trio.id, players[p1_idx_final].id)
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.total_racks_played == 6
        assert trio.awaiting_confirmation, "Should be awaiting confirmation at rack 6"
        assert not trio.is_completed, "Should not be completed until confirmed"

        # Confirm result - SHOULD complete
        trio.confirm_result_by_admin()
        db_session.commit()
        trio = db_session.get(TrioMatch, trio.id)
        assert trio.is_completed, "Should complete after confirmation"


class TestTrioConfigCalculations:
    """Verify TrioConfig calculations are correct."""

    def test_distance_2_config(self):
        """Distance 2: 1 round, 0 bonus, 3 racks total."""
        config = TrioConfig(distance=2)
        assert config.num_rounds == 1
        assert config.bonus_racks == 0
        assert config.total_played_racks == 3

    def test_distance_3_config(self):
        """Distance 3: 1 round, 1 bonus, 3 racks total."""
        config = TrioConfig(distance=3)
        assert config.num_rounds == 1
        assert config.bonus_racks == 1
        assert config.total_played_racks == 3

    def test_distance_4_config(self):
        """Distance 4: 2 rounds, 0 bonus, 6 racks total."""
        config = TrioConfig(distance=4)
        assert config.num_rounds == 2
        assert config.bonus_racks == 0
        assert config.total_played_racks == 6

    def test_distance_5_config(self):
        """Distance 5: 2 rounds, 1 bonus, 6 racks total."""
        config = TrioConfig(distance=5)
        assert config.num_rounds == 2
        assert config.bonus_racks == 1
        assert config.total_played_racks == 6
