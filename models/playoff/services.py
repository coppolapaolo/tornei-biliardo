"""
Module: models/playoff/services.py
Purpose: Playoff domain services for business logic
Requirements: SPECIFICHE.md - Playoff management and qualification system
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import db, utc_now
from .models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from ..transaction.manager import transactional


class PlayoffService:
    """Service for playoff management and business logic."""

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_configuration(
        campionato_id: int,
        name: str,
        playoff_type: PlayoffType,
        max_participants: int,
        qualification_criteria: Dict[str, Any],
        description: Optional[str] = None,
        min_garas_played: Optional[int] = None,
        location: Optional[str] = None,
        scheduled_date: Optional[datetime] = None,
        entry_fee: Optional[float] = None,
        response_deadline: Optional[datetime] = None,
    ) -> PlayoffConfiguration:
        """Create a new playoff configuration."""

        configuration = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=playoff_type,
            max_participants=max_participants,
            description=description,
            min_garas_played=min_garas_played,
            location=location,
            scheduled_date=scheduled_date,
            entry_fee=entry_fee,
            response_deadline=response_deadline,
        )

        configuration.set_qualification_criteria(qualification_criteria)

        db.session.add(configuration)
        return configuration

    @staticmethod
    def create_standard_playoff_configurations(
        campionato_id: int,
    ) -> List[PlayoffConfiguration]:
        """Create standard playoff configurations for a campionato."""
        configurations = []

        # Elite Playoff (Top 6)
        elite_config = PlayoffService.create_playoff_configuration(
            campionato_id=campionato_id,
            name="Elite Playoff",
            playoff_type=PlayoffType.ELITE_ACADEMY,
            max_participants=6,
            qualification_criteria={
                "category": "elite",
                "elite_positions": 6,
                "academy_positions": 6,
            },
            description="Playoff for top 6 classified players",
            min_garas_played=3,
        )
        configurations.append(elite_config)

        # Academy Playoff (Positions 7-12)
        academy_config = PlayoffService.create_playoff_configuration(
            campionato_id=campionato_id,
            name="Academy Playoff",
            playoff_type=PlayoffType.ELITE_ACADEMY,
            max_participants=6,
            qualification_criteria={
                "category": "academy",
                "elite_positions": 6,
                "academy_positions": 6,
            },
            description="Playoff for players in positions 7-12",
            min_garas_played=3,
        )
        configurations.append(academy_config)

        return configurations

    @staticmethod
    def generate_all_qualifications(
        campionato_id: int,
    ) -> Dict[str, List[PlayoffQualification]]:
        """Generate qualifications for all playoff configurations of a campionato."""
        configurations = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True, auto_generate=True
        ).all()

        results = {}
        for config in configurations:
            qualifications = config.generate_qualifications()
            results[config.name] = qualifications

        return results

    @staticmethod
    @transactional(domain="playoff")
    def notify_qualified_players(configuration_id: int) -> int:
        """Send notifications to qualified players."""
        qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
            notified_at=None,
        ).all()

        # In a real implementation, this would send actual notifications
        # For now, just mark as notified
        count = 0
        for qualification in qualifications:
            qualification.notified_at = utc_now()
            count += 1

        return count

    @staticmethod
    @transactional(domain="playoff")
    def confirm_qualification(
        qualification_id: int, user_id: int
    ) -> PlayoffQualification:
        """Confirm a user's playoff qualification."""
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        qualification.confirm_participation()

        # Check if we can start the playoff campionato
        PlayoffService._check_playoff_readiness(qualification.configuration_id)

        return qualification

    @staticmethod
    @transactional(domain="playoff")
    def decline_qualification(
        qualification_id: int, user_id: int
    ) -> Optional[PlayoffQualification]:
        """Decline a user's playoff qualification and find replacement."""
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        replacement = qualification.decline_participation()

        # Notify replacement if found
        if replacement:
            PlayoffService.notify_qualified_players(qualification.configuration_id)

        return replacement

    @staticmethod
    @transactional(domain="playoff")
    def find_replacement_player(
        configuration_id: int,
    ) -> Optional[PlayoffQualification]:
        """Find the next eligible player for playoff replacement."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise ValueError("Configurazione playoff non trovata")

        # Get current qualified/confirmed players by querying directly instead of using relationship
        confirmed_qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.CONFIRMED.value,
        ).all()
        pending_qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, status=QualificationStatus.PENDING.value
        ).all()
        current_qualifications = confirmed_qualifications + pending_qualifications

        current_players = {q.user_id for q in current_qualifications}

        # Re-evaluate qualifications to find next eligible
        all_qualified = configuration.evaluate_qualifications()

        for player_data in all_qualified:
            if player_data["user_id"] not in current_players:
                # Found a replacement
                replacement = PlayoffQualification(
                    configuration_id=configuration_id,
                    user_id=player_data["user_id"],
                    qualifying_position=player_data["position"],
                    qualification_reason=f"Replacement - {player_data['qualification_reason']}",
                )
                db.session.add(replacement)
                return replacement

        return None

    @staticmethod
    @transactional(domain="playoff")
    def expire_old_qualifications() -> int:
        """Expire qualifications that have passed their deadline."""
        expired_count = 0

        configurations = PlayoffConfiguration.query.filter(
            PlayoffConfiguration.response_deadline <= utc_now(),
            PlayoffConfiguration.is_active.is_(True),
        ).all()

        for config in configurations:
            expired_qualifications = config.qualifications.filter_by(
                status=QualificationStatus.PENDING
            ).all()

            for qualification in expired_qualifications:
                qualification.expire_qualification()
                expired_count += 1

                # Find replacement
                replacement = PlayoffService.find_replacement_player(config.id)
                if replacement:
                    PlayoffService.notify_qualified_players(config.id)

        return expired_count

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_campionato(configuration_id: int) -> PlayoffTournament:
        """Create the actual playoff campionato."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise ValueError("Configurazione playoff non trovata")

        # Check if campionato already exists
        if configuration.playoff_campionato is not None:
            # Explicitly query for the playoff campionato to avoid type issues
            playoff_campionato = PlayoffTournament.query.filter_by(
                configuration_id=configuration_id
            ).first()
            if playoff_campionato:
                return playoff_campionato

        campionato = PlayoffTournament(
            configuration_id=configuration_id,
            name=configuration.name,
            campionato_date=configuration.scheduled_date,
            location=configuration.location,
            entry_fee=configuration.entry_fee,
            max_participants=configuration.max_participants,
        )

        db.session.add(campionato)

        return campionato

    @staticmethod
    @transactional(domain="playoff")
    def start_playoff_registration(campionato_id: int) -> PlayoffTournament:
        """Start registration for a playoff campionato."""
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            raise ValueError("Campionato playoff non trovato")
        campionato.start_registration()

        return campionato

    @staticmethod
    def get_campionato_playoff_status(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive playoff status for a campionato."""
        configurations = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()

        status = {
            "has_playoffs": len(configurations) > 0,
            "configurations": [],
            "total_qualified": 0,
            "total_confirmed": 0,
            "ready_to_start": [],
        }

        for config in configurations:
            config_status = {
                "configuration": config,
                "total_qualified": config.qualifications.count(),
                "confirmed": config.qualifications.filter_by(
                    status=QualificationStatus.CONFIRMED
                ).count(),
                "pending": config.qualifications.filter_by(
                    status=QualificationStatus.PENDING
                ).count(),
                "declined": config.qualifications.filter_by(
                    status=QualificationStatus.DECLINED
                ).count(),
                "has_campionato": config.playoff_campionato is not None,
                "campionato_status": (
                    config.playoff_campionato.status
                    if config.playoff_campionato
                    else None
                ),
            }

            status["configurations"].append(config_status)
            status["total_qualified"] += config_status["total_qualified"]
            status["total_confirmed"] += config_status["confirmed"]

            # Check if ready to start
            if (
                config_status["confirmed"] >= config.max_participants * 0.8
                and config_status["pending"] == 0  # At least 80% confirmed
            ):  # No pending responses
                status["ready_to_start"].append(config.name)

        return status

    @staticmethod
    def _check_playoff_readiness(configuration_id: int) -> None:
        """Check if playoff is ready to start and create campionato if needed."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise ValueError("Configurazione playoff non trovata")

        confirmed_count = configuration.qualifications.filter_by(
            status=QualificationStatus.CONFIRMED
        ).count()

        pending_count = configuration.qualifications.filter_by(
            status=QualificationStatus.PENDING
        ).count()

        # If we have enough confirmed players and no pending responses
        if (
            confirmed_count >= configuration.max_participants * 0.8
            and pending_count == 0
            and not configuration.playoff_campionato
        ):

            # Auto-create playoff campionato
            PlayoffService.create_playoff_campionato(configuration_id)

    @staticmethod
    @transactional(domain="playoff")
    def complete_playoff_campionato(
        campionato_id: int, winner_id: Optional[int] = None
    ) -> PlayoffTournament:
        """Complete a playoff campionato."""
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            raise ValueError("Campionato playoff non trovato")
        campionato.complete_campionato(winner_id)

        return campionato

    @staticmethod
    def get_user_playoff_history(user_id: int) -> List[Dict[str, Any]]:
        """Get user's playoff participation history."""
        qualifications = PlayoffQualification.query.filter_by(user_id=user_id).all()

        history = []
        for qualification in qualifications:
            history.append(
                {
                    "campionato_name": qualification.configuration.campionato.name,
                    "playoff_name": qualification.configuration.name,
                    "qualifying_position": qualification.qualifying_position,
                    "status": qualification.status.value,
                    "qualified_at": qualification.created_at,
                    "responded_at": qualification.responded_at,
                }
            )

        return sorted(history, key=lambda x: x["qualified_at"], reverse=True)
