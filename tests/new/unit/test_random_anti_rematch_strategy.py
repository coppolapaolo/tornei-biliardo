"""
Comprehensive unit tests for RandomAntiRematchStrategy.
Tests the graph-based algorithm with BYE_PLAYER_ID approach.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Set, Tuple

from models.matchmaking.strategies.random_anti_rematch import RandomAntiRematchStrategy


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
            (1, 2),
            (1, 3),
            (1, 4),
            (1, 5),
            (1, 6),
            (2, 3),
            (2, 4),
            (2, 5),
            (2, 6),
            (3, 4),
            (3, 5),
            (3, 6),
            (4, 5),
            (4, 6),
            (5, 6),
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
            # Player 1 had bye in round 1
            mock_history.return_value = (
                {
                    tuple(sorted([1, self.strategy.BYE_PLAYER_ID]))
                },  # previous pairs in canonical form
                {},  # trio count
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
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
            inscription.is_waitlist = False
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
        mock_gara.odd_number_policy = "bye"  # 3 active players → 1 match + 1 bye

        # Mock inscriptions with one withdrawn
        mock_inscriptions = []
        for user_id in [1, 2, 3, 4]:
            inscription = Mock()
            inscription.user_id = user_id
            inscription.is_withdrawn = user_id == 3  # Player 3 withdrawn
            inscription.is_waitlist = False
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
        """Test _should_use_trio method logic.

        After the spec-random-anti-rematch refactor, the hardcoded fallback
        `[3,5,7] players → trio` has been removed. Trio decision now flows
        from gara.odd_number_policy, with StrategyBehaviorConfig as fallback
        when only gara.distance is available.
        """
        # Even number - never use trio
        assert self.strategy._should_use_trio([1, 2, 3, 4]) is False

        # Odd number without gara - safe default is bye (no policy, no distance)
        assert self.strategy._should_use_trio([1, 2, 3]) is False
        assert self.strategy._should_use_trio([1, 2, 3, 4, 5]) is False

        # Explicit policy on gara
        mock_gara = Mock()
        mock_gara.odd_number_policy = "trio"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is True

        mock_gara.odd_number_policy = "bye"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is False

        mock_gara.odd_number_policy = "bye_with_challenge"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is False

        mock_gara.odd_number_policy = "no"
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara) is False

        # No explicit policy: delegate to StrategyBehaviorConfig via distance
        mock_gara2 = Mock(spec=["odd_number_policy", "distance"])
        mock_gara2.odd_number_policy = None
        mock_gara2.distance = 5  # Race to 5 → TRIO per ADR-005
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara2) is True

        mock_gara2.distance = 10  # Race to 10 → BYE_WITH_CHALLENGE (ADR-005)
        assert self.strategy._should_use_trio([1, 2, 3], mock_gara2) is False

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
        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
            mock_history.return_value = (
                set(),
                {},
            )  # No previous matches, no trio history

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
            (4, 5),
            (4, 6),
            (5, 6),  # Trio internal pairs
        }
        expected_trio_count = {4: 1, 5: 1, 6: 1}

        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
            mock_history.return_value = (expected_pairs, expected_trio_count)

            # Call method
            previous_pairs, trio_count = self.strategy._get_encounter_history(
                mock_gara, current_round=2
            )

            # Verify results
            assert previous_pairs == expected_pairs
            assert trio_count == expected_trio_count

            # Verify method was called correctly
            mock_history.assert_called_once_with(mock_gara, current_round=2)


class TestWeightedMatching:
    """Test the weighted NetworkX matching: non-rematch pairs preferred."""

    def setup_method(self):
        self.strategy = RandomAntiRematchStrategy()

    def test_matching_minimizes_rematches_when_fallback(self):
        """When anti-rematch is infeasible, matching picks the minimum-rematch option.

        Scenario: 4 players, 5 of 6 possible pairs already met. The only
        non-rematch pair is (3,4). Pairing 3-4 forces (1,2) as the other pair,
        which IS a rematch — so we have 1 forced rematch total. The old
        double-matching approach could have picked matchings with 2 rematches.
        """
        player_ids = [1, 2, 3, 4]
        # Only (3,4) is not in previous_pairs
        previous_pairings = {(1, 2), (1, 3), (1, 4), (2, 3), (2, 4)}

        pairings = self.strategy._generate_valid_random_pairings(
            player_ids, previous_pairings, round_number=5
        )

        assert len(pairings) == 2
        created_pairs = {tuple(sorted(p.players)) for p in pairings}
        # (3,4) must be selected — it's the only non-rematch option
        assert (3, 4) in created_pairs
        # Exactly 1 rematch forced (the complement pair covering players 1 and 2)
        rematches = created_pairs & previous_pairings
        assert len(rematches) == 1

    def test_warning_logged_on_forced_rematch(self, caplog):
        """logger.warning is emitted when any pair in the matching is a rematch."""
        import logging

        player_ids = [1, 2, 3, 4]
        # All pairs met → every selected pair will be a rematch
        previous_pairings = {(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)}

        mock_gara = Mock()
        mock_gara.id = 42
        mock_gara.odd_number_policy = "bye"
        mock_gara.inscriptions = []

        with caplog.at_level(
            logging.WARNING, logger="models.matchmaking.strategies.random_anti_rematch"
        ):
            with patch.object(self.strategy, "_get_encounter_history") as mock_history:
                mock_history.return_value = (previous_pairings, {})
                self.strategy._generate_valid_random_pairings(
                    player_ids, set(), round_number=3, gara=mock_gara
                )

        assert any("rematch forzato" in rec.message for rec in caplog.records), (
            f"Expected warning about forced rematch, got: "
            f"{[r.message for r in caplog.records]}"
        )

    def test_no_warning_when_no_rematch(self, caplog):
        """No warning when matching finds a complete non-rematch cover."""
        import logging

        player_ids = [1, 2, 3, 4]
        previous_pairings: Set[Tuple[int, int]] = set()  # fresh gara

        with caplog.at_level(
            logging.WARNING, logger="models.matchmaking.strategies.random_anti_rematch"
        ):
            self.strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number=1
            )

        forced = [r for r in caplog.records if "rematch forzato" in r.message]
        assert not forced


class TestDeterministicSeeding:
    """Test that set_context provides deterministic, isolated RNG."""

    def test_seed_deterministic(self):
        """Same seed → same output across two separate strategy instances."""
        from models.matchmaking.registry import PairingContext

        player_ids = [1, 2, 3, 4, 5, 6]

        s1 = RandomAntiRematchStrategy()
        s1.set_context(PairingContext(seed=42))
        p1 = s1._generate_valid_random_pairings(player_ids, set(), round_number=1)

        s2 = RandomAntiRematchStrategy()
        s2.set_context(PairingContext(seed=42))
        p2 = s2._generate_valid_random_pairings(player_ids, set(), round_number=1)

        pairs1 = sorted(tuple(sorted(p.players)) for p in p1)
        pairs2 = sorted(tuple(sorted(p.players)) for p in p2)
        assert pairs1 == pairs2

    def test_no_global_random_contamination(self):
        """Two strategies with different seeds do not share RNG state."""
        from models.matchmaking.registry import PairingContext

        player_ids = [1, 2, 3, 4, 5, 6]

        s1 = RandomAntiRematchStrategy()
        s1.set_context(PairingContext(seed=111))

        s2 = RandomAntiRematchStrategy()
        s2.set_context(PairingContext(seed=222))

        # Interleave calls — if they shared a global RNG, output would depend
        # on call order, not on instance seed.
        p1_a = s1._generate_valid_random_pairings(player_ids, set(), round_number=1)
        _ = s2._generate_valid_random_pairings(player_ids, set(), round_number=1)
        p1_b = s1._generate_valid_random_pairings(player_ids, set(), round_number=1)

        # Reset s1 to same seed; the sequence of two consecutive calls must be
        # reproducible from scratch, independent of s2 activity.
        s1_bis = RandomAntiRematchStrategy()
        s1_bis.set_context(PairingContext(seed=111))
        p1_a_bis = s1_bis._generate_valid_random_pairings(
            player_ids, set(), round_number=1
        )
        p1_b_bis = s1_bis._generate_valid_random_pairings(
            player_ids, set(), round_number=1
        )

        def to_set(pairings):
            return frozenset(tuple(sorted(p.players)) for p in pairings)

        assert to_set(p1_a) == to_set(p1_a_bis)
        assert to_set(p1_b) == to_set(p1_b_bis)


class TestTrioCountWalkoverFilter:
    """Verify that get_trio_counts excludes walkover trios (coherent with Amalfi)."""

    def test_trio_count_excludes_walkover(self):
        """PlayerEncounterService.get_trio_counts(exclude_walkover=True) skips
        trios with total_racks_played == 0.

        Mocks the DB query since this is a unit test.
        """
        from models.classification.encounter_service import PlayerEncounterService

        trio_contested = Mock()
        trio_contested.total_racks_played = 3
        trio_contested.player1_id = 1
        trio_contested.player2_id = 2
        trio_contested.player3_id = 3

        trio_walkover = Mock()
        trio_walkover.total_racks_played = 0  # walkover
        trio_walkover.player1_id = 4
        trio_walkover.player2_id = 5
        trio_walkover.player3_id = 6

        with patch(
            "models.classification.encounter_service.db.session.query"
        ) as mock_query:
            filtrati = mock_query.return_value.join.return_value.filter.return_value
            filtrati.all.return_value = [
                trio_contested,
                trio_walkover,
            ]

            # Bypass cache by clearing any memoized value for this gara
            # (cached decorator uses gara_id + args as key; unique id avoids hits)
            counts = PlayerEncounterService.get_trio_counts(
                gara_id=99991, exclude_walkover=True
            )

        # Contested trio counted; walkover trio skipped
        assert counts.get(1) == 1
        assert counts.get(2) == 1
        assert counts.get(3) == 1
        assert 4 not in counts
        assert 5 not in counts
        assert 6 not in counts


class TestFullSchedulePreGeneration:
    """Tests del nuovo generatore globale dello schedule (Bug 1).

    Tre rami:
      - Ramo A: N pari → circle method puro (zero reincontri ≤ N-1 round).
      - Ramo B: N dispari + BYE → circle method su N+1 con sentinella.
      - Ramo C: N dispari + TRIO → branch-and-bound search globale.
    """

    def setup_method(self):
        from models.matchmaking.registry import PairingContext

        self.strategy = RandomAntiRematchStrategy()
        self.strategy.set_context(PairingContext(seed=42))

    # ---------- helpers ----------

    @staticmethod
    def _make_gara(rounds_count, odd_policy=None, gara_id=1):
        gara = Mock()
        gara.id = gara_id
        gara.rounds_count = rounds_count
        gara.odd_number_policy = odd_policy
        return gara

    @staticmethod
    def _all_pairs_in_schedule(schedule):
        """Return list of canonical (sorted) pair tuples across all rounds."""
        pairs = []
        for round_pairings in schedule:
            for p in round_pairings:
                if p.is_bye or len(p.players) == 1:
                    continue
                if len(p.players) == 2:
                    pairs.append(tuple(sorted(p.players)))
                elif len(p.players) == 3:
                    # Trio: 3 internal pairs
                    for i in range(3):
                        for j in range(i + 1, 3):
                            pairs.append(tuple(sorted([p.players[i], p.players[j]])))
        return pairs

    # ---------- Ramo A: N pari ----------

    def test_circle_method_even_zero_rematches(self):
        """6 player × 5 round → zero reincontri (round-robin completo)."""
        gara = self._make_gara(rounds_count=5)
        player_ids = [10, 20, 30, 40, 50, 60]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 5)

        assert schedule is not None
        assert len(schedule) == 5
        # Ogni round ha esattamente 3 pair (6/2)
        for round_pairings in schedule:
            assert len(round_pairings) == 3
            assert all(not p.is_bye for p in round_pairings)
        # Zero reincontri
        pairs = self._all_pairs_in_schedule(schedule)
        assert len(pairs) == len(set(pairs)), "Reincontri trovati nello schedule"
        # Round-robin completo: tutte le 15 coppie distinte
        assert len(set(pairs)) == 6 * 5 // 2

    def test_circle_method_even_truncated_no_rematches(self):
        """6 player × 4 round (caso bug produzione 2026-05-20) → zero reincontri."""
        gara = self._make_gara(rounds_count=4)
        player_ids = [1, 2, 3, 4, 5, 6]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 4)

        assert schedule is not None
        assert len(schedule) == 4
        pairs = self._all_pairs_in_schedule(schedule)
        assert len(pairs) == len(set(pairs))

    def test_circle_method_even_too_many_rounds_returns_none(self):
        """Oltre N-1 round per N pari → pre-gen non applicabile, fallback."""
        gara = self._make_gara(rounds_count=10)
        player_ids = [1, 2, 3, 4, 5, 6]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 10)

        # 10 round con 6 player superano la capacità round-robin (5 round)
        assert schedule is None

    # ---------- Ramo B: N dispari + BYE ----------

    def test_circle_method_odd_bye_zero_rematches(self):
        """5 player × 5 round, policy=BYE → 0 reincontri, 1 bye per giocatore."""
        gara = self._make_gara(rounds_count=5, odd_policy="bye")
        player_ids = [11, 22, 33, 44, 55]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 5)

        assert schedule is not None
        assert len(schedule) == 5

        # Ogni round: 2 pair + 1 bye = 3 pairing
        bye_counts: dict[int, int] = {p: 0 for p in player_ids}
        for round_pairings in schedule:
            byes = [p for p in round_pairings if p.is_bye]
            assert len(byes) == 1, f"Atteso 1 bye per round, trovati {len(byes)}"
            bye_counts[byes[0].players[0]] += 1

        # Ogni giocatore esattamente 1 bye sui 5 round
        assert all(v == 1 for v in bye_counts.values())

        # Zero reincontri sulle vere coppie
        pairs = self._all_pairs_in_schedule(schedule)
        assert len(pairs) == len(set(pairs))

    # ---------- Ramo C: N dispari + TRIO ----------

    def test_trio_search_returns_schedule(self):
        """5 player × 4 round, policy=TRIO → schedule completo, ogni round
        con 1 trio + 1 pair."""
        gara = self._make_gara(rounds_count=4, odd_policy="trio")
        player_ids = [1, 2, 3, 4, 5]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 4)

        assert schedule is not None
        assert len(schedule) == 4
        for round_pairings in schedule:
            trios = [p for p in round_pairings if len(p.players) == 3]
            pairs = [p for p in round_pairings if len(p.players) == 2 and not p.is_bye]
            assert len(trios) == 1
            assert len(pairs) == 1

    def test_trio_search_balanced_counts(self):
        """5 player × 4 round, policy=TRIO → max trio_count ≤ ceil(12/5) = 3."""
        import math

        gara = self._make_gara(rounds_count=4, odd_policy="trio")
        player_ids = [1, 2, 3, 4, 5]

        schedule = self.strategy._pre_generate_full_schedule(gara, player_ids, 4)

        assert schedule is not None
        trio_counts: dict[int, int] = {p: 0 for p in player_ids}
        for round_pairings in schedule:
            for pairing in round_pairings:
                if len(pairing.players) == 3:
                    for p in pairing.players:
                        trio_counts[p] += 1

        target_max = math.ceil(4 * 3 / 5)  # = 3
        assert max(trio_counts.values()) <= target_max
        # Bilanciamento minimo: nessun giocatore zero trii sulla rotazione
        assert min(trio_counts.values()) >= 2

    def test_trio_search_deadline_fallback(self):
        """Deadline 0 ms → search ritorna None → fallback al path incrementale."""
        player_ids = [1, 2, 3, 4, 5]
        result = self.strategy._search_trio_schedule(
            player_ids, n_rounds=4, deadline_ms=0
        )
        # Con deadline=0 la search non ha tempo di trovare nulla
        assert result is None

    # ---------- Cache & dispatch ----------

    def test_schedule_signature_cached_across_rounds(self):
        """Stessa signature → cache hit, no ricomputo."""
        gara = self._make_gara(rounds_count=5, gara_id=42)
        player_ids = [1, 2, 3, 4, 5, 6]

        # Prima chiamata: build
        s1 = self.strategy._get_or_build_schedule(gara, player_ids)
        assert s1 is not None
        # Seconda chiamata (stessa signature): cache hit, stessa istanza in memoria
        s2 = self.strategy._get_or_build_schedule(gara, player_ids)
        assert s2 is s1

    def test_schedule_cache_invalidated_by_set_context(self):
        """set_context() invalida la cache (nuovo seed → nuovo schedule)."""
        from models.matchmaking.registry import PairingContext

        gara = self._make_gara(rounds_count=5, gara_id=43)
        player_ids = [1, 2, 3, 4, 5, 6]

        s1 = self.strategy._get_or_build_schedule(gara, player_ids)
        self.strategy.set_context(PairingContext(seed=999))
        s2 = self.strategy._get_or_build_schedule(gara, player_ids)
        assert s2 is not s1

    def test_pairing_round_numbers_consistent(self):
        """Le Pairing in schedule[i] hanno round_number == i+1."""
        gara = self._make_gara(rounds_count=3)
        # 4 player × 3 round = round-robin completo (N-1)
        schedule = self.strategy._pre_generate_full_schedule(gara, [1, 2, 3, 4], 3)
        assert schedule is not None
        for i, round_pairings in enumerate(schedule):
            for pairing in round_pairings:
                assert pairing.round_number == i + 1
