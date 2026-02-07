# models/campionato/tournament_service.py
"""CRUD and lifecycle operations for Campionato.

Extracted from services.py for maintainability (Round 4 P4).
Inherits statistics methods from TournamentStatisticsService.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from models.user.models import User
from models.match.models import Match
from sqlalchemy.exc import IntegrityError

from models.base import db, utc_now
from .models import Campionato
from ..user.role_enum import UserRole
from ..transaction.manager import (
    transactional,
    read_only,
)
from models.events.base import EventBus
from models.events.competition_events import (
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent,
    CampionatoCreatedEvent,
)
from .statistics_service import TournamentStatisticsService, compute_campionato_status


class TournamentService(TournamentStatisticsService):
    """Operazioni di business sui Campionati (API di base conservate).

    Inherits statistics/classification methods from TournamentStatisticsService.
    """

    def __init__(self):
        super().__init__()

    @transactional(domain="campionato")
    def create_campionato(self, name: str, **kwargs: Any) -> Campionato:
        """Crea e persiste un campionato (API compatibile con test esistenti)."""
        # Track domain access
        self._track_domain_access()

        # Filter valid kwargs for Campionato model
        valid_campionato_fields = {
            # Core configuration
            "campionato_type",
            "challenge_mode",
            "is_active",
            "planned_gare_count",
            # Default values for gare
            "default_venue_id",
            "default_entry_fee",
            "default_rounds_count",
            "default_odd_policy",
            "default_anti_rematch",
            # Deprecated but kept for compatibility
            "without_x",
            "final_playoffs",
            "scoring_policy",
        }
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k in valid_campionato_fields
        }

        # Extract director_id if present for separate handling
        director_id = kwargs.get("director_id")

        campionato = self._execute_with_tracking(
            lambda: Campionato(name=name, **filtered_kwargs)
        )
        db.session.add(campionato)
        db.session.flush()  # Flush to ensure ID is assigned

        # Handle director assignment if director_id provided
        if director_id:
            from ..user.models import DirectorAssignment

            director_assignment = DirectorAssignment(
                user_id=director_id,
                entity_type="campionato",
                entity_id=campionato.id,
                assigned_by_id=director_id,  # Self-assignment for now
            )
            db.session.add(director_assignment)

        # Publish creation event
        if director_id:
            event = CampionatoCreatedEvent(
                campionato_id=campionato.id,
                name=campionato.name,
                creator_id=director_id,
                campionato_type=campionato.campionato_type or "amalfi"
            )
            EventBus.publish(event)

        return campionato

    @transactional(domain="campionato")
    def create_campionato_with_director(
        self,
        name: str,
        creator_user_id: int,
        campionato_type: str = "amalfi",
        challenge_mode: bool = False,
        is_active: bool = True,
        # New fields - wizard step 1
        planned_gare_count: int = 10,
        # New fields - wizard step 2 (defaults for gare)
        default_venue_id: Optional[int] = None,
        default_entry_fee: Optional[float] = None,
        default_rounds_count: int = 3,
        default_odd_policy: str = "bye",
        default_anti_rematch: bool = True,
        default_classification_system: str = "WINS",
        # Deprecated but kept for compatibility
        without_x: bool = False,
        final_playoffs: bool = False,
        scoring_policy: str = "classic",
    ) -> Campionato:
        """Crea campionato e assegna automaticamente il direttore se necessario."""
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import User, DirectorAssignment

        user = self._execute_with_tracking(
            lambda: db.session.get(User, creator_user_id)
        )
        if not user:
            raise ValueError("User not found")

        campionato = self._execute_with_tracking(
            lambda: Campionato(
                name=name,
                campionato_type=campionato_type,
                challenge_mode=challenge_mode,
                is_active=is_active,
                planned_gare_count=planned_gare_count,
                default_venue_id=default_venue_id,
                default_entry_fee=default_entry_fee,
                default_rounds_count=default_rounds_count,
                default_odd_policy=default_odd_policy,
                default_anti_rematch=default_anti_rematch,
                default_classification_system=default_classification_system,
                # Deprecated fields
                without_x=without_x,
                final_playoffs=final_playoffs,
                scoring_policy=scoring_policy,
            )
        )
        db.session.add(campionato)
        db.session.flush()  # Per ottenere l'ID senza commit completo

        # Se l'utente è un direttore (non admin), assegnalo automaticamente
        if user.is_director and not user.is_admin:
            assignment = self._execute_with_tracking(
                lambda: DirectorAssignment(
                    entity_type="campionato",
                    entity_id=campionato.id,
                    user_id=creator_user_id,
                    assigned_by_id=creator_user_id,
                )
            )
            db.session.add(assignment)

        # Publish creation event
        event = CampionatoCreatedEvent(
            campionato_id=campionato.id,
            name=campionato.name,
            creator_id=creator_user_id,
            campionato_type=campionato.campionato_type or "amalfi"
        )
        EventBus.publish(event)

        return campionato

    @transactional(domain="campionato")
    def update_campionato(self, campionato_id: int, **kwargs: Any) -> Campionato:
        """Aggiorna un campionato con i campi forniti."""
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if not campionato.can_be_modified():
            raise ValueError(
                "Impossibile modificare il campionato: alcune gare hanno già delle iscrizioni!"
            )

        # Aggiorna solo i campi forniti
        for field, value in kwargs.items():
            if hasattr(campionato, field):
                setattr(campionato, field, value)

        campionato.updated_at = utc_now()
        return campionato

    @transactional(domain="campionato")
    def toggle_active_status(self, campionato_id: int) -> Campionato:
        """Attiva/disattiva un campionato."""
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        campionato.is_active = not campionato.is_active
        campionato.updated_at = utc_now()
        return campionato

    @transactional(domain="campionato")
    def add_director(
        self, campionato_id: int, user_id: int, assigned_by_id: int
    ) -> bool:
        """Aggiunge un co-direttore al campionato.

        Returns:
            True se aggiunto con successo, False se già esistente

        Raises:
            ValueError se l'utente è admin
        """
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import User, DirectorAssignment

        user = self._execute_with_tracking(lambda: db.session.get(User, user_id))
        if not user:
            raise ValueError("User not found")

        if user.role == UserRole.ADMIN.value:
            raise ValueError("Gli admin non vanno assegnati come direttori.")

        existing = self._execute_with_tracking(
            lambda: DirectorAssignment.query.filter_by(
                entity_type="campionato", entity_id=campionato_id, user_id=user_id
            ).first()
        )

        if existing:
            return False  # Già esistente

        assignment = self._execute_with_tracking(
            lambda: DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato_id,
                user_id=user_id,
                assigned_by_id=assigned_by_id,
            )
        )
        db.session.add(assignment)

        # Pubblica evento per notifica (pattern event-driven)
        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        event = DirectorAssignmentAddedEvent(
            entity_type="campionato",
            entity_id=campionato_id,
            entity_name=campionato.name,
            user_id=user_id,
            username=user.username,
            assigned_by_id=assigned_by_id
        )
        EventBus.publish(event)

        return True

    @transactional(domain="campionato")
    def remove_director(self, campionato_id: int, user_id: int) -> bool:
        """Rimuove un co-direttore dal campionato.

        Returns:
            True se rimosso con successo, False se non trovato
        """
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import DirectorAssignment, User

        assignment = self._execute_with_tracking(
            lambda: DirectorAssignment.query.filter_by(
                entity_type="campionato", entity_id=campionato_id, user_id=user_id
            ).first()
        )

        if not assignment:
            return False

        # Recupera dati per evento prima di eliminare
        user = self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )

        # Elimina associazione
        db.session.delete(assignment)

        # Pubblica evento per notifica (pattern event-driven)
        event = DirectorAssignmentRemovedEvent(
            entity_type="campionato",
            entity_id=campionato_id,
            entity_name=campionato.name,
            user_id=user_id,
            username=user.username,
            removed_by_id=assignment.assigned_by_id
        )
        EventBus.publish(event)

        return True

    @read_only(domain="campionato")
    def get_active_campionatos(self) -> List[Campionato]:
        """Restituisce i campionati attivi (non soft-deleted)."""
        # Track domain access
        self._track_domain_access()

        return self._execute_with_tracking(
            lambda: Campionato.get_active_campionatos().all()
        )

    @transactional(domain="campionato")
    def delete_campionato(self, campionato_id: int) -> None:
        """
        Cancella un campionato rispettando le regole di dominio e garantendo atomicità.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if not campionato.can_be_deleted():
            raise ValueError("Campionato non cancellabile: esistono iscrizioni.")

        # Clean up director assignments manually since it's a polymorphic relationship
        from models.user.models import DirectorAssignment

        assignments = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        )
        for assignment in assignments:
            db.session.delete(assignment)

        db.session.delete(campionato)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            raise

    @transactional(domain="campionato")
    def soft_delete_campionato(
        self,
        campionato_id: int,
        deleted_by_id: int,
        cascade_option: str = "delete_all",
        reason: Optional[str] = None
    ) -> bool:
        """Soft delete campionato with cascade options."""
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if campionato.is_deleted:
            return False

        # Handle cascade option for all garas in the campionato
        if cascade_option == "keep_matches":
            # Detach all matches from garas in this campionato
            gara_ids = [g.id for g in campionato.gare]
            if gara_ids:
                Match.query.filter(Match.gara_id.in_(gara_ids)).update(
                    {"gara_id": None},
                    synchronize_session="fetch"
                )

        # Soft delete all garas in the campionato
        for gara in campionato.gare:
            if not gara.is_deleted:
                gara.deleted_at = utc_now()
                gara.deleted_reason = reason or ""
                db.session.add(gara)

        # Soft delete the campionato itself
        success = campionato.soft_delete(reason or "")
        return success

    @transactional(domain="campionato")
    def restore_campionato(self, campionato_id: int) -> bool:
        """
        Restore a soft-deleted campionato.
        Returns True if successful, False if not deleted.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if not campionato.is_deleted:
            return False

        success = campionato.restore()
        return success

    @read_only(domain="campionato")
    def get_deleted_campionatos(self) -> List[Campionato]:
        """Get all soft-deleted campionati."""
        # Track domain access
        self._track_domain_access()

        return self._execute_with_tracking(
            lambda: Campionato.get_deleted_campionatos().all()
        )

    @transactional(domain="campionato")
    def permanently_delete_campionato(self, campionato_id: int) -> None:
        """
        Permanently delete a campionato (hard delete).
        Only allowed if no matches have been played.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if not campionato.can_be_hard_deleted():
            raise ValueError("Cannot permanently delete campionato with played matches")

        db.session.delete(campionato)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            raise

    @read_only(domain="campionato")
    def get_campionato_detail_data(self, campionato_id: int) -> Dict[str, Any]:
        """
        Get all data needed for the campionato detail page.
        """
        from models.competition.models import Gara
        from models.user.models import User
        from sqlalchemy import not_

        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        gare = self._execute_with_tracking(
            lambda: (
                Gara.query.filter_by(campionato_id=campionato_id)
                .order_by(Gara.number)
                .all()
            )
        )

        # ID dei direttori già assegnati a questo campionato
        from models.user.models import DirectorAssignment

        assigned_ids = [
            da.user_id
            for da in db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        ]

        # Solo utenti role='director' che non sono già assegnati
        candidate_directors = self._execute_with_tracking(
            lambda: (
                User.query.filter_by(role="director")
                .filter(not_(User.id.in_(assigned_ids)))
                .order_by(User.username)
                .all()
            )
        )

        return {
            "campionato": campionato,
            "gare": gare,
            "candidate_directors": candidate_directors,
        }

    @read_only(domain="campionato")
    def get_candidate_directors(self, campionato_id: int) -> List[User]:
        """
        Get directors not already assigned to this campionato.
        """
        from models.user.models import User
        from sqlalchemy import not_

        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        # ID dei direttori già assegnati a questo campionato
        from models.user.models import DirectorAssignment

        assigned_ids = [
            da.user_id
            for da in db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        ]

        # Solo utenti role='director' che non sono già assegnati
        candidate_directors = self._execute_with_tracking(
            lambda: (
                User.query.filter_by(role="director")
                .filter(not_(User.id.in_(assigned_ids)))
                .order_by(User.username)
                .all()
            )
        )

        return candidate_directors

    @read_only(domain="campionato")
    def calculate_campionato_status(self, campionato_id: int) -> str:
        """
        Calculate derived status information for a campionato.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        return compute_campionato_status(campionato)

    @staticmethod
    @transactional(domain="campionato")
    def create_playoff_config(
        campionato_id: int,
        name: str,
        max_participants: int,
        positions_from: int,
        positions_to: int,
    ) -> Any:
        """Create a playoff configuration for a campionato."""
        from models.playoff.models import PlayoffConfiguration, PlayoffType

        config = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=PlayoffType.TOP_N,
            max_participants=max_participants,
            positions_from=positions_from,
            positions_to=positions_to,
            is_active=True,
            auto_generate=True,
        )
        db.session.add(config)
        return config
