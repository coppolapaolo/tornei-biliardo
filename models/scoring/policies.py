# models/scoring/policies.py
"""Scoring policy interface and implementations for tournament classifications."""

from abc import ABC, abstractmethod
from typing import List, Tuple, Any
from models.user.models import User


class ScoringPolicy(ABC):
    """Abstract base class for scoring policies.
    
    Defines the interface for calculating player standings in tournaments.
    """

    @abstractmethod
    def calculate_standings(self, players: List[User], match_results: List[dict]) -> List[Tuple[User, Any]]:
        """Calculate player standings based on match results.
        
        Args:
            players: List of players in the tournament
            match_results: List of match results with player scores
            
        Returns:
            List of tuples (player, score) sorted by ranking criteria
        """
        pass

    @abstractmethod
    def get_ranking_criteria(self) -> List[str]:
        """Get the criteria used for ranking players.
        
        Returns:
            List of ranking criteria names in order of priority
        """
        pass