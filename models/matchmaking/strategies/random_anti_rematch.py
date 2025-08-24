"""
Module: models/matchmaking/strategies/random_anti_rematch.py
Purpose: Random pairing strategy with anti-rematch logic
Requirements: SPECIFICHE.md - Random pairing with rematch prevention
"""

from __future__ import annotations

import random
from typing import Sequence, List, Tuple, Optional, Set

from .base import Pairing, ValidationResult
from ..policies import calculate_anti_rematch_constraint


class RandomAntiRematchStrategy:
    """Random pairing strategy that prevents rematches."""
    
    name = "Random Anti-Rematch"
    
    def __init__(self, max_attempts: int = 100):
        self.strategy_name = "random_anti_rematch"
        self.max_attempts = max_attempts  # Max attempts to find valid pairing
    
    def validate(self, prova: object) -> ValidationResult:
        """Validate if Random Anti-Rematch can be used for this prova."""
        try:
            # Get active inscriptions
            active_inscriptions = [i for i in prova.inscriptions if i.status == "confirmed"]
            player_count = len(active_inscriptions)
            
            if player_count < 2:
                return ValidationResult(
                    ok=False,
                    messages=("Random pairing requires at least 2 players",)
                )
            
            # Check if anti-rematch is still feasible
            if player_count > 2:
                # With more than 2 players, anti-rematch should be feasible for reasonable round counts
                max_possible_unique_matches = (player_count * (player_count - 1)) // 2
                
                if hasattr(prova, 'rounds_count') and prova.rounds_count > max_possible_unique_matches:
                    return ValidationResult(
                        ok=False,
                        messages=(f"With {player_count} players, only {max_possible_unique_matches} unique matches possible, but {prova.rounds_count} rounds planned",)
                    )
            
            return ValidationResult(ok=True)
            
        except Exception as e:
            return ValidationResult(
                ok=False,
                messages=(f"Validation error: {str(e)}",)
            )
    
    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(prova, round_number)
    
    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Propose actual pairings for the round."""
        return self._generate_round_pairings(prova, round_number)
    
    def _generate_round_pairings(self, prova: object, round_number: int) -> List[Pairing]:
        """Generate random pairings while avoiding rematches."""
        try:
            # Get active players
            active_inscriptions = [i for i in prova.inscriptions if i.status == "confirmed"]
            player_ids = [i.user_id for i in active_inscriptions]
            
            if len(player_ids) < 2:
                return []
            
            # Get previous matches to avoid rematches
            previous_pairings = self._get_previous_pairings(prova, round_number)
            
            # Generate valid random pairings
            pairings = self._generate_valid_random_pairings(
                player_ids, previous_pairings, round_number
            )
            
            return pairings
            
        except Exception as e:
            print(f"Error generating Random Anti-Rematch pairings: {e}")
            return []
    
    def _get_previous_pairings(self, prova: object, current_round: int) -> Set[Tuple[int, int]]:
        """Get all previous pairings to avoid rematches."""
        from ...match.models import Match
        
        previous_matches = Match.query.filter_by(prova_id=prova.id).filter(
            Match.round_number < current_round
        ).all()
        
        previous_pairings = set()
        
        for match in previous_matches:
            if match.player1_id and match.player2_id and not match.is_bye:
                # Store pairing in canonical form (smaller ID first)
                pair = tuple(sorted([match.player1_id, match.player2_id]))
                previous_pairings.add(pair)
        
        return previous_pairings
    
    def _generate_valid_random_pairings(
        self, 
        player_ids: List[int], 
        previous_pairings: Set[Tuple[int, int]], 
        round_number: int
    ) -> List[Pairing]:
        """Generate random pairings that don't conflict with previous matches."""
        
        best_pairings = []
        best_rematch_count = float('inf')
        
        # Try multiple random arrangements to find the best one
        for attempt in range(self.max_attempts):
            pairings = self._attempt_random_pairing(
                player_ids.copy(), previous_pairings, round_number
            )
            
            # Count rematches in this arrangement
            rematch_count = self._count_rematches(pairings, previous_pairings)
            
            if rematch_count == 0:
                # Found perfect solution with no rematches
                return pairings
            elif rematch_count < best_rematch_count:
                # Better solution found
                best_pairings = pairings
                best_rematch_count = rematch_count
        
        # Return best solution found
        return best_pairings
    
    def _attempt_random_pairing(
        self, 
        player_ids: List[int], 
        previous_pairings: Set[Tuple[int, int]], 
        round_number: int
    ) -> List[Pairing]:
        """Attempt one random pairing arrangement."""
        
        # Shuffle players randomly
        random.shuffle(player_ids)
        
        pairings = []
        remaining_players = player_ids.copy()
        
        # Handle trio if odd number and trio is allowed
        if len(remaining_players) % 2 == 1 and self._should_use_trio(remaining_players):
            trio_players = remaining_players[:3]
            remaining_players = remaining_players[3:]
            pairings.append(Pairing(players=tuple(trio_players), round_number=round_number))
        
        # Pair remaining players
        while len(remaining_players) >= 2:
            player1 = remaining_players.pop(0)
            player2 = self._find_best_partner(
                player1, remaining_players, previous_pairings
            )
            
            if player2:
                remaining_players.remove(player2)
                pairings.append(Pairing(players=(player1, player2), round_number=round_number))
            else:
                # No valid partner found, pair with next available
                player2 = remaining_players.pop(0)
                pairings.append(Pairing(players=(player1, player2), round_number=round_number))
        
        # Handle remaining single player (bye)
        if remaining_players:
            pairings.append(Pairing(players=(remaining_players[0],), is_bye=True, round_number=round_number))
        
        return pairings
    
    def _find_best_partner(
        self, 
        player_id: int, 
        available_players: List[int], 
        previous_pairings: Set[Tuple[int, int]]
    ) -> Optional[int]:
        """Find best partner for a player, preferring those without previous matches."""
        
        # Prefer players we haven't played against
        for candidate in available_players:
            pair = tuple(sorted([player_id, candidate]))
            if pair not in previous_pairings:
                return candidate
        
        # If all candidates are rematches, return the first one
        return available_players[0] if available_players else None
    
    def _count_rematches(
        self, 
        pairings: List[Pairing], 
        previous_pairings: Set[Tuple[int, int]]
    ) -> int:
        """Count number of rematches in the proposed pairings."""
        rematch_count = 0
        
        for pairing in pairings:
            if len(pairing.players) == 2 and not pairing.is_bye:
                pair = tuple(sorted(pairing.players))
                if pair in previous_pairings:
                    rematch_count += 1
        
        return rematch_count
    
    def _should_use_trio(self, player_ids: List[int]) -> bool:
        """Determine if trio should be used for odd number of players."""
        # Use trio if we have 3, 5, or 7 players (as per specifications)
        # For larger odd numbers, use bye instead
        return len(player_ids) in [3, 5, 7]
    
    def can_generate_all_rounds(self, prova: object) -> bool:
        """Check if all rounds can be generated without rematches."""
        active_inscriptions = [i for i in prova.inscriptions if i.status == "confirmed"]
        player_count = len(active_inscriptions)
        
        if player_count < 2:
            return False
        
        # Calculate maximum unique pairings possible
        max_unique_pairings = (player_count * (player_count - 1)) // 2
        
        # Each round uses roughly player_count/2 pairings
        pairings_per_round = player_count // 2
        max_rounds_without_rematch = max_unique_pairings // pairings_per_round
        
        rounds_count = getattr(prova, 'rounds_count', 1)
        return rounds_count <= max_rounds_without_rematch
    
    def get_rematch_probability(self, prova: object, round_number: int) -> float:
        """Calculate probability of rematches in the given round."""
        active_inscriptions = [i for i in prova.inscriptions if i.status == "confirmed"]
        player_count = len(active_inscriptions)
        
        if player_count < 2:
            return 0.0
        
        # Calculate used pairings so far
        total_possible_pairings = (player_count * (player_count - 1)) // 2
        pairings_per_round = player_count // 2
        used_pairings = (round_number - 1) * pairings_per_round
        
        if used_pairings >= total_possible_pairings:
            return 1.0  # Guaranteed rematches
        
        # Simple approximation
        remaining_pairings = total_possible_pairings - used_pairings
        return max(0.0, 1.0 - (remaining_pairings / pairings_per_round))


class RandomAntiRematchPairingStrategy(RandomAntiRematchStrategy):
    """Alias for compatibility with existing strategy registry."""
    pass