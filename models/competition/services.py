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
        Handles both string (from HTML forms) and native types.

        Args:
            data: Dictionary with prova data (can contain strings or native types)

        Returns:
            Dictionary of field -> error message (empty if valid)
        """
        from datetime import datetime

        errors = {}

        # Helper function to clean string input
        def clean_string(value):
            """Clean string input, return None if empty after strip"""
            if value is None:
                return None
            if isinstance(value, str):
                cleaned = value.strip()
                return cleaned if cleaned else None
            return value

        # Required fields with string cleaning
        name = clean_string(data.get("name"))
        if not name:
            errors["name"] = "Nome richiesto"

        discipline = clean_string(data.get("discipline"))
        if not discipline:
            errors["discipline"] = "Disciplina richiesta"

        # Distance validation with type coercion
        distance_raw = data.get("distance")
        if not distance_raw and distance_raw != 0:  # Allow 0 to be validated
            errors["distance"] = "Distanza richiesta"
        else:
            try:
                # Handle both string and int inputs
                distance = (
                    int(distance_raw) if isinstance(distance_raw, str) else distance_raw
                )
                if distance < 1:
                    errors["distance"] = "Distanza deve essere almeno 1"
            except (ValueError, TypeError):
                errors["distance"] = "Distanza deve essere un numero valido"

        # Date validation for inscription dates if present
        if data.get("inscription_start") and data.get("inscription_end"):
            try:
                start = data["inscription_start"]
                end = data["inscription_end"]

                # Convert strings to dates if necessary
                if isinstance(start, str):
                    start = datetime.strptime(start, "%Y-%m-%d").date()
                if isinstance(end, str):
                    end = datetime.strptime(end, "%Y-%m-%d").date()

                if start >= end:
                    errors["inscription_end"] = "Data fine deve essere dopo data inizio"
            except (ValueError, TypeError):
                errors["inscription_end"] = "Formato date non valido"

        # Participants validation with type coercion
        min_p_raw = data.get("min_participants", 2)
        max_p_raw = data.get("max_participants")

        # Validate min_participants
        try:
            # Handle both string and int, with default of 2
            if min_p_raw is not None:
                min_p = int(min_p_raw) if isinstance(min_p_raw, str) else min_p_raw
                if min_p < 2:
                    errors["min_participants"] = "Minimo 2 partecipanti"
            else:
                min_p = 2  # Default value
        except (ValueError, TypeError):
            errors["min_participants"] = "Numero partecipanti non valido"
            min_p = None

        # Validate max_participants if present
        if max_p_raw:
            try:
                max_p = int(max_p_raw) if isinstance(max_p_raw, str) else max_p_raw
                if max_p < 1:
                    errors["max_participants"] = "Max partecipanti deve essere almeno 1"
                elif min_p and max_p < min_p:
                    errors["max_participants"] = "Max deve essere >= min partecipanti"
            except (ValueError, TypeError):
                errors["max_participants"] = "Numero partecipanti non valido"

        # Optional fields validation
        # Rounds count
        rounds_raw = data.get("rounds_count")
        if rounds_raw:
            try:
                rounds = int(rounds_raw) if isinstance(rounds_raw, str) else rounds_raw
                if rounds < 1:
                    errors["rounds_count"] = "Numero round deve essere almeno 1"
            except (ValueError, TypeError):
                errors["rounds_count"] = "Numero round non valido"

        # Entry fee
        fee_raw = data.get("entry_fee")
        if fee_raw:
            try:
                fee = float(fee_raw) if isinstance(fee_raw, str) else fee_raw
                if fee < 0:
                    errors["entry_fee"] = "La quota non può essere negativa"
            except (ValueError, TypeError):
                errors["entry_fee"] = "Quota deve essere un numero valido"

        # Number field (for prova number)
        number_raw = data.get("number")
        if number_raw:
            try:
                number = int(number_raw) if isinstance(number_raw, str) else number_raw
                if number < 1:
                    errors["number"] = "Numero prova deve essere almeno 1"
            except (ValueError, TypeError):
                errors["number"] = "Numero prova non valido"

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
