"""
Module: models/playoff/services.py
Purpose: Playoff domain services for business logic
Requirements: SPECIFICHE.md - Playoff management and qualification system
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base import db
from .models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from ..transaction.manager import transactional


class PlayoffService:
    """Service for playoff management and business logic.

    This service manages the complete playoff lifecycle for the American Pool community platform:
    - Playoff configuration creation with flexible qualification criteria
    - Player qualification and notification workflows
    - Tournament creation and readiness management
    - Replacement player discovery when qualifications are declined/expired

    Transaction Management:
    All state-modifying methods use @transactional(domain="playoff") for atomic operations.
    This ensures data integrity across the complex playoff qualification workflow,
    particularly important for replacement logic and status transitions.

    Business Rules:
    - Elite playoffs: Top 6 classified players qualify for championship tier
    - Academy playoffs: Players in positions 7-12 compete in development tier
    - Minimum gara participation requirements ensure qualified engagement
    - Automatic replacement system maintains tournament viability
    - 80% confirmation threshold + no pending responses triggers tournament creation
    - Response deadlines prevent indefinite waiting periods

    Playoff Types Supported:
    - TOP_N: Fixed number from top of classification
    - ELITE_ACADEMY: Two-tier system (elite + academy divisions)
    - CONDITIONAL: Custom criteria-based qualification
    - BOTTOM_EXCLUDE: Exclude top performers, include next tier
    """

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
        """Create a new playoff configuration with qualification criteria.

        Establishes the framework for a playoff tournament linked to a campionato.
        This creates the template that defines WHO qualifies and HOW they qualify
        based on their final campionato classification and participation level.

        Transaction Boundary: Atomic configuration creation with JSON criteria validation.
        The @transactional decorator ensures rollback if JSON serialization fails or
        database constraints are violated.

        Args:
            campionato_id: Parent campionato for this playoff
            name: Display name (e.g., "Elite Playoff", "Academy Playoff")
            playoff_type: Determines qualification algorithm (TOP_N, ELITE_ACADEMY, etc.)
            max_participants: Maximum players who can qualify (tournament size limit)
            qualification_criteria: JSON-serializable dict with type-specific criteria:
                - TOP_N: {"top_positions": 6}
                - ELITE_ACADEMY: {"category": "elite", "elite_positions": 6, "academy_positions": 6}
                - CONDITIONAL: {"min_matches_won": 10, "min_point_difference": 20}
            min_garas_played: Minimum campionato participation for eligibility (None = no minimum)
            response_deadline: Player response cutoff (None = no deadline, immediate notification)

        Returns:
            PlayoffConfiguration: Configured playoff ready for qualification generation

        Business Logic:
            - Criteria stored as JSON for flexible, extensible evaluation algorithms
            - Configuration created in 'active' state with auto_generate=True by default
            - Auto-generation triggers qualification creation when campionato completes
            - Response deadline enables time-bound qualification acceptance workflow
        """

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
        """Create standard Elite and Academy playoff configurations.

        This convenience method establishes the two-tier playoff system commonly used
        in American Pool community tournaments. Creates both playoff configurations
        simultaneously for a complete competitive structure.

        Playoff Structure:
        1. Elite Playoff: Top 6 classified players compete for championship recognition
           - Targets positions 1-6 from final campionato classification
           - Represents the highest competitive tier
        2. Academy Playoff: Players in positions 7-12 compete for development recognition
           - Targets positions 7-12 from final campionato classification
           - Provides competitive opportunity for intermediate-level players

        Eligibility Requirements:
        Both playoffs require minimum 3 gare participation to ensure meaningful
        campionato engagement. This prevents "cherry-picking" behavior and ensures
        qualified players have demonstrated consistent participation.

        Returns:
            List[PlayoffConfiguration]: Both Elite and Academy configurations ready for use

        Transaction Behavior:
        Each configuration inherits @transactional behavior from create_playoff_configuration(),
        ensuring atomic creation of both playoff types.
        """
        configurations = []

        # Elite Playoff: Top 6 players from campionato classification
        # Uses ELITE_ACADEMY type with "elite" category to target positions 1-6
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

        # Academy Playoff: Next tier players (positions 7-12) from classification
        # Uses ELITE_ACADEMY type with "academy" category to target positions 7-12
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
        """Generate qualifications for all active playoff configurations.

        This method evaluates all playoff configurations associated with a completed
        campionato and generates PlayoffQualification records for eligible players
        based on their final classification and the specific criteria of each playoff.

        Workflow Integration:
        Typically called when a campionato transitions to 'completed' status,
        triggering the automatic qualification evaluation process for all configured
        playoffs (Elite, Academy, custom, etc.).

        Args:
            campionato_id: The completed campionato to evaluate for playoffs

        Returns:
            Dict[str, List[PlayoffQualification]]:
                Key = playoff configuration name (e.g., "Elite Playoff", "Academy Playoff")
                Value = list of newly created qualification records for that playoff

        Business Logic:
            - Only processes configurations with is_active=True and auto_generate=True
            - Each configuration applies its own qualification algorithm and criteria
            - Duplicate prevention: generate_qualifications() checks for existing records
            - Players are notified separately via notify_qualified_players()

        Read-Only Operation: No transaction needed as each configuration handles
        its own qualification creation with database commits.
        """
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
        """Send notifications to qualified players about their playoff invitation.

        Notifies all players who have qualified for a playoff but haven't been
        notified yet. This is typically called after qualification generation
        or when replacement players are found.

        Transaction Boundary: Atomic update of notification timestamps.
        Ensures all qualified players are marked as notified or none are.

        Args:
            configuration_id: The playoff configuration to process notifications for

        Returns:
            int: Number of players notified in this batch

        Current Implementation:
            - Marks qualifications as notified with timestamp
            - TODO: Integration with actual notification system (email, in-app)
            - Only processes PENDING qualifications that haven't been notified

        Business Logic:
            - Players have a limited time to respond to qualification notifications
            - If response_deadline passes, qualifications automatically expire
            - Replacement players are notified immediately when found
        """
        qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
            notified_at=None,
        ).all()

        # TODO: Replace with actual notification system integration
        # This should send email/in-app notifications about playoff qualification
        # Current implementation only tracks notification state for workflow
        count = 0
        for qualification in qualifications:
            qualification.notified_at = datetime.utcnow()
            count += 1

        return count

    @staticmethod
    @transactional(domain="playoff")
    def confirm_qualification(
        qualification_id: int, user_id: int
    ) -> PlayoffQualification:
        """Confirm a player's acceptance of their playoff qualification.

        When a qualified player accepts their playoff invitation, this method
        updates their qualification status and checks if the playoff is ready
        to start based on confirmation thresholds.

        Transaction Boundary: Atomic confirmation with readiness check.
        Ensures qualification state is updated and playoff readiness is evaluated
        in a single transaction to maintain consistency.

        Args:
            qualification_id: The specific qualification being confirmed
            user_id: Player confirming (security check to prevent unauthorized confirmations)

        Returns:
            PlayoffQualification: Updated qualification with CONFIRMED status

        Side Effects:
            - May auto-create PlayoffTournament if readiness threshold is met
            - Readiness threshold: 80% confirmed + no pending responses

        Raises:
            ValueError: If qualification is not in PENDING status
            404: If qualification doesn't exist or belong to user
        """
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        qualification.confirm_participation()

        # Auto-check playoff readiness: may create tournament if 80% confirmed
        PlayoffService._check_playoff_readiness(qualification.configuration_id)

        return qualification

    @staticmethod
    @transactional(domain="playoff")
    def decline_qualification(
        qualification_id: int, user_id: int
    ) -> Optional[PlayoffQualification]:
        """Decline a player's playoff qualification and trigger replacement process.

        When a qualified player declines their playoff invitation, this method
        marks their qualification as declined and immediately searches for the
        next eligible replacement player based on the original qualification criteria.

        Transaction Boundary: Atomic decline and replacement discovery.
        Ensures declined qualification is recorded and replacement (if found)
        is created in a single transaction.

        Args:
            qualification_id: The qualification being declined
            user_id: Player declining (security check)

        Returns:
            Optional[PlayoffQualification]: New qualification for replacement player,
                                          None if no eligible replacement found

        Side Effects:
            - Original qualification marked as DECLINED with timestamp
            - Replacement player (if found) is automatically notified
            - Replacement inherits qualifying position context

        Business Logic:
            - Replacement search follows original qualification criteria
            - Next eligible player in classification order becomes replacement
            - Replacement reason includes "Replacement" prefix for audit trail
        """
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        replacement = qualification.decline_participation()

        # Auto-notify replacement player if one was found
        if replacement:
            PlayoffService.notify_qualified_players(qualification.configuration_id)

        return replacement

    @staticmethod
    @transactional(domain="playoff")
    def find_replacement_player(
        configuration_id: int,
    ) -> Optional[PlayoffQualification]:
        """Find the next eligible player to replace a declined/expired qualification.

        This method maintains playoff integrity when qualified players decline or
        expire by finding the next eligible player who would have qualified under
        the original criteria. Ensures fair replacement selection based on merit.

        Transaction Boundary: Atomic replacement creation with duplicate prevention.
        Uses direct database queries to avoid SQLAlchemy relationship loading issues
        within the transactional context.

        Replacement Algorithm:
        1. Query current qualified/pending players to build exclusion set
        2. Re-evaluate original qualification criteria (evaluate_qualifications)
        3. Find first eligible player not in current qualification set
        4. Create new qualification with "Replacement" prefix for audit trail

        Args:
            configuration_id: Playoff configuration needing a replacement

        Returns:
            Optional[PlayoffQualification]: New qualification for replacement player,
                                          None if no eligible players remain

        Business Logic:
            - Maintains chronological qualification order from original evaluation
            - Prevents duplicate qualifications through user_id exclusion set
            - Replacement inherits exact qualification criteria and position context
            - Audit trail: qualification_reason prefixed with "Replacement -"

        SQLAlchemy Pattern:
        Uses direct queries instead of relationship access to ensure proper
        transaction handling and avoid InstrumentedList issues in migration.
        """
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            from flask import abort

            abort(404)

        # SQLAlchemy Migration Pattern: Direct queries avoid relationship loading issues
        # Post-migration from db.session.commit() to @transactional decorator pattern
        # Collect all current qualifications (confirmed + pending) to exclude from replacement search
        confirmed_qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.CONFIRMED.value,
        ).all()
        pending_qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, status=QualificationStatus.PENDING.value
        ).all()
        current_qualifications = confirmed_qualifications + pending_qualifications

        current_players = {q.user_id for q in current_qualifications}

        # Replacement Fairness: Re-evaluate complete qualification algorithm
        # Ensures replacement follows identical criteria and maintains merit-based selection
        # Next eligible player in original evaluation order becomes replacement
        all_qualified = configuration.evaluate_qualifications()

        for player_data in all_qualified:
            if player_data["user_id"] not in current_players:
                # Found next eligible player who hasn't been qualified yet
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
        """Expire qualifications that have passed their response deadline.

        This maintenance method processes playoff configurations with expired response
        deadlines, automatically transitioning pending qualifications to expired status
        and triggering replacement player discovery to maintain tournament viability.

        Transaction Boundary: Atomic expiration and replacement processing.
        Each configuration's expiration cycle and replacement discovery is handled
        as a single atomic operation to ensure data consistency.

        Maintenance Schedule:
        Typically called by scheduled background job or admin maintenance tasks.
        Should run regularly (daily/hourly) to ensure timely qualification processing.

        Returns:
            int: Total number of qualifications expired across all configurations

        Expiration Process:
        1. Query configurations with response_deadline <= current_time and is_active=True
        2. For each configuration, expire all PENDING qualifications
        3. For each expired qualification, trigger replacement player discovery
        4. Auto-notify replacement players to maintain workflow momentum

        Business Logic:
            - Only PENDING qualifications expire (CONFIRMED ones remain valid)
            - Expired qualifications maintain audit trail with EXPIRED status
            - Replacement discovery follows original qualification algorithm
            - Immediate notification prevents qualification chain delays
            - Ensures tournaments don't stall due to unresponsive players
        """
        expired_count = 0

        configurations = PlayoffConfiguration.query.filter(
            PlayoffConfiguration.response_deadline <= datetime.utcnow(),
            PlayoffConfiguration.is_active.is_(True),
        ).all()

        for config in configurations:
            expired_qualifications = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.PENDING
            ).all()

            for qualification in expired_qualifications:
                qualification.expire_qualification()
                expired_count += 1

                # Auto-find replacement for each expired qualification
                # Maintains tournament viability when players don't respond
                replacement = PlayoffService.find_replacement_player(config.id)
                if replacement:
                    PlayoffService.notify_qualified_players(config.id)

        return expired_count

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_campionato(configuration_id: int) -> PlayoffTournament:
        """Create the actual playoff tournament entity for a configuration.

        This method creates the PlayoffTournament record that represents the
        actual tournament event. This is separate from the configuration (which
        defines qualification rules) and represents the executable tournament.

        Transaction Boundary: Atomic tournament creation with duplicate prevention.
        Ensures only one tournament exists per configuration.

        Relationship:
        - PlayoffConfiguration: Defines "who qualifies" and "how"
        - PlayoffTournament: Represents "the actual tournament event"
        - Future integration: Links to Gara for match execution

        Args:
            configuration_id: The configuration to create a tournament for

        Returns:
            PlayoffTournament: Created tournament in 'setup' status

        Business Logic:
            - Idempotent: Returns existing tournament if already created
            - Inherits configuration details (name, location, date, fees)
            - Created in 'setup' status, ready for registration phase
            - Links to configuration for qualification validation

        TODO: Integration with Gara creation for actual match execution
        """
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            from flask import abort

            abort(404)

        # Idempotent operation: return existing tournament if already created
        # Prevents duplicate tournaments for same configuration
        if configuration.playoff_campionato is not None:
            # Direct query approach ensures proper type handling in transaction context
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
        """Start the registration phase for a playoff tournament.

        Transitions the tournament from 'setup' to 'registration' status and
        initiates the process of converting qualified players into registered
        participants for the actual tournament.

        Transaction Boundary: Atomic status transition with registration setup.

        Args:
            campionato_id: The playoff tournament to start registration for

        Returns:
            PlayoffTournament: Tournament with updated 'registration' status

        Business Logic:
            - Only valid from 'setup' status
            - Records registration start timestamp
            - Future: Auto-register confirmed qualified players
            - Future: Create linked Gara for match execution

        TODO: Complete integration with GaraService for match system
        """
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            from flask import abort

            abort(404)
        campionato.start_registration()
        return campionato

    @staticmethod
    def get_campionato_playoff_status(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive playoff status and readiness information for dashboard display.

        Provides a complete administrative view of all playoff configurations
        associated with a campionato, including real-time qualification counts,
        confirmation status, and tournament readiness indicators for decision-making.

        Read-Only Operation: No transaction needed for status aggregation queries.

        Args:
            campionato_id: The campionato to analyze playoff status for

        Returns:
            Dict containing comprehensive playoff status:
            - has_playoffs: Boolean indicating if any playoffs are configured
            - configurations: List of detailed status for each playoff configuration
            - total_qualified: Aggregate players qualified across all playoffs
            - total_confirmed: Aggregate confirmations across all playoffs
            - ready_to_start: List of playoff names meeting tournament readiness threshold

        Per-Configuration Status Details:
            - total_qualified: All qualifications (pending + confirmed + declined + expired)
            - confirmed: Players who confirmed participation (tournament-ready)
            - pending: Players who haven't responded yet (awaiting decision)
            - declined: Players who declined participation (replacement triggered)
            - has_campionato: Whether PlayoffTournament entity exists
            - campionato_status: Current tournament status if entity exists

        Tournament Readiness Evaluation:
            - Minimum 80% of max_participants confirmed (viable tournament size)
            - Zero pending responses (all players have made their decision)
            - Indicates when playoffs can transition to tournament execution phase
        """
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
                "confirmed": PlayoffQualification.query.filter_by(
                    configuration_id=config.id, status=QualificationStatus.CONFIRMED
                ).count(),
                "pending": PlayoffQualification.query.filter_by(
                    configuration_id=config.id, status=QualificationStatus.PENDING
                ).count(),
                "declined": PlayoffQualification.query.filter_by(
                    configuration_id=config.id, status=QualificationStatus.DECLINED
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

            # Tournament readiness check: 80% confirmed + no pending responses
            # This indicates sufficient participation for viable tournament
            if (
                config_status["confirmed"] >= config.max_participants * 0.8
                and config_status["pending"] == 0  # No pending responses
            ):  # Ready for tournament creation
                status["ready_to_start"].append(config.name)

        return status

    @staticmethod
    def _check_playoff_readiness(configuration_id: int) -> None:
        """Internal method to evaluate playoff readiness and auto-create tournament.

        Called automatically during qualification confirmation workflow to assess
        whether the playoff has reached sufficient participation threshold for
        tournament creation and execution.

        Private Method: Internal workflow integration, not for direct external use.

        Readiness Criteria (ALL must be met):
        - At least 80% of max_participants have confirmed participation
        - Zero pending responses (all qualified players have responded)
        - PlayoffTournament entity doesn't already exist for this configuration

        Args:
            configuration_id: The configuration to evaluate readiness for

        Side Effects:
            - May auto-create PlayoffTournament if all readiness criteria are satisfied
            - Tournament creation inherits transactional context from calling method

        Business Logic:
            - 80% threshold balances tournament viability with player flexibility
            - Zero pending requirement prevents tournament creation with uncertain participation
            - Auto-creation streamlines transition from qualification to tournament phases
            - Eliminates manual intervention need for standard tournament progression
        """
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            from flask import abort

            abort(404)

        confirmed_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, status=QualificationStatus.CONFIRMED
        ).count()

        pending_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, status=QualificationStatus.PENDING
        ).count()

        # Readiness threshold: 80% confirmed participation + no pending responses
        # This ensures viable tournament size while accounting for potential dropouts
        if (
            confirmed_count >= configuration.max_participants * 0.8
            and pending_count == 0
            and not configuration.playoff_campionato
        ):

            # Auto-create tournament entity when readiness threshold is met
            # This streamlines the playoff lifecycle from qualification to tournament
            PlayoffService.create_playoff_campionato(configuration_id)

    @staticmethod
    @transactional(domain="playoff")
    def complete_playoff_campionato(
        campionato_id: int, winner_id: Optional[int] = None
    ) -> PlayoffTournament:
        """Mark a playoff tournament as completed and record results.

        Finalizes the tournament by updating status to 'completed' and
        optionally recording the winner for community recognition and statistics.

        Transaction Boundary: Atomic completion with winner recording.
        Ensures tournament state and results are updated together.

        Args:
            campionato_id: The tournament to complete
            winner_id: Optional winner for tournament records and statistics

        Returns:
            PlayoffTournament: Completed tournament with final status

        Business Logic:
            - Sets completion timestamp for audit trail
            - Winner information feeds into player statistics and community rankings
            - Completed tournaments become part of player history
            - Status change enables cleanup and archival processes
        """
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            from flask import abort

            abort(404)
        campionato.complete_campionato(winner_id)
        return campionato

    @staticmethod
    def get_user_playoff_history(user_id: int) -> List[Dict[str, Any]]:
        """Get comprehensive playoff participation history for player profile display.

        Retrieves complete playoff qualification history for a player across all
        campionatos, providing detailed competitive record for profile enhancement
        and community recognition within the American Pool platform.

        Read-Only Operation: No transaction needed for historical data queries.

        Args:
            user_id: The player to compile playoff history for

        Returns:
            List[Dict]: Chronologically ordered playoff participation records (newest first)

        Each participation record contains:
            - campionato_name: Parent campionato name for context
            - playoff_name: Specific playoff type (Elite, Academy, custom)
            - qualifying_position: Final campionato position that earned qualification
            - status: Final qualification outcome (confirmed, declined, expired, replaced)
            - qualified_at: Timestamp when qualification was initially earned
            - responded_at: Timestamp when player responded (None if no response)

        Business Value:
            - Player profile enhancement: Showcase competitive achievements
            - Community recognition: Highlight playoff participation and success
            - Engagement analytics: Track player involvement in competitive events
            - Tournament design insights: Understand participation patterns for directors
            - Social proof: Demonstrate player competitiveness within community
        """
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

        # Return most recent qualifications first for better user experience
        return sorted(history, key=lambda x: x["qualified_at"], reverse=True)
