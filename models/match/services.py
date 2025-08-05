"""
Match domain business logic and services

This module contains all business logic and service layer functions for match
management.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from typing import List, Optional
from models.base import db
from .models import Match, Rack, MatchResult, TrioMatch


class MatchService:
    """
    Service class for match-related business operations.

    This is a placeholder for future business logic extraction.
    Current implementation keeps business logic in the model for backward compatibility.
    """

    @staticmethod
    def create_match(
        prova_id: int,
        round_number: int,
        player1_id: int,
        player2_id: Optional[int] = None,
        is_bye: bool = False,
    ) -> Match:
        """
        Create a new match.

        Args:
            prova_id: ID of the prova
            round_number: Round number (1, 2, 3, etc.)
            player1_id: ID of first player
            player2_id: ID of second player (optional for bye)
            is_bye: Whether this is a bye match

        Returns:
            Match: Created match instance
        """
        match = Match(
            prova_id=prova_id,
            round_number=round_number,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=is_bye,
        )
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def get_matches_by_prova(
        prova_id: int, round_number: Optional[int] = None
    ) -> List[Match]:
        """Get all matches for a prova, optionally filtered by round."""
        query = Match.query.filter_by(prova_id=prova_id)
        if round_number is not None:
            query = query.filter_by(round_number=round_number)
        return query.order_by(Match.round_number, Match.id).all()


class RackService:
    """
    Service class for rack-related business operations.
    """

    @staticmethod
    def add_rack_result(match_id: int, winner_id: int, reported_by_id: int) -> Rack:
        """Add a rack result to a match."""
        # Find next rack number
        last_rack = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

        rack = Rack(
            match_id=match_id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
        )
        db.session.add(rack)

        # Update match scores
        match = db.session.get(Match, match_id)
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

        db.session.commit()
        return rack


class MatchResultService:
    """
    Service class for match result submission and validation.
    """

    @staticmethod
    def submit_result(
        match_id: int,
        user_id: int,
        player1_score: int,
        player2_score: int,
        winner_id: int,
    ) -> MatchResult:
        """Submit a match result."""
        result = MatchResult(
            match_id=match_id,
            user_id=user_id,
            player1_score=player1_score,
            player2_score=player2_score,
            winner_id=winner_id,
        )
        db.session.add(result)
        db.session.commit()
        return result


class TrioMatchService:
    """
    Service class for trio match operations.
    """

    @staticmethod
    def create_trio_match(
        match_id: int, player1_id: int, player2_id: int, player3_id: int
    ) -> TrioMatch:
        """Create a trio match."""
        trio = TrioMatch(
            match_id=match_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player3_id=player3_id,
            current_player1_id=player1_id,
            current_player2_id=player2_id,
            waiting_player_id=player3_id,
        )
        db.session.add(trio)

        # Update match to mark as trio
        match = db.session.get(Match, match_id)
        match.is_trio = True

        db.session.commit()
        return trio


# Placeholder for future service expansion
__all__ = ["MatchService", "RackService", "MatchResultService", "TrioMatchService"]
