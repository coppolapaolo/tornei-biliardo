"""
Competition domain business logic and services

This module contains all business logic and service layer functions for competition
management.

Author: Refactoring Phase 2 - Sprint 1
Updated: 2025-08-06 - Sprint 2 Standalone support
"""

from typing import List, Optional, Dict
from datetime import datetime
from models.base import db
from .models import Prova, Inscription


class ProvaService:
    """
    Service class for Prova-related business operations.

    Supports both tournament-based and standalone competitions.
    """

    @staticmethod
    def create_prova(
        number: int,
        name: str,
        date,
        discipline: str,
        distance: int,
        tournament_id: Optional[int] = None,
        director_id: Optional[int] = None,
        **kwargs
    ) -> Prova:
        """
        Create a new prova (tournament-based or standalone).

        Args:
            number: Competition number
            name: Competition name
            date: Competition date
            discipline: Game discipline (8-ball, 9-ball, etc.)
            distance: Number of racks to play
            tournament_id: Tournament ID (None for standalone)
            director_id: Director ID (required for standalone)
            **kwargs: Additional optional fields

        Returns:
            Created Prova instance

        Raises:
            ValueError: If neither tournament_id nor director_id provided
        """
        if tournament_id is None and director_id is None:
            raise ValueError("Either tournament_id or director_id must be provided")

        prova = Prova(
            number=number,
            name=name,
            date=date,
            discipline=discipline,
            distance=distance,
            tournament_id=tournament_id,
            director_id=director_id,
            **kwargs
        )

        db.session.add(prova)
        db.session.commit()

        return prova

    @staticmethod
    def get_director_provas(director_id: int) -> List[Prova]:
        """
        Get all provas organized by a director (standalone + tournament).

        Args:
            director_id: Director user ID

        Returns:
            List of Prova instances
        """
        # Get standalone provas
        standalone = Prova.query.filter_by(director_id=director_id).all()

        # Get tournament provas where user is director
        from models.user.models import TournamentDirector
        from sqlalchemy import select

        # Use select() to avoid SQLAlchemy warning
        tournament_ids_query = select(TournamentDirector.tournament_id).filter_by(
            user_id=director_id
        )

        tournament_provas = Prova.query.filter(
            Prova.tournament_id.in_(tournament_ids_query)
        ).all()

        return standalone + tournament_provas

    @staticmethod
    def get_available_for_inscription(user_id: int) -> List[Prova]:
        """
        Get all provas available for inscription.

        Includes both tournament and standalone competitions.

        Args:
            user_id: User ID to check inscriptions

        Returns:
            List of available Prova instances
        """
        now = datetime.utcnow()

        # Get all provas in inscription phase
        provas = Prova.query.filter(
            Prova.status == "inscription",
            Prova.inscription_start <= now,
            Prova.inscription_end >= now,
        ).all()

        # Filter out where user already inscribed
        available = []
        for prova in provas:
            if not prova.is_user_inscribed(user_id):
                available.append(prova)

        return available

    @staticmethod
    def validate_prova_data(data: Dict) -> Dict[str, str]:
        """
        Validate prova creation/update data.

        Args:
            data: Dictionary with prova data

        Returns:
            Dictionary of field -> error message (empty if valid)
        """
        errors = {}

        # Required fields
        if not data.get("name"):
            errors["name"] = "Nome richiesto"

        if not data.get("discipline"):
            errors["discipline"] = "Disciplina richiesta"

        if not data.get("distance"):
            errors["distance"] = "Distanza richiesta"
        elif data["distance"] < 1:
            errors["distance"] = "Distanza deve essere almeno 1"

        # Date validation
        if data.get("inscription_start") and data.get("inscription_end"):
            if data["inscription_start"] >= data["inscription_end"]:
                errors["inscription_end"] = "Data fine deve essere dopo data inizio"

        # Participants validation
        min_p = data.get("min_participants", 2)
        max_p = data.get("max_participants")

        if min_p < 2:
            errors["min_participants"] = "Minimo 2 partecipanti"

        if max_p and max_p < min_p:
            errors["max_participants"] = "Max deve essere >= min partecipanti"

        return errors


class InscriptionService:
    """
    Service class for Inscription-related business operations.

    This is a placeholder for future business logic extraction.
    """

    @staticmethod
    def inscribe_user(user_id: int, prova_id: int) -> Optional[Inscription]:
        """
        Inscribe a user to a prova if allowed.

        Args:
            user_id: User ID
            prova_id: Prova ID

        Returns:
            Created Inscription or None if not allowed
        """
        prova = Prova.query.get_or_404(prova_id)

        # Check if already inscribed
        if prova.is_user_inscribed(user_id):
            return None

        # Check if inscriptions open
        if prova.status != "inscription":
            return None

        # Check max participants
        if prova.max_participants:
            current_count = len(prova.inscriptions)
            if current_count >= prova.max_participants:
                return None

        inscription = Inscription(user_id=user_id, prova_id=prova_id)

        db.session.add(inscription)
        db.session.commit()

        return inscription

    @staticmethod
    def remove_inscription(user_id: int, prova_id: int) -> bool:
        """
        Remove a user inscription from a prova.

        Args:
            user_id: User ID
            prova_id: Prova ID

        Returns:
            True if removed, False if not found
        """
        inscription = Inscription.query.filter_by(
            user_id=user_id, prova_id=prova_id
        ).first()

        if inscription:
            db.session.delete(inscription)
            db.session.commit()
            return True
        return False
