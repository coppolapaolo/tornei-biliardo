"""
Tournament domain business logic and services

This module contains all business logic and service layer functions for tournament
management.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from typing import List
from models.base import db
from .models import Tournament


class TournamentService:
    """
    Service class for tournament-related business operations.

    This is a placeholder for future business logic extraction.
    Current implementation keeps business logic in the model for backward compatibility.
    """

    @staticmethod
    def create_tournament(name: str, **kwargs) -> Tournament:
        """
        Create a new tournament.

        Args:
            name: Tournament name
            **kwargs: Additional tournament configuration

        Returns:
            Tournament: Created tournament instance
        """
        tournament = Tournament(name=name, **kwargs)
        db.session.add(tournament)
        db.session.commit()
        return tournament

    @staticmethod
    def get_active_tournaments() -> List[Tournament]:
        """Get all active tournaments."""
        return Tournament.query.filter_by(is_active=True).all()


# Placeholder for future service expansion
__all__ = ["TournamentService"]
