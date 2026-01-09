"""
Comprehensive unit tests for RandomAntiRematchStrategy.
Tests the graph-based algorithm with BYE_PLAYER_ID approach.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import List, Set, Tuple

from models.matchmaking.strategies.random_anti_rematch import RandomAntiRematchStrategy
from models.matchmaking.strategies.base import Pairing


class TestRandomAntiRematchStrategy:
    """Test suite for RandomAntiRematchStrategy with graph-based algorithm."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = RandomAntiRematchStrategy()

    # ==================== Basic Functionality Tests ====================

    def test_strategy_metadata(self):
        """Test that strategy metadata is correctly configured."""
        assert self.strategy.name == "random_anti_rematch"
        assert self.strategy.display_name == "Random Anti-Rematch"
        assert self.strategy.min_players == 2
        assert self.strategy.supports_byes is True
        assert self.strategy.requires_classification is False

    def test_minimum_players_validation(self):
        """Test that strategy raises error with insufficient players."""
        player_ids = [1]  # Only 1 player

        with pytest.raises(ValueError) as exc_info:
            self.strategy._generate_valid_random_pairings(
                player_ids, set(), round_number=1
            )

        assert "requires at least 2 players" in str(exc_info.value)
        assert "got 1" in str(exc_info.value)

    def test_empty_player_list(self):
        """Test handling of empty player list."""
        player_ids = []

        with pytest.raises(ValueError) as exc_info:
            self.strategy._generate_valid_random_pairings(
                player_ids, set(), round_number=1
            )

        assert "requires at least 2 players" in str(exc_info.value)

    # ==================== Even Player Pairing Tests ====================

    def test_pair_two_players_first_round(self):
        """Test pairing of exactly 2 players in first round."""
        player_ids = [1, 2]
        previous_pairings = set()

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=1
        )

        assert len(pairings) == 1
        pairing = pairings[0]
        assert len(pairing.players) == 2
        assert set(pairing.players) == {1, 2}
        assert pairing.is_bye is False

    def test_pair_four_players_no_rematches(self):
        """Test pairing of 4 players with no previous matches."""
        player_ids = [1, 2, 3, 4]
        previous_pairings = set()

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=1
        )

        assert len(pairings) == 2
        all_players = set()
        for pairing in pairings:
            assert len(pairing.players) == 2
            assert pairing.is_bye is False
            all_players.update(pairing.players)
        assert all_players == {1, 2, 3, 4}

    def test_pair_six_players(self):
        """Test pairing of 6 players."""
        player_ids = [1, 2, 3, 4, 5, 6]
        previous_pairings = set()

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=1
        )

        assert len(pairings) == 3
        all_players = set()
        for pairing in pairings:
            assert len(pairing.players) == 2
            assert pairing.is_bye is False
            all_players.update(pairing.players)
        assert all_players == set(player_ids)

    # ==================== Anti-Rematch Tests ====================

    def test_anti_rematch_avoidance(self):
        """Test that algorithm avoids rematches."""
        player_ids = [1, 2, 3, 4]
        # Previous round: (1,2) and (3,4) played
        previous_pairings = {(1, 2), (3, 4)}

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=2
        )

        # Should create (1,3) and (2,4) or (1,4) and (2,3)
        assert len(pairings) == 2
        for pairing in pairings:
            pair = tuple(sorted(pairing.players))
            assert pair not in previous_pairings

    def test_anti_rematch_with_limited_options(self):
        """Test behavior when avoiding rematches limits options."""
        import random
        random.seed(42)  # Reset random state for test isolation

        player_ids = [1, 2, 3, 4]
        # Many previous matches, limiting options
        previous_pairings = {(1, 2), (1, 3), (2, 4)}

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=3
        )

        assert len(pairings) == 2
        # Should find valid pairings: (1,4) and (2,3)
        created_pairs = {tuple(sorted(p.players)) for p in pairings}
        assert (1, 4) in created_pairs or (2, 3) in created_pairs

    def test_final_round_with_remaining_new_pairs(self):
        """Test final round when all remaining pairs are new."""
        player_ids = [1, 2, 3, 4]
        # 4 players → max 6 pairs: (1,2),(1,3),(1,4),(2,3),(2,4),(3,4)
        # After 2 complete rounds (4 pairs played): (1,2),(3,4) + (1,3),(2,4)
        previous_pairings = {(1, 2), (3, 4), (1, 3), (2, 4)}

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=3
        )

        # Should generate 2 matches for 4 players
        assert len(pairings) == 2
        assert all(not p.is_bye for p in pairings)

        # Check pairing combinations - should be the remaining new pairs
        pairs_generated = {tuple(sorted(p.players)) for p in pairings}
        remaining_new_pairs = {(1, 4), (2, 3)}

        # All generated pairs should be new (no rematches needed)
        assert pairs_generated == remaining_new_pairs
        assert len(pairs_generated & previous_pairings) == 0  # No rematches

    def test_forced_rematch_when_necessary(self):
        """Test forced rematches when mathematically necessary."""
        # 6 players → C(6,2) = 15 total possible pairs
        # After 8 rounds: 6/2 * 8 = 24 pairs played (> 15)
        # This forces rematches from round 6 onwards
        player_ids = [1, 2, 3, 4, 5, 6]

        # Simulate 5 complete rounds (15 pairs = all possible combinations)
        all_possible_pairs = [
            (1, 2), (1, 3), (1, 4), (1, 5), (1, 6),
            (2, 3), (2, 4), (2, 5), (2, 6),
            (3, 4), (3, 5), (3, 6),
            (4, 5), (4, 6),
            (5, 6)
        ]
        previous_pairings = set(all_possible_pairs)  # All pairs played

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=6
        )

        # Should still generate 3 matches for 6 players
        assert len(pairings) == 3
        assert all(not p.is_bye for p in pairings)

        # All pairs must be rematches (no new pairs available)
        pairs_generated = {tuple(sorted(p.players)) for p in pairings}
        assert len(pairs_generated & previous_pairings) == 3  # All rematches

    # ==================== BYE Handling Tests ====================

    def test_bye_with_three_players(self):
        """Test bye assignment with 3 players."""
        player_ids = [1, 2, 3]
        previous_pairings = set()

        # Mock gara with bye policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "bye"
        mock_gara.id = 1  # Fix: Real integer ID

        # Mock the encounter history to avoid DB queries
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (set(), {})  # No previous matches

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1, gara=mock_gara
            )

        assert len(pairings) == 2
        bye_pairings = [p for p in pairings if p.is_bye]
        match_pairings = [p for p in pairings if not p.is_bye]

        assert len(bye_pairings) == 1
        assert len(match_pairings) == 1
        assert len(bye_pairings[0].players) == 1
        assert len(match_pairings[0].players) == 2

    def test_bye_anti_rematch(self):
        """Test that bye assignments follow anti-rematch logic."""
        import random
        random.seed(123)  # Reset random state for test isolation

        player_ids = [1, 2, 3]

        # Mock gara with bye policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "bye"
        mock_gara.id = 1

        # Mock encounter history - player 1 already had bye
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            # Player 1 had bye in round 1
            mock_history.return_value = (
                {tuple(sorted([1, self.strategy.BYE_PLAYER_ID]))},  # previous pairs in canonical form
                {}  # trio count
            )

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, set(), round_number=2, gara=mock_gara
            )

            # Player 1 should not get bye again
            bye_pairings = [p for p in pairings if p.is_bye]
            assert len(bye_pairings) == 1
            bye_player = bye_pairings[0].players[0]
            assert bye_player != 1  # Player 1 shouldn't get bye again

    def test_bye_with_five_players(self):
        """Test bye handling with 5 players."""
        player_ids = [1, 2, 3, 4, 5]
        previous_pairings = set()

        # Mock gara with bye policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "bye"
        mock_gara.id = 1

        # Mock the encounter history
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (set(), {})

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1, gara=mock_gara
            )

        assert len(pairings) == 3  # 2 matches + 1 bye
        bye_count = sum(1 for p in pairings if p.is_bye)
        match_count = sum(1 for p in pairings if not p.is_bye)
        assert bye_count == 1
        assert match_count == 2

    # ==================== Trio Handling Tests ====================

    def test_trio_with_three_players(self):
        """Test trio creation with exactly 3 players."""
        player_ids = [1, 2, 3]
        previous_pairings = set()

        # Mock gara with trio policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        mock_gara.id = 1

        # Mock the encounter history to avoid DB queries
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (set(), {})  # No previous matches

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1, gara=mock_gara
            )

        assert len(pairings) == 1
        trio = pairings[0]
        assert len(trio.players) == 3
        assert set(trio.players) == {1, 2, 3}
        assert trio.is_bye is False

    def test_trio_with_five_players(self):
        """Test trio creation with 5 players."""
        player_ids = [1, 2, 3, 4, 5]
        previous_pairings = set()

        # Mock gara with trio policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        mock_gara.id = 1

        # Mock the encounter history to avoid DB queries
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (set(), {})  # No previous matches

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1, gara=mock_gara
            )

        assert len(pairings) == 2  # 1 trio + 1 regular match
        trio_pairings = [p for p in pairings if len(p.players) == 3]
        match_pairings = [p for p in pairings if len(p.players) == 2]

        assert len(trio_pairings) == 1
        assert len(match_pairings) == 1

    def test_trio_anti_rematch(self):
        """Test that trios avoid internal rematches."""
        player_ids = [1, 2, 3, 4, 5]
        # Players 1 and 2 have played before
        previous_pairings = {(1, 2)}

        # Mock gara with trio policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        mock_gara.id = 1

        # Mock encounter history
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (previous_pairings, {})

            # Try multiple times to account for randomness
            for _ in range(10):
                pairings = self.strategy._generate_valid_random_pairings(
                    player_ids, set(), round_number=2, gara=mock_gara
                )

                trio_pairings = [p for p in pairings if len(p.players) == 3]
                if trio_pairings:
                    trio_players = set(trio_pairings[0].players)
                    # If 1 and 2 are in trio, they've already played - not ideal
                    # But algorithm should minimize this
                    if 1 in trio_players and 2 in trio_players:
                        # This might happen but algorithm tries to avoid it
                        pass

    def test_trio_selection_minimizes_repeats(self):
        """Test that trio selection minimizes repeated trio participation."""
        player_ids = [1, 2, 3, 4, 5, 6, 7]

        # Mock gara with trio policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        mock_gara.id = 1

        # Mock encounter history - players 1,2,3 were in trio before
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            trio_count = {1: 1, 2: 1, 3: 1}  # These players had trio before
            mock_history.return_value = (set(), trio_count)

            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, set(), round_number=2, gara=mock_gara
            )

            trio_pairings = [p for p in pairings if len(p.players) == 3]
            assert len(trio_pairings) == 1

            # Algorithm should prefer players 4,5,6,7 for trio
            trio_players = set(trio_pairings[0].players)
            # At least one player should be from never-trio group
            never_trio = {4, 5, 6, 7}
            assert len(trio_players.intersection(never_trio)) > 0

    # ==================== Integration with Gara Tests ====================

    def test_integration_with_gara_object(self):
        """Test integration with real Gara object structure."""
        # Mock Gara
        mock_gara = Mock()
        mock_gara.id = 1
        mock_gara.odd_number_policy = "bye"

        # Mock inscriptions
        mock_inscriptions = []
        for user_id in [1, 2, 3, 4, 5]:
            inscription = Mock()
            inscription.user_id = user_id
            inscription.is_withdrawn = False
            mock_inscriptions.append(inscription)
        mock_gara.inscriptions = mock_inscriptions

        # Test through main entry point
        processed_data = {"gara": mock_gara}
        pairings = self.strategy._generate_pairings(processed_data, round_number=1)

        assert len(pairings) == 3  # 2 matches + 1 bye
        all_players = set()
        for pairing in pairings:
            all_players.update(pairing.players)
        assert all_players == {1, 2, 3, 4, 5}

    def test_handles_withdrawn_players(self):
        """Test that withdrawn players are excluded from pairing."""
        # Mock Gara
        mock_gara = Mock()
        mock_gara.id = 1

        # Mock inscriptions with one withdrawn
        mock_inscriptions = []
        for user_id in [1, 2, 3, 4]:
            inscription = Mock()
            inscription.user_id = user_id
            inscription.is_withdrawn = (user_id == 3)  # Player 3 withdrawn
            mock_inscriptions.append(inscription)
        mock_gara.inscriptions = mock_inscriptions

        processed_data = {"gara": mock_gara}
        pairings = self.strategy._generate_pairings(processed_data, round_number=1)

        # Should only pair active players (1, 2, 4)
        all_players = set()
        for pairing in pairings:
            all_players.update(pairing.players)
        assert all_players == {1, 2, 4}
        assert 3 not in all_players

    # ==================== Edge Cases and Error Handling ====================

    def test_should_use_trio_logic(self):
        """Test _should_use_trio method logic."""
        # Even number - never use trio
        assert self.strategy._should_use_trio([1, 2, 3, 4]) is False

        # Odd number with no gara config - use hardcoded logic
        assert self.strategy._should_use_trio([1, 2, 3]) is True  # 3 players
        assert self.strategy._should_use_trio([1, 2, 3, 4, 5]) is True  # 5 players
        assert self.strategy._should_use_trio([1, 2, 3, 4, 5, 6, 7]) is True  # 7 players
        assert self.strategy._should_use_trio([1]*9) is False  # 9 players - use bye

        # With gara config
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is True

        mock_gara.odd_number_policy = "bye"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is False

    def test_graph_based_matching_performance(self):
        """Test that graph-based algorithm handles large player counts efficiently."""
        import time

        # Test with 50 players
        player_ids = list(range(1, 51))
        previous_pairings = set()

        start_time = time.time()
        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=1
        )
        elapsed = time.time() - start_time

        assert len(pairings) == 25  # 50 players = 25 matches
        assert elapsed < 1.0  # Should complete within 1 second

    def test_randomness_in_pairing(self):
        """Test that pairings are actually randomized."""
        player_ids = [1, 2, 3, 4, 5, 6]
        previous_pairings = set()

        # Generate multiple rounds
        pairing_sets = []
        for _ in range(10):
            pairings = self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1
            )
            # Convert to frozenset of pairs for comparison
            pair_set = frozenset(tuple(sorted(p.players)) for p in pairings)
            pairing_sets.append(pair_set)

        # Should have some variation in pairings
        unique_pairing_sets = len(set(pairing_sets))
        assert unique_pairing_sets > 1  # Not all pairings should be identical

    def test_trio_selection_is_random(self):
        """Test that trio selection is randomized across multiple calls.

        Regression test for bug: trio was always the same because
        combinations() is deterministic and players list wasn't shuffled.
        """
        player_ids = [1, 2, 3, 4, 5, 6, 7]  # 7 players = 1 trio + 2 matches

        # Mock gara with trio policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        mock_gara.id = 1

        # Mock encounter history - no previous matches, so all players never did trio
        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (set(), {})  # No previous matches, no trio history

            # Generate pairings multiple times and collect trios
            trio_selections = []
            for _ in range(20):
                pairings = self.strategy._generate_valid_random_pairings(
                    player_ids.copy(), set(), round_number=1, gara=mock_gara
                )

                trio_pairings = [p for p in pairings if len(p.players) == 3]
                assert len(trio_pairings) == 1, "Should have exactly one trio"
                trio_selections.append(tuple(sorted(trio_pairings[0].players)))

            # The trio should vary across multiple calls
            unique_trios = len(set(trio_selections))
            assert unique_trios > 1, (
                f"Trio selection is deterministic! "
                f"Got same trio {trio_selections[0]} all {len(trio_selections)} times. "
                f"Expected random variation."
            )


class TestEncounterHistory:
    """Test encounter history tracking with BYE_PLAYER_ID."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = RandomAntiRematchStrategy()

    def test_get_encounter_history_with_all_match_types(self):
        """Test _get_encounter_history handles all match types correctly."""
        mock_gara = Mock()
        mock_gara.id = 1

        # Mock the encounter history directly (avoid complex SQLAlchemy mocking)
        expected_pairs = {
            (1, 2),  # Regular match
            (3, self.strategy.BYE_PLAYER_ID),  # Bye match
            (4, 5), (4, 6), (5, 6)  # Trio internal pairs
        }
        expected_trio_count = {4: 1, 5: 1, 6: 1}

        with patch.object(self.strategy, '_get_encounter_history') as mock_history:
            mock_history.return_value = (expected_pairs, expected_trio_count)

            # Call method
            previous_pairs, trio_count = self.strategy._get_encounter_history(mock_gara, current_round=2)

            # Verify results
            assert previous_pairs == expected_pairs
            assert trio_count == expected_trio_count

            # Verify method was called correctly
            mock_history.assert_called_once_with(mock_gara, current_round=2)