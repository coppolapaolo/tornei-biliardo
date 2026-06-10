"""
Module: models/playoff/services.py
Purpose: Playoff domain services for business logic
Requirements: SPECIFICHE.md - Playoff management and qualification system
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import db, utc_now
from ..exceptions import NotFoundError
from .models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from ..transaction.manager import transactional

logger = logging.getLogger(__name__)


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
        """Send notifications to qualified players non ancora invitati.

        Usa invited_at (campo attivo) come marcatore: notified_at e' deprecato
        e non viene mai popolato dal flusso di invito (start_playoff /
        _send_playoff_invitations usano invited_at). Filtrando su notified_at
        questo metodo ri-processava TUTTI i pending — anche i gia' invitati —
        ad ogni chiamata (es. dopo un decline+replacement).
        """
        qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
            invited_at=None,
        ).all()

        # In a real implementation, this would send actual notifications.
        # For now, just mark as invited.
        count = 0
        for qualification in qualifications:
            qualification.invited_at = utc_now()
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
            raise NotFoundError("Configurazione playoff non trovata")

        # Get current qualified/confirmed players (querying directly,
        # not via relationship)
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
                    qualification_reason=(
                        f"Replacement - {player_data['qualification_reason']}"
                    ),
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
            expired_qualifications = PlayoffQualification.query.filter_by(
                configuration_id=config.id,
                status=QualificationStatus.PENDING,
            ).all()

            for qualification in expired_qualifications:
                qualification.expire_qualification()
                expired_count += 1

                # Find replacement and notify
                replacement = PlayoffService.find_replacement_player(config.id)
                if replacement:
                    replacement.invited_at = utc_now()
                    replacement.expires_at = config.response_deadline
                    PlayoffService._send_playoff_invitations(config, [replacement])

        return expired_count

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_campionato(configuration_id: int) -> PlayoffTournament:
        """Create the actual playoff campionato."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise NotFoundError("Configurazione playoff non trovata")

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
            raise NotFoundError("Campionato playoff non trovato")
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
            total_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id
            ).count()
            confirmed_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.CONFIRMED
            ).count()
            pending_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.PENDING
            ).count()
            declined_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.DECLINED
            ).count()
            config_status = {
                "configuration": config,
                "total_qualified": total_q,
                "confirmed": confirmed_q,
                "pending": pending_q,
                "declined": declined_q,
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
            raise NotFoundError("Configurazione playoff non trovata")

        confirmed_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.CONFIRMED,
        ).count()

        pending_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
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
            raise NotFoundError("Campionato playoff non trovato")
        campionato.complete_campionato(winner_id)

        return campionato

    # ── Config management (pre-avvio) ──────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def update_configuration(config_id: int, **fields: Any) -> PlayoffConfiguration:
        """Update a playoff configuration. Blocked if qualifications exist."""
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if config.has_qualifications():
            raise ValueError("Non modificabile dopo avvio playoff")

        allowed = {
            "name",
            "positions_from",
            "positions_to",
            "max_participants",
            "min_garas_played",
            "location",
            "scheduled_date",
            "entry_fee",
            "response_deadline",
            "discipline",
            "distance",
            "rounds_count",
            "strategy_type",
            "odd_number_policy",
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(config, key, value)

        return config

    @staticmethod
    @transactional(domain="playoff")
    def add_configuration(
        campionato_id: int,
        name: str,
        positions_from: int,
        positions_to: int,
        max_participants: int,
        min_garas_played: Optional[int] = None,
        **kwargs: Any,
    ) -> PlayoffConfiguration:
        """Add a new playoff configuration.

        Blocked if any config already has qualifications.
        """
        existing_configs = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()
        for c in existing_configs:
            if c.has_qualifications():
                raise ValueError("Non modificabile dopo avvio playoff")

        config = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=PlayoffType.TOP_N,
            max_participants=max_participants,
            min_garas_played=min_garas_played,
            positions_from=positions_from,
            positions_to=positions_to,
        )
        # Optional gara params
        for key in (
            "discipline",
            "distance",
            "rounds_count",
            "strategy_type",
            "odd_number_policy",
            "location",
            "scheduled_date",
            "entry_fee",
        ):
            if key in kwargs:
                setattr(config, key, kwargs[key])

        db.session.add(config)
        return config

    @staticmethod
    @transactional(domain="playoff")
    def deactivate_configuration(config_id: int) -> PlayoffConfiguration:
        """Deactivate a playoff configuration. Blocked if qualifications exist."""
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if config.has_qualifications():
            raise ValueError("Non modificabile dopo avvio playoff")

        config.is_active = False
        return config

    # ── Avvio playoff ────────────────────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def start_playoff(
        campionato_id: int,
    ) -> Dict[str, List[PlayoffQualification]]:
        """Start playoffs: generate qualifications from classification.

        Iterates over all active configs of the campionato. Sets
        response_deadline (default 7 days) and sends notifications.
        Returns dict of config_name → list of new qualifications.
        """
        from ..campionato.models import Campionato
        from ..status_enum import TournamentStatus
        from ..classification.models import Classification

        campionato = db.session.get(Campionato, campionato_id)
        if campionato is None:
            raise NotFoundError("Campionato non trovato")

        if campionato.get_status() != TournamentStatus.TERMINATED.value:
            raise ValueError(
                "Il campionato deve essere terminato per avviare i playoff"
            )

        configs = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()

        if not configs:
            raise ValueError("Nessuna configurazione playoff attiva")

        # Pre-flight: check ALL configs before any creation
        if any(c.has_qualifications() for c in configs):
            raise ValueError("Playoff già avviati per questo campionato")

        # Make sure Classification records are up-to-date: la UI calcola la
        # classifica on-the-fly via calculate_general_classification, ma
        # qui leggiamo dai Classification persistiti per congelare i dati.
        try:
            from ..classification.campionato_classification import (
                ClassificationService,
            )

            ClassificationService.update_campionato_classification(campionato_id)
        except Exception:
            logger.warning(
                "Impossibile aggiornare la classifica campionato %d "
                "prima di start_playoff",
                campionato_id,
            )

        # Get the frozen classification
        classifications = (
            Classification.query.filter_by(campionato_id=campionato_id)
            .order_by(Classification.position)
            .all()
        )

        results: Dict[str, List[PlayoffQualification]] = {}
        now = utc_now()

        for config in configs:
            # Set deadline if not explicitly configured
            if config.response_deadline is None:
                config.response_deadline = now + timedelta(days=7)

            qualifications: List[PlayoffQualification] = []

            if config.positions_from is not None and config.positions_to is not None:
                # Position-based qualification
                for cls in classifications:
                    if cls.position is None:
                        continue
                    if config.positions_from <= cls.position <= config.positions_to:
                        if config._meets_minimum_requirements(cls.user_id):
                            if len(qualifications) < config.max_participants:
                                qual = PlayoffQualification(
                                    configuration_id=config.id,
                                    user_id=cls.user_id,
                                    qualifying_position=cls.position,
                                    qualification_reason=(
                                        f"Posizione {cls.position} in classifica"
                                    ),
                                    invited_at=now,
                                    expires_at=config.response_deadline,
                                )
                                db.session.add(qual)
                                qualifications.append(qual)
                        else:
                            logger.info(
                                "Player %d excluded: min_garas_played not met",
                                cls.user_id,
                            )
                            # Try next in line beyond positions_to
                # If we need replacements (some excluded by min_garas)
                if len(qualifications) < config.max_participants:
                    next_pos = config.positions_to + 1
                    already_qualified = {q.user_id for q in qualifications}
                    for cls in classifications:
                        if cls.position is None or cls.position < next_pos:
                            continue
                        if cls.user_id in already_qualified:
                            continue
                        if config._meets_minimum_requirements(cls.user_id):
                            qual = PlayoffQualification(
                                configuration_id=config.id,
                                user_id=cls.user_id,
                                qualifying_position=cls.position,
                                qualification_reason=(
                                    f"Rimpiazzo — posizione {cls.position}"
                                ),
                                invited_at=now,
                                expires_at=config.response_deadline,
                            )
                            db.session.add(qual)
                            qualifications.append(qual)
                            if len(qualifications) >= config.max_participants:
                                break
            else:
                # Fallback to evaluate_qualifications (legacy JSON criteria)
                qualifications = list(config.generate_qualifications())
                for q in qualifications:
                    q.invited_at = now
                    q.expires_at = config.response_deadline

            results[config.name] = qualifications

        # Notify all qualified players via NotificationFactory
        db.session.flush()
        for config in configs:
            PlayoffService._send_playoff_invitations(
                config, results.get(config.name, [])
            )

        return results

    @staticmethod
    def _send_playoff_invitations(
        config: PlayoffConfiguration,
        qualifications: List[PlayoffQualification],
    ) -> None:
        """Send in-app notifications to qualified players.

        Una notifica PER qualifica, con deep-link alla pagina di invito
        (`/player/playoff/invitation/<id>`) dove il giocatore conferma o
        rifiuta la partecipazione (bug 15). Non si può usare una bulk
        notification: l'`action_url` deve contenere la qualification_id
        specifica di ciascun giocatore.
        """
        import logging
        from ..notification.services import NotificationService
        from ..notification.models import NotificationType, NotificationPriority

        if not qualifications:
            return

        campionato_name = config.campionato.name if config.campionato else ""

        for qual in qualifications:
            try:
                NotificationService.create_notification(
                    user_id=qual.user_id,
                    notification_type=NotificationType.PLAYOFF_INVITATION,
                    title=f"Invito Playoff — {config.name}",
                    message=(
                        f"Sei stato qualificato per {config.name} "
                        f"del campionato {campionato_name}. "
                        f"Conferma o rifiuta la partecipazione."
                    ),
                    priority=NotificationPriority.HIGH,
                    action_url=f"/player/playoff/invitation/{qual.id}",
                    action_text="Conferma o rifiuta",
                    related_entities={
                        "campionato_id": config.campionato_id,
                        "configuration_id": config.id,
                        "configuration_name": config.name,
                        "qualification_id": qual.id,
                    },
                    expires_at=getattr(qual, "expires_at", None),
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Invio invito playoff fallito per qualification %s", qual.id
                )

    # ── Creazione gara playoff ───────────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_gara(configuration_id: int):
        """Create the playoff Gara for a config and inscribe confirmed players.

        Returns the created Gara instance.
        """
        from ..competition.services import GaraService
        from ..competition.inscription_service import InscriptionService
        from datetime import date as date_type, time as time_type

        config = db.session.get(PlayoffConfiguration, configuration_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Already has gara?
        if config.gara is not None:
            return config.gara

        # Get gara params (explicit or inherited from campionato)
        params = config.get_gara_params()

        # Determine date — always use today or later to avoid past-date rejection
        gara_date: Any
        gara_time: Any
        if config.scheduled_date:
            sched = config.scheduled_date
            is_dt = isinstance(sched, datetime)
            candidate = sched.date() if is_dt else sched
            gara_date = max(candidate, date_type.today())
            gara_time = sched.time() if is_dt else time_type(20, 0)
        else:
            gara_date = date_type.today()
            gara_time = time_type(20, 0)

        # Next gara number: after all existing gare in campionato
        from ..competition.models import Gara as GaraModel

        max_number = (
            db.session.query(db.func.max(GaraModel.number))
            .filter_by(campionato_id=config.campionato_id)
            .scalar()
        ) or 0

        gara = GaraService.create_gara(
            number=max_number + 1,
            name=config.name,
            date=gara_date,
            discipline=params["discipline"],
            distance=params["distance"],
            campionato_id=config.campionato_id,
            time=gara_time,
            rounds_count=params.get("rounds_count", 1),
            max_participants=config.max_participants,
            playoff_config_id=config.id,
            **{
                k: v
                for k, v in params.items()
                if v is not None
                and k
                in (
                    "location",
                    "entry_fee",
                    "matchmaking_strategy",
                    "odd_number_policy",
                )
            },
        )

        # Inscribe all confirmed players
        confirmed = (
            PlayoffQualification.query.filter_by(
                configuration_id=configuration_id,
                status=QualificationStatus.CONFIRMED,
            )
            .order_by(PlayoffQualification.qualifying_position)
            .all()
        )

        for qual in confirmed:
            InscriptionService.inscribe_user(
                user_id=qual.user_id,
                gara_id=gara.id,
                _bypass_playoff_check=True,
            )

        # Update PlayoffTournament if exists, or create one
        tournament = PlayoffTournament.query.filter_by(
            configuration_id=configuration_id
        ).first()
        if not tournament:
            tournament = PlayoffTournament(
                configuration_id=configuration_id,
                name=config.name,
                campionato_date=config.scheduled_date,
                location=config.location,
                entry_fee=config.entry_fee,
                max_participants=config.max_participants,
            )
            db.session.add(tournament)

        tournament.gara_id = gara.id
        tournament.status = "registration"
        tournament.registration_start = utc_now()
        tournament.confirmed_participants = len(confirmed)

        return gara

    # ── Admin player management ──────────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def admin_add_player(
        configuration_id: int, user_id: int, admin_username: str
    ) -> PlayoffQualification:
        """Manually add a player to a playoff config.

        Admin override — bypasses position and min_garas checks.
        """
        from ..competition.models import Inscription, Gara

        config = db.session.get(PlayoffConfiguration, configuration_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Block if gara already created
        if config.gara is not None:
            raise ValueError("Non modificabile dopo creazione gara playoff")

        # Check player already present
        existing = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, user_id=user_id
        ).first()
        if existing:
            raise ValueError("Giocatore già presente nella lista playoff")

        # Validate: player must have participated in at least one gara of the campionato
        participation = (
            Inscription.query.join(Gara)
            .filter(
                Inscription.user_id == user_id,
                Gara.campionato_id == config.campionato_id,
            )
            .first()
        )
        if not participation:
            raise ValueError("Il giocatore non ha partecipato al campionato")

        # Determine position from classification if available
        from ..classification.models import Classification

        cls = Classification.query.filter_by(
            campionato_id=config.campionato_id, user_id=user_id
        ).first()
        position = cls.position if cls else 0

        qual = PlayoffQualification(
            configuration_id=configuration_id,
            user_id=user_id,
            qualifying_position=position or 0,
            qualification_reason=f"Aggiunto manualmente da {admin_username}",
            status=QualificationStatus.CONFIRMED,
            responded_at=utc_now(),
        )
        db.session.add(qual)
        return qual

    @staticmethod
    @transactional(domain="playoff")
    def admin_remove_player(
        qualification_id: int, admin_username: str
    ) -> PlayoffQualification:
        """Remove a player from a playoff config. Sets status to DECLINED."""
        qual = db.session.get(PlayoffQualification, qualification_id)
        if qual is None:
            raise NotFoundError("Qualificazione non trovata")

        config = qual.configuration
        if config.gara is not None:
            raise ValueError("Non modificabile dopo creazione gara playoff")

        qual.status = QualificationStatus.DECLINED
        original_reason = qual.qualification_reason
        qual.qualification_reason = (
            f"Rimosso da {admin_username} (era: {original_reason})"
        )
        qual.responded_at = utc_now()
        return qual

    @staticmethod
    def get_user_playoff_history(user_id: int) -> List[Dict[str, Any]]:
        """Get user's playoff participation history."""
        from sqlalchemy.orm import joinedload

        # Eager-load configuration + campionato per evitare 2 lazy-load per riga
        # (N+1) sull'accesso a configuration.campionato.name / .name.
        qualifications = (
            PlayoffQualification.query.filter_by(user_id=user_id)
            .options(
                joinedload(PlayoffQualification.configuration).joinedload(
                    PlayoffConfiguration.campionato
                )
            )
            .all()
        )

        history = []
        for qualification in qualifications:
            config = qualification.configuration
            # campionato puo' essere None (record orfano / campionato rimosso):
            # non far esplodere l'intera pagina history su un None-deref.
            campionato = config.campionato if config else None
            history.append(
                {
                    "campionato_name": campionato.name if campionato else None,
                    "playoff_name": config.name if config else None,
                    "qualifying_position": qualification.qualifying_position,
                    "status": qualification.status.value,
                    "qualified_at": qualification.created_at,
                    "responded_at": qualification.responded_at,
                }
            )

        return sorted(history, key=lambda x: x["qualified_at"], reverse=True)
