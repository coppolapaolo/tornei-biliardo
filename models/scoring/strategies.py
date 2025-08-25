# models/scoring/strategies.py
"""Concrete implementations of scoring policies."""

from typing import List, Tuple, Any
from models.scoring.policies import ScoringPolicy
from models.user.models import User


class ClassicScoringPolicy(ScoringPolicy):
    """Classic Amalfi scoring policy.

    Ranking criteria:
    1. Number of wins (descending)
    2. Rack difference (descending)
    3. Previous order (ascending)
    """

    def calculate_standings(
        self, players: List[User], match_results: List[dict]
    ) -> List[Tuple[User, Any]]:
        """Calculate standings using classic Amalfi criteria."""
        # Initialize player statistics
        player_stats = {}
        for player in players:
            player_stats[player.id] = {
                "player": player,
                "wins": 0,
                "rack_diff": 0,
                "previous_order": players.index(player),  # For tie-breaking
            }

        # Process match results
        for result in match_results:
            player1_id = result["player1_id"]
            player2_id = result["player2_id"]
            player1_score = result["player1_score"]
            player2_score = result["player2_score"]

            # Update wins
            if player1_score > player2_score:
                player_stats[player1_id]["wins"] += 1
            elif player2_score > player1_score:
                player_stats[player2_id]["wins"] += 1

            # Update rack differences
            player_stats[player1_id]["rack_diff"] += player1_score - player2_score
            player_stats[player2_id]["rack_diff"] += player2_score - player1_score

        # Sort by ranking criteria
        sorted_players = sorted(
            player_stats.values(),
            key=lambda x: (-x["wins"], -x["rack_diff"], x["previous_order"]),
        )

        # Return as list of tuples (player, score_data)
        return [(item["player"], item) for item in sorted_players]

    def get_ranking_criteria(self) -> List[str]:
        """Get the ranking criteria for this policy."""
        return ["wins", "rack_difference", "previous_order"]


class FargoRatingScoringPolicy(ScoringPolicy):
    """Scoring policy based on Fargo rating system."""

    def calculate_standings(
        self, players: List[User], match_results: List[dict]
    ) -> List[Tuple[User, Any]]:
        """Calculate standings using Fargo rating system."""
        # This would integrate with the rating system
        # For now, we'll use a simplified version
        player_stats = {}
        for player in players:
            # Get player's Fargo rating
            fargo_rating = getattr(player, "fargo_rating", 0)
            player_stats[player.id] = {
                "player": player,
                "rating": fargo_rating,
                "wins": 0,
                "rack_diff": 0,
            }

        # Process match results
        for result in match_results:
            player1_id = result["player1_id"]
            player2_id = result["player2_id"]
            player1_score = result["player1_score"]
            player2_score = result["player2_score"]

            # Update wins
            if player1_score > player2_score:
                player_stats[player1_id]["wins"] += 1
            elif player2_score > player1_score:
                player_stats[player2_id]["wins"] += 1

            # Update rack differences
            player_stats[player1_id]["rack_diff"] += player1_score - player2_score
            player_stats[player2_id]["rack_diff"] += player2_score - player1_score

        # Sort by rating, then wins, then rack difference
        sorted_players = sorted(
            player_stats.values(),
            key=lambda x: (-x["rating"], -x["wins"], -x["rack_diff"]),
        )

        return [(item["player"], item) for item in sorted_players]

    def get_ranking_criteria(self) -> List[str]:
        """Get the ranking criteria for this policy."""
        return ["fargo_rating", "wins", "rack_difference"]


class EloRatingScoringPolicy(ScoringPolicy):
    """Scoring policy based on Elo rating system."""

    def calculate_standings(
        self, players: List[User], match_results: List[dict]
    ) -> List[Tuple[User, Any]]:
        """Calculate standings using Elo rating system."""
        # This would integrate with the rating system
        # For now, we'll use a simplified version
        player_stats = {}
        for player in players:
            # Get player's Elo rating
            elo_rating = getattr(player, "elo_rating", 0)
            player_stats[player.id] = {
                "player": player,
                "rating": elo_rating,
                "wins": 0,
                "rack_diff": 0,
            }

        # Process match results
        for result in match_results:
            player1_id = result["player1_id"]
            player2_id = result["player2_id"]
            player1_score = result["player1_score"]
            player2_score = result["player2_score"]

            # Update wins
            if player1_score > player2_score:
                player_stats[player1_id]["wins"] += 1
            elif player2_score > player1_score:
                player_stats[player2_id]["wins"] += 1

            # Update rack differences
            player_stats[player1_id]["rack_diff"] += player1_score - player2_score
            player_stats[player2_id]["rack_diff"] += player2_score - player1_score

        # Sort by rating, then wins, then rack difference
        sorted_players = sorted(
            player_stats.values(),
            key=lambda x: (-x["rating"], -x["wins"], -x["rack_diff"]),
        )

        return [(item["player"], item) for item in sorted_players]

    def get_ranking_criteria(self) -> List[str]:
        """Get the ranking criteria for this policy."""
        return ["elo_rating", "wins", "rack_difference"]
