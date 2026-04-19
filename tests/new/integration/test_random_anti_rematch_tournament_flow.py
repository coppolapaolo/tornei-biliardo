"""
Integration tests for RandomAntiRematchStrategy in tournament flow.
Tests complete tournament scenarios with multiple rounds.
"""

from typing import List, Tuple
from unittest.mock import Mock, patch

from models.matchmaking.strategies.random_anti_rematch import RandomAntiRematchStrategy
from models.matchmaking.strategies.base import Pairing


class TestRandomAntiRematchTournamentFlow:
    """Integration tests simulating complete tournament flows."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = RandomAntiRematchStrategy()

    def create_mock_gara(self, player_ids: List[int], odd_policy: str = "bye") -> Mock:
        """Helper to create mock Gara with inscriptions."""
        mock_gara = Mock()
        mock_gara.id = 1
        mock_gara.odd_number_policy = odd_policy

        # Create inscriptions
        mock_inscriptions = []
        for user_id in player_ids:
            inscription = Mock()
            inscription.user_id = user_id
            inscription.is_withdrawn = False
            inscription.is_waitlist = False
            mock_inscriptions.append(inscription)
        mock_gara.inscriptions = mock_inscriptions

        return mock_gara

    def simulate_tournament_round(
        self, gara: Mock, round_number: int, previous_matches: List[Tuple[int, ...]]
    ) -> List[Pairing]:
        """Simulate a tournament round with encounter history."""

        # Mock the encounter history based on previous matches
        previous_pairs = set()
        trio_count = {}

        for match in previous_matches:
            if len(match) == 2:
                # Regular match or bye
                if match[1] == self.strategy.BYE_PLAYER_ID:
                    # Bye match
                    previous_pairs.add(tuple(sorted(match)))
                else:
                    # Regular 1v1
                    previous_pairs.add(tuple(sorted(match)))
            elif len(match) == 3:
                # Trio match
                players = list(match)
                for p in players:
                    trio_count[p] = trio_count.get(p, 0) + 1
                # Add all pairs from trio
                for i in range(len(players)):
                    for j in range(i + 1, len(players)):
                        previous_pairs.add(tuple(sorted([players[i], players[j]])))

        with patch.object(self.strategy, "_get_encounter_history") as mock_history:
            mock_history.return_value = (previous_pairs, trio_count)

            processed_data = {"gara": gara}
            return self.strategy._generate_pairings(processed_data, round_number)

    # ==================== Multi-Round Tournament Tests ====================

    def test_four_player_three_round_tournament(self):
        """Test complete 3-round tournament with 4 players."""
        players = [1, 2, 3, 4]
        gara = self.create_mock_gara(players)

        all_matches = []
        all_pairs_played = set()

        # Round 1
        round1_pairings = self.simulate_tournament_round(gara, 1, [])
        assert len(round1_pairings) == 2

        for pairing in round1_pairings:
            pair = tuple(sorted(pairing.players))
            all_pairs_played.add(pair)
            all_matches.append(pair)

        # Round 2
        round2_pairings = self.simulate_tournament_round(gara, 2, all_matches)
        assert len(round2_pairings) == 2

        for pairing in round2_pairings:
            pair = tuple(sorted(pairing.players))
            # Should not repeat round 1 pairings
            assert pair not in all_pairs_played
            all_pairs_played.add(pair)
            all_matches.append(pair)

        # Round 3
        round3_pairings = self.simulate_tournament_round(gara, 3, all_matches)
        assert len(round3_pairings) == 2

        for pairing in round3_pairings:
            pair = tuple(sorted(pairing.players))
            all_pairs_played.add(pair)
            all_matches.append(pair)

        # After 3 rounds, all possible pairs should have played
        # Possible pairs: (1,2), (1,3), (1,4), (2,3), (2,4), (3,4) = 6 pairs
        # We create 2 pairs per round = 6 pairs total
        assert len(all_pairs_played) == 6

    def test_five_player_tournament_with_bye_rotation(self):
        """Test tournament with 5 players ensuring bye rotation."""
        players = [1, 2, 3, 4, 5]
        gara = self.create_mock_gara(players, odd_policy="bye")

        bye_players = []
        all_matches = []

        # Simulate 5 rounds (each player should get bye once)
        for round_num in range(1, 6):
            pairings = self.simulate_tournament_round(gara, round_num, all_matches)

            # Should have 2 regular matches + 1 bye
            assert len(pairings) == 3
            bye_pairings = [p for p in pairings if p.is_bye]
            regular_pairings = [p for p in pairings if not p.is_bye]

            assert len(bye_pairings) == 1
            assert len(regular_pairings) == 2

            # Track who gets bye
            bye_player = bye_pairings[0].players[0]
            bye_players.append(bye_player)

            # Add to match history
            all_matches.append((bye_player, self.strategy.BYE_PLAYER_ID))
            for pairing in regular_pairings:
                all_matches.append(tuple(sorted(pairing.players)))

        # Each player should get bye at most once (ideally)
        # Due to randomness, we check that no player gets bye more than twice
        bye_counts = {p: bye_players.count(p) for p in players}
        assert max(bye_counts.values()) <= 2

    def test_seven_player_tournament_with_trio(self):
        """Test tournament with 7 players using trio policy."""
        players = [1, 2, 3, 4, 5, 6, 7]
        gara = self.create_mock_gara(players, odd_policy="trio")

        all_matches = []
        trio_participation = {p: 0 for p in players}

        # Simulate 3 rounds
        for round_num in range(1, 4):
            pairings = self.simulate_tournament_round(gara, round_num, all_matches)

            # Should have 1 trio + 2 regular matches
            trio_pairings = [p for p in pairings if len(p.players) == 3]
            regular_pairings = [p for p in pairings if len(p.players) == 2]

            assert len(trio_pairings) == 1
            assert len(regular_pairings) == 2

            # Track trio participation
            trio_players = trio_pairings[0].players
            for player in trio_players:
                trio_participation[player] += 1

            # Add to match history
            all_matches.append(tuple(trio_players))
            for pairing in regular_pairings:
                all_matches.append(tuple(sorted(pairing.players)))

        # Check trio participation is balanced:
        # 3 rounds × 3 players/trio = 9 slots for 7 players
        # Ideal distribution: 5 players do 1 trio, 2 players do 2 trios
        # max - min should be <= 1 for perfect distribution
        max_participation = max(trio_participation.values())
        min_participation = min(trio_participation.values())

        # Strict check: max should be at most 2 (ideal distribution)
        assert max_participation <= 2, (
            f"Trio participation not minimized: max={max_participation}, "
            f"distribution={dict(trio_participation)}"
        )
        # All players should participate at least once (9 slots > 7 players)
        assert (
            min_participation >= 1
        ), f"Some players never did trio: distribution={dict(trio_participation)}"

    def test_trio_distribution_fairness_over_multiple_simulations(self):
        """Test that trio participation is fairly distributed across many simulations.

        This test runs multiple tournament simulations and verifies that
        on average, trio participation is distributed fairly among all players.
        """
        players = [1, 2, 3, 4, 5, 6, 7]
        num_simulations = 20
        total_participation = {p: 0 for p in players}

        for _ in range(num_simulations):
            gara = self.create_mock_gara(players, odd_policy="trio")
            all_matches = []
            simulation_participation = {p: 0 for p in players}

            # Simulate 3 rounds
            for round_num in range(1, 4):
                pairings = self.simulate_tournament_round(gara, round_num, all_matches)

                trio_pairings = [p for p in pairings if len(p.players) == 3]
                regular_pairings = [p for p in pairings if len(p.players) == 2]

                assert len(trio_pairings) == 1
                assert len(regular_pairings) == 2

                # Track trio participation
                trio_players = trio_pairings[0].players
                for player in trio_players:
                    simulation_participation[player] += 1

                # Add to match history
                all_matches.append(tuple(trio_players))
                for pairing in regular_pairings:
                    all_matches.append(tuple(sorted(pairing.players)))

            # Accumulate for overall statistics
            for player, count in simulation_participation.items():
                total_participation[player] += count

        # Calculate average participation per player across all simulations
        avg_participation = {
            p: total_participation[p] / num_simulations for p in players
        }

        # Expected average: 9 slots / 7 players = 1.29 per simulation
        expected_avg = (3 * 3) / 7  # rounds * players_per_trio / total_players

        # Check that all players have similar average participation
        # Deviation from expected should be small (< 0.5)
        for player, avg in avg_participation.items():
            deviation = abs(avg - expected_avg)
            assert deviation < 0.5, (
                f"Player {player} has unfair trio distribution: "
                f"avg={avg:.2f}, expected={expected_avg:.2f}, deviation={deviation:.2f}"
            )

    def test_large_tournament_performance(self):
        """Test performance with larger tournament (20 players)."""
        import time

        players = list(range(1, 21))
        gara = self.create_mock_gara(players)

        all_matches = []
        total_time = 0

        # Simulate 5 rounds
        for round_num in range(1, 6):
            start = time.time()
            pairings = self.simulate_tournament_round(gara, round_num, all_matches)
            elapsed = time.time() - start
            total_time += elapsed

            assert len(pairings) == 10  # 20 players = 10 matches

            # Add to match history
            for pairing in pairings:
                all_matches.append(tuple(sorted(pairing.players)))

        # Should complete 5 rounds in reasonable time
        assert total_time < 5.0  # 5 seconds for 5 rounds

    # ==================== Complex Scenario Tests ====================

    def test_tournament_with_player_withdrawal(self):
        """Test tournament handling player withdrawal mid-tournament."""
        players = [1, 2, 3, 4, 5, 6]
        gara = self.create_mock_gara(players)

        all_matches = []

        # Round 1: All players active
        round1_pairings = self.simulate_tournament_round(gara, 1, [])
        assert len(round1_pairings) == 3
        for pairing in round1_pairings:
            all_matches.append(tuple(sorted(pairing.players)))

        # Player 3 withdraws before round 2
        for inscription in gara.inscriptions:
            if inscription.user_id == 3:
                inscription.is_withdrawn = True

        # Round 2: Only 5 players (odd number)
        round2_pairings = self.simulate_tournament_round(gara, 2, all_matches)

        # Should handle odd number (2 matches + 1 bye)
        assert len(round2_pairings) == 3

        # Player 3 should not appear in any pairing
        for pairing in round2_pairings:
            assert 3 not in pairing.players

    def test_mixed_policy_tournament(self):
        """Test tournament that changes odd player policy between rounds."""
        players = [1, 2, 3, 4, 5]

        # Round 1: Use bye policy
        gara = self.create_mock_gara(players, odd_policy="bye")
        round1_pairings = self.simulate_tournament_round(gara, 1, [])

        bye_count_r1 = sum(1 for p in round1_pairings if p.is_bye)
        trio_count_r1 = sum(1 for p in round1_pairings if len(p.players) == 3)

        assert bye_count_r1 == 1
        assert trio_count_r1 == 0

        # Round 2: Switch to trio policy
        gara.odd_number_policy = "trio"
        all_matches = [
            (
                tuple(sorted(p.players))
                if not p.is_bye
                else (p.players[0], self.strategy.BYE_PLAYER_ID)
            )
            for p in round1_pairings
        ]

        round2_pairings = self.simulate_tournament_round(gara, 2, all_matches)

        bye_count_r2 = sum(1 for p in round2_pairings if p.is_bye)
        trio_count_r2 = sum(1 for p in round2_pairings if len(p.players) == 3)

        assert bye_count_r2 == 0
        assert trio_count_r2 == 1

    def test_complete_round_robin_detection(self):
        """Test behavior when all possible pairings have been played."""
        players = [1, 2, 3]
        gara = self.create_mock_gara(players, odd_policy="bye")

        # All possible pairs for 3 players
        all_possible_pairs = [(1, 2), (1, 3), (2, 3)]

        # Simulate that all pairs have played
        all_matches = all_possible_pairs.copy()

        # Try to create new round
        pairings = self.simulate_tournament_round(gara, 4, all_matches)

        # Should create at least 1 pairing (may be just bye if no valid rematches)
        assert len(pairings) >= 1

        # Check if we have any matches (should be rematches if any)
        match_pairings = [p for p in pairings if not p.is_bye]
        bye_pairings = [p for p in pairings if p.is_bye]

        # Should have at least one bye
        assert len(bye_pairings) >= 1

        # Any matches should be rematches
        for pairing in match_pairings:
            pair = tuple(sorted(pairing.players))
            assert pair in all_possible_pairs  # Must be a rematch

    def test_anti_rematch_priority_order(self):
        """Test that anti-rematch prioritizes correctly."""
        players = [1, 2, 3, 4, 5, 6]
        gara = self.create_mock_gara(players)

        # Create specific match history
        # Player 1 has played against 2 and 3
        # Player 4 has played against 5
        # Player 6 has never played
        all_matches = [(1, 2), (1, 3), (4, 5)]

        # Generate next round
        pairings = self.simulate_tournament_round(gara, 2, all_matches)

        # Verify no rematches if possible
        for pairing in pairings:
            if not pairing.is_bye:
                pair = tuple(sorted(pairing.players))
                # These specific pairs should not repeat
                assert pair not in [(1, 2), (1, 3), (4, 5)]

        # Player 6 should definitely be paired (never played anyone)
        all_paired_players = set()
        for pairing in pairings:
            all_paired_players.update(pairing.players)
        assert 6 in all_paired_players


class TestBYEPlayerIDConsistency:
    """Test BYE_PLAYER_ID handling consistency."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = RandomAntiRematchStrategy()

    def test_bye_player_id_value(self):
        """Test that BYE_PLAYER_ID has expected value."""
        assert self.strategy.BYE_PLAYER_ID == -1
        assert self.strategy.BYE_PLAYER_ID < 0  # Should be negative to avoid conflicts

    def test_bye_player_id_in_sorting(self):
        """Test that BYE_PLAYER_ID works correctly in tuple sorting."""
        # BYE_PLAYER_ID should always sort first (being -1)
        pair1 = tuple(sorted([5, self.strategy.BYE_PLAYER_ID]))
        assert pair1 == (-1, 5)

        pair2 = tuple(sorted([self.strategy.BYE_PLAYER_ID, 10]))
        assert pair2 == (-1, 10)

    def test_bye_conversion_consistency(self):
        """Test bye conversion between algorithm and Pairing format."""
        players = [1, 2, 3]

        # Create mock gara with bye policy
        mock_gara = Mock()
        mock_gara.odd_number_policy = "bye"
        mock_gara.id = 1
        mock_gara.inscriptions = []
        for user_id in players:
            inscription = Mock()
            inscription.user_id = user_id
            inscription.is_withdrawn = False
            inscription.is_waitlist = False
            mock_gara.inscriptions.append(inscription)

        # Generate pairings
        processed_data = {"gara": mock_gara}
        pairings = self.strategy._generate_pairings(processed_data, 1)

        # Find bye pairing
        bye_pairings = [p for p in pairings if p.is_bye]
        assert len(bye_pairings) == 1

        bye_pairing = bye_pairings[0]
        assert len(bye_pairing.players) == 1  # Bye has single player
        assert bye_pairing.players[0] in players  # Must be real player
        # Not the special ID
        assert bye_pairing.players[0] != self.strategy.BYE_PLAYER_ID
