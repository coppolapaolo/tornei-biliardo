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
from .models import Campionato
from ..user.role_enum import UserRole
from ..transaction.manager import (
    DomainService,
    transactional,
    read_only,
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

        campionato = self._execute_with_tracking(
            lambda: Campionato(name=name, **kwargs)
        )
        db.session.add(campionato)
        db.session.flush()  # Flush to ensure ID is assigned
        return campionato

    @transactional(domain="campionato")
    def create_campionato_with_director(
        self,
        name: str,
        creator_user_id: int,
        campionato_type: str = "Amalfi",
        without_x: bool = False,
        final_playoffs: bool = False,
        challenge_mode: bool = False,
        scoring_policy: str = "classic",
        is_active: bool = True,
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
                without_x=without_x,
                final_playoffs=final_playoffs,
                challenge_mode=challenge_mode,
                scoring_policy=scoring_policy,
                is_active=is_active,
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
        from models.user.models import DirectorAssignment

        assignment = self._execute_with_tracking(
            lambda: DirectorAssignment.query.filter_by(
                entity_type="campionato", entity_id=campionato_id, user_id=user_id
            ).first()
        )

        if assignment:
            db.session.delete(assignment)
            return True

        return False

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
        assignments = db.session.query(DirectorAssignment).filter(
            DirectorAssignment.entity_type == "campionato",
            DirectorAssignment.entity_id == campionato_id
        ).all()
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
        self, campionato_id: int, reason: Optional[str] = None
    ) -> bool:
        """
        Perform soft delete on campionato with played matches.
        Returns True if successful, False if already deleted.
        """
        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        if campionato.is_deleted:
            return False

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

    @read_only(domain="campionato")
    def calculate_general_classification(self, campionato_id: int) -> List[tuple]:
        """Calcola la classifica generale del campionato basata su tutte le gare completate."""
        from models.competition.models import Gara
        from models.classification.models import RoundClassification
        from models.campionato.models import Campionato
        from models.user.models import User
        from sqlalchemy import func

        # Trova il campionato per verificare il tipo
        campionato = db.session.query(Campionato).filter_by(id=campionato_id).first()
        if not campionato:
            return []

        # Trova tutte le gare completate del campionato (incluse quelle "playing" ma finite)
        all_garas = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .filter(Gara.status.in_(["completed", "playing"]))
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

        # Raccoglie tutti i risultati per giocatore
        player_totals = {}

        for gara in completed_garas:
            # Ottieni la classifica finale di questa gara (ultimo turno)
            final_round = gara.rounds_count
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=final_round)
                .order_by(RoundClassification.position)
                .all()
            )

            for classification in classifications:
                user_id = classification.user_id
                if user_id not in player_totals:
                    player_totals[user_id] = {
                        "username": classification.user.username,
                        "total_matches_won": 0,
                        "total_rack_difference": 0,
                        "participations": 0,
                    }

                # Per campionati Amalfi: somma match vinti e differenza rack
                player_totals[user_id]["total_matches_won"] += (
                    classification.matches_won or 0
                )
                player_totals[user_id]["total_rack_difference"] += (
                    classification.rack_difference or 0
                )
                player_totals[user_id]["participations"] += 1

        # Per campionati Amalfi: ordina per match vinti (decrescente), poi per differenza rack (decrescente)
        if campionato.campionato_type == "Amalfi":
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]["total_matches_won"],  # Prima i match vinti
                    -x[1]["total_rack_difference"],  # Poi la differenza rack
                ),
            )
        else:
            # Per altri tipi di campionato, usa il sistema a punti
            position_points = {
                1: 10,
                2: 7,
                3: 5,
                4: 4,
                5: 3,
                6: 2,
                7: 2,
                8: 1,
                9: 1,
                10: 1,
            }
            # Calcola punti per giocatore (logica precedente)
            for gara in completed_garas:
                final_round = gara.rounds_count
                classifications = (
                    db.session.query(RoundClassification)
                    .filter_by(gara_id=gara.id, round_number=final_round)
                    .order_by(RoundClassification.position)
                    .all()
                )

                for classification in classifications:
                    user_id = classification.user_id
                    if "total_points" not in player_totals[user_id]:
                        player_totals[user_id]["total_points"] = 0

                    points = position_points.get(classification.position, 0)
                    player_totals[user_id]["total_points"] += points

            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1].get("total_points", 0),
                    -x[1]["total_rack_difference"],
                    -x[1]["total_matches_won"],
                ),
            )

        # Aggiungi posizioni e restituisci nel formato richiesto
        result = []
        for position, (user_id, data) in enumerate(sorted_players, 1):
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
