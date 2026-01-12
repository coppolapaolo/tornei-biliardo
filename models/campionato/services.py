"""
Module: models/campionato/services
Purpose: Service layer per il dominio Campionato + funzione pura di calcolo
         dello stato derivato del campionato.
Data Structures: TournamentService, compute_campionato_status
Dependencies: models.base.db, models.campionato.models, models.status_enum
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from models.user.models import User
from models.match.models import Match
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from models.base import db
from models.status_enum import TournamentStatus, GaraStatus
from models.matchmaking.configuration import MatchmakingStrategy
from .models import Campionato
from ..user.role_enum import UserRole
from ..transaction.manager import (
    DomainService,
    transactional,
    read_only,
)
from models.events.base import EventBus
from models.events.competition_events import (
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent
)


class TournamentService(DomainService):
    """Operazioni di business sui Campionati (API di base conservate)."""

    def __init__(self):
        super().__init__("campionato")

    @transactional(domain="campionato")
    def create_campionato(self, name: str, **kwargs) -> Campionato:
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
        # Deprecated but kept for compatibility
        without_x: bool = False,
        final_playoffs: bool = False,
        scoring_policy: str = "classic",
    ) -> Campionato:
        """Crea campionato e assegna automaticamente il direttore se necessario.

        Args:
            name: Nome del campionato
            creator_user_id: ID dell'utente che crea il campionato
            campionato_type: Tipo matchmaking (amalfi, random, etc.)
            challenge_mode: Abilita challenge drill
            is_active: Se il campionato è attivo
            planned_gare_count: Numero di gare previste (target)
            default_venue_id: Venue di default per le gare
            default_entry_fee: Costo iscrizione di default
            default_rounds_count: Numero turni di default per gara
            default_odd_policy: Gestione dispari di default (bye, bye_with_challenge, trio)
            default_anti_rematch: Anti-rematch di default
            without_x: DEPRECATED - use default_odd_policy
            final_playoffs: DEPRECATED - use PlayoffConfiguration
            scoring_policy: DEPRECATED - automatic from campionato_type
        """
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

        return campionato

    @transactional(domain="campionato")
    def update_campionato(self, campionato_id: int, **kwargs) -> Campionato:
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

        campionato.updated_at = datetime.utcnow()
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
        campionato.updated_at = datetime.utcnow()
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
        - Blocca se esistono iscrizioni (regola attuale in Campionato.can_be_deleted()).
        - Esegue il delete con cascade ORM/DB.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if not campionato.can_be_deleted():
            # Regola di dominio esistente: iscrizioni presenti ⇒ non cancellabile
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
            # Propaga: la route mapperà su HTTP 409 con messaggio user-friendly
            raise

    @transactional(domain="campionato")
    def soft_delete_campionato(
        self,
        campionato_id: int,
        deleted_by_id: int,
        cascade_option: str = "delete_all",
        reason: Optional[str] = None
    ) -> bool:
        """Soft delete campionato with cascade options.

        Admin-only operation. Marks the campionato and all its garas as deleted.
        Related matches can be either kept linked (hidden with garas) or detached
        (become standalone).

        Args:
            campionato_id: ID of campionato to soft delete
            deleted_by_id: ID of admin performing the deletion
            cascade_option: "delete_all" or "keep_matches"
                - delete_all: Matches stay linked (hidden with garas)
                - keep_matches: Matches become standalone (gara_id = NULL)
            reason: Optional reason for deletion

        Returns:
            True if successful, False if already deleted

        Raises:
            ValueError: If campionato not found
        """
        from models.competition.models import Gara

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
                gara.deleted_at = datetime.utcnow()
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
        This consolidates the complex queries from the campionato_detail route.

        Args:
            campionato_id: ID of the campionato to get data for

        Returns:
            Dictionary containing all campionato detail data
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

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of candidate directors
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

        Args:
            campionato_id: ID of the campionato

        Returns:
            String representation of campionato status
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        return compute_campionato_status(campionato)

    @read_only(domain="campionato")
    def get_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """
        Get campionato-level statistics.

        Args:
            campionato_id: ID of the campionato

        Returns:
            Dictionary containing campionato statistics
        """
        from models.competition.models import Gara, Inscription

        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        # Get all provas for this campionato
        gare = self._execute_with_tracking(
            lambda: Gara.query.filter_by(campionato_id=campionato_id).all()
        )
        gara_ids = [p.id for p in gare]

        # Calculate statistics
        total_garas = len(gare)
        total_inscriptions = self._execute_with_tracking(
            lambda: (
                Inscription.query.filter(Inscription.gara_id.in_(gara_ids)).count()
                if gara_ids
                else 0
            )
        )
        total_matches = self._execute_with_tracking(
            lambda: (
                Match.query.filter(Match.gara_id.in_(gara_ids)).count()
                if gara_ids
                else 0
            )
        )

        # Status distribution
        status_counts = {}
        for gara in gare:
            status = getattr(gara, "status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_garas": total_garas,
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "status_distribution": status_counts,
        }

    @read_only(domain="campionato")
    def calculate_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """Calcola statistiche avanzate del campionato."""
        from models.competition.models import Gara, Inscription
        from sqlalchemy import func, distinct

        # Trova tutte le gare del campionato
        gare = db.session.query(Gara).filter_by(campionato_id=campionato_id).all()

        # Giocatori unici che hanno mai partecipato al campionato
        unique_players_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(Gara.campionato_id == campionato_id)
        )
        total_unique_players = unique_players_query.count()

        # Giocatori attualmente iscritti a gare con iscrizioni aperte
        active_inscriptions_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Gara.status == "inscription",  # Solo gare con iscrizioni aperte
            )
        )
        currently_inscribed_players = active_inscriptions_query.count()

        # Match totali completati in tutte le gare
        completed_matches_query = (
            db.session.query(func.count(Match.id))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == "completed",  # type: ignore[attr-defined]
            )
        )
        total_completed_matches = completed_matches_query.scalar() or 0

        # Rack totali giocati (somma dei punteggi di tutti i match completati)
        rack_sum_query = (
            db.session.query(func.sum(Match.player1_score + Match.player2_score))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == "completed",  # type: ignore[attr-defined]
            )
        )
        total_racks_played = rack_sum_query.scalar() or 0

        return {
            "total_unique_players": total_unique_players,
            "currently_inscribed_players": currently_inscribed_players,
            "total_completed_matches": total_completed_matches,
            "total_racks_played": total_racks_played,
        }

    def _aggregate_player_totals(
        self,
        garas: List,
        campionato_type: str,
    ) -> Dict[int, Dict[str, Any]]:
        """Aggrega i totali dei giocatori per un insieme di gare.

        Args:
            garas: Lista di gare da aggregare
            campionato_type: Tipo di campionato (amalfi, random, etc.)

        Returns:
            Dizionario user_id -> dati aggregati del giocatore
        """
        from models.classification.models import RoundClassification, GaraClassification

        player_totals: Dict[int, Dict[str, Any]] = {}

        for gara in garas:
            # Ottieni la classifica finale di questa gara (ultimo turno)
            final_round = gara.rounds_count
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=final_round)
                .order_by(RoundClassification.position)
                .all()
            )

            # Per Random campionati, ottieni anche i punteggi SSR da GaraClassification
            gara_ssr_scores: Dict[int, int] = {}
            if campionato_type == MatchmakingStrategy.RANDOM.value:
                gara_classifications = (
                    db.session.query(GaraClassification)
                    .filter_by(gara_id=gara.id)
                    .all()
                )
                gara_ssr_scores = {
                    gc.user_id: gc.spot_shot_wins or 0
                    for gc in gara_classifications
                }

            for classification in classifications:
                user_id = classification.user_id
                if user_id not in player_totals:
                    player_totals[user_id] = {
                        "username": classification.user.username,
                        "total_matches_won": 0,
                        "total_rack_difference": 0,
                        "total_spot_shot_wins": 0,
                        "participations": 0,
                        "total_points": 0,
                    }

                # Per campionati Amalfi: somma match vinti e differenza rack
                player_totals[user_id]["total_matches_won"] += (
                    classification.matches_won or 0
                )
                player_totals[user_id]["total_rack_difference"] += (
                    classification.rack_difference or 0
                )
                # Aggiungi punteggio SSR per campionati Random
                player_totals[user_id]["total_spot_shot_wins"] += (
                    gara_ssr_scores.get(user_id, 0)
                )
                player_totals[user_id]["participations"] += 1

        # Per sistemi a punti, calcola i punti
        if campionato_type not in [
            MatchmakingStrategy.AMALFI.value,
            MatchmakingStrategy.RANDOM.value,
        ]:
            position_points = {
                1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1, 10: 1
            }
            for gara in garas:
                final_round = gara.rounds_count
                classifications = (
                    db.session.query(RoundClassification)
                    .filter_by(gara_id=gara.id, round_number=final_round)
                    .order_by(RoundClassification.position)
                    .all()
                )
                for classification in classifications:
                    user_id = classification.user_id
                    if user_id in player_totals:
                        points = position_points.get(classification.position, 0)
                        player_totals[user_id]["total_points"] += points

        return player_totals

    def _sort_and_rank_players(
        self,
        player_totals: Dict[int, Dict[str, Any]],
        campionato_type: str,
    ) -> List[tuple]:
        """Ordina i giocatori e assegna le posizioni.

        Args:
            player_totals: Dizionario user_id -> dati aggregati
            campionato_type: Tipo di campionato

        Returns:
            Lista di tuple (posizione, user_id) ordinate
        """
        if campionato_type == MatchmakingStrategy.AMALFI.value:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]["total_matches_won"],
                    -x[1]["total_rack_difference"],
                ),
            )
        elif campionato_type == MatchmakingStrategy.RANDOM.value:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]["total_rack_difference"],
                    -x[1]["total_spot_shot_wins"],
                ),
            )
        else:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1].get("total_points", 0),
                    -x[1]["total_rack_difference"],
                    -x[1]["total_matches_won"],
                ),
            )

        # Restituisce lista di (posizione, user_id)
        return [(pos, user_id) for pos, (user_id, _) in enumerate(sorted_players, 1)]

    @read_only(domain="campionato")
    def calculate_general_classification(self, campionato_id: int) -> List[tuple]:
        """Calcola la classifica generale del campionato basata su tutte le gare completate.

        Include il calcolo del trend (previous_position) confrontando la classifica
        attuale con quella calcolata escludendo l'ultima gara completata.
        """
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        # Trova il campionato per verificare il tipo
        campionato = db.session.query(Campionato).filter_by(id=campionato_id).first()
        if not campionato:
            return []

        # Trova tutte le gare completate del campionato (incluse quelle "playing" ma finite)
        all_garas = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .filter(Gara.status.in_(["completed", "playing"]))
            .order_by(Gara.number)
            .all()
        )

        # Filtra le gare che sono realmente completate
        completed_garas = []
        for gara in all_garas:
            if gara.status == "completed":
                completed_garas.append(gara)
            elif gara.status == "playing" and gara.current_round > gara.rounds_count:
                # Gara con tutti i round completati
                completed_garas.append(gara)

        if not completed_garas:
            return []

        # Calcola posizioni precedenti (tutte le gare tranne l'ultima)
        previous_positions: Dict[int, int] = {}
        if len(completed_garas) > 1:
            previous_garas = completed_garas[:-1]
            previous_totals = self._aggregate_player_totals(
                previous_garas, campionato.campionato_type
            )
            previous_ranking = self._sort_and_rank_players(
                previous_totals, campionato.campionato_type
            )
            previous_positions = {user_id: pos for pos, user_id in previous_ranking}

        # Calcola classifica attuale (tutte le gare)
        player_totals = self._aggregate_player_totals(
            completed_garas, campionato.campionato_type
        )
        current_ranking = self._sort_and_rank_players(
            player_totals, campionato.campionato_type
        )

        # Costruisci risultato con posizione precedente
        result = []
        for position, user_id in current_ranking:
            data = player_totals[user_id]
            # Aggiungi previous_position solo se il giocatore era nella classifica precedente
            data["previous_position"] = previous_positions.get(user_id)
            result.append((position, data))

        return result


# -----------------------------
# Funzione *pura* per lo stato derivato del Campionato
# -----------------------------


def compute_campionato_status(campionato: Campionato) -> str:
    """Calcola lo stato derivato del campionato in base agli stati delle Gare.

    Regole (soft, aderenti al comportamento attuale):
    - Se non ci sono Gare → SETUP
    - Se almeno una Gara è in PLAYING → IN_PROGRESS
    - Altrimenti, se almeno una Gara è in INSCRIPTION → REGISTRATION_OPEN
    - Altrimenti, se tutte le Gare esistono e sono COMPLETED → COMPLETED
    - In tutti gli altri casi → SETUP

    Ritorna la stringa dello stato (compat con UI/template esistenti).
    """
    gare = getattr(campionato, "gare", []) or []
    if not gare:
        return TournamentStatus.SETUP.value

    # Normalizza valori (stringhe) e valuta
    values = [getattr(p, "status", GaraStatus.SETUP.value) for p in gare]

    if any(v == GaraStatus.PLAYING.value for v in values):
        return TournamentStatus.IN_PROGRESS.value
    if any(v == GaraStatus.INSCRIPTION.value for v in values):
        return TournamentStatus.REGISTRATION_OPEN.value
    if all(v == GaraStatus.COMPLETED.value for v in values):
        return TournamentStatus.COMPLETED.value

    return TournamentStatus.SETUP.value


__all__ = ["TournamentService", "compute_campionato_status"]
