"""
Competition domain business logic and services

This module contains all business logic and service layer functions for competition
management.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from typing import List
from models.base import db
from .models import Prova, Inscription


class ProvaService:
    """
    Service class for Prova-related business operations.

    This is a placeholder for future business logic extraction.
    """

    @staticmethod
    def create_prova(tournament_id: int, number: int, **kwargs) -> Prova:
        """Create a new prova for a tournament."""
        prova = Prova(tournament_id=tournament_id, number=number, **kwargs)
        db.session.add(prova)
        db.session.commit()
        return prova

    @staticmethod
    def get_available_for_inscription(user_id: int) -> List[Prova]:
        """Get all provas available for inscription for a user."""
        # Placeholder - actual implementation would filter properly
        return Prova.query.filter_by(status="inscription").all()


class InscriptionService:
    """
    Service class for Inscription-related business operations.
    """

    @staticmethod
    def inscribe_user(user_id: int, prova_id: int) -> Inscription:
        """Inscribe a user to a prova."""
        inscription = Inscription(user_id=user_id, prova_id=prova_id)
        db.session.add(inscription)
        db.session.commit()
        return inscription

    @staticmethod
    def remove_inscription(user_id: int, prova_id: int) -> bool:
        """Remove a user inscription from a prova."""
        inscription = Inscription.query.filter_by(
            user_id=user_id, prova_id=prova_id
        ).first()
        if inscription:
            db.session.delete(inscription)
            db.session.commit()
            return True
        return False


__all__ = ["ProvaService", "InscriptionService"]
