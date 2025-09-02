"""
Module: models/tournament/services
Purpose: Service layer per il dominio Tournament + funzione pura di calcolo
         dello stato derivato del torneo.
Data Structures: TournamentService, compute_tournament_status
Dependencies: models.base.db, models.tournament.models, models.status_enum
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from models.user.models import User
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from models.base import db
from models.status_enum import TournamentStatus, ProvaStatus
from .models import Tournament
from ..user.role_enum import UserRole
from ..transaction.manager import (
    DomainService,
    transactional,
    read_only,
)


class TournamentService(DomainService):
    """Operazioni di business sui Tornei (API di base conservate)."""

    def __init__(self):
        super().__init__("tournament")

    @transactional(domain="tournament")
    def create_tournament(self, name: str, **kwargs) -> Tournament:
        """Crea e persiste un torneo (API compatibile con test esistenti)."""
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: Tournament(name=name, **kwargs)
        )
        db.session.add(tournament)
        db.session.flush()  # Flush to ensure ID is assigned
        return tournament

    @transactional(domain="tournament")
    def create_tournament_with_director(
        self,
        name: str,
        creator_user_id: int,
        tournament_type: str = "Amalfi",
        without_x: bool = False,
        final_playoffs: bool = False,
        challenge_mode: bool = False,
        scoring_policy: str = "classic",
        is_active: bool = True,
    ) -> Tournament:
        """Crea torneo e assegna automaticamente il direttore se necessario."""
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import User, TournamentDirector

        user = self._execute_with_tracking(
            lambda: db.session.get(User, creator_user_id)
        )
        if not user:
            raise ValueError("User not found")

        tournament = self._execute_with_tracking(
            lambda: Tournament(
                name=name,
                tournament_type=tournament_type,
                without_x=without_x,
                final_playoffs=final_playoffs,
                challenge_mode=challenge_mode,
                scoring_policy=scoring_policy,
                is_active=is_active,
            )
        )
        db.session.add(tournament)
        db.session.flush()  # Per ottenere l'ID senza commit completo

        # Se l'utente è un direttore (non admin), assegnalo automaticamente
        if user.is_director and not user.is_admin:
            assignment = self._execute_with_tracking(
                lambda: TournamentDirector(
                    user_id=creator_user_id,
                    tournament_id=tournament.id,
                    assigned_by_id=creator_user_id,
                )
            )
            db.session.add(assignment)

        return tournament

    @transactional(domain="tournament")
    def update_tournament(self, tournament_id: int, **kwargs) -> Tournament:
        """Aggiorna un torneo con i campi forniti."""
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        if not tournament.can_be_modified():
            raise ValueError(
                "Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!"
            )

        # Aggiorna solo i campi forniti
        for field, value in kwargs.items():
            if hasattr(tournament, field):
                setattr(tournament, field, value)

        tournament.updated_at = datetime.utcnow()
        return tournament

    @transactional(domain="tournament")
    def toggle_active_status(self, tournament_id: int) -> Tournament:
        """Attiva/disattiva un torneo."""
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        tournament.is_active = not tournament.is_active
        tournament.updated_at = datetime.utcnow()
        return tournament

    @transactional(domain="tournament")
    def add_director(
        self, tournament_id: int, user_id: int, assigned_by_id: int
    ) -> bool:
        """Aggiunge un co-direttore al torneo.

        Returns:
            True se aggiunto con successo, False se già esistente

        Raises:
            ValueError se l'utente è admin
        """
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import User, TournamentDirector

        user = self._execute_with_tracking(lambda: db.session.get(User, user_id))
        if not user:
            raise ValueError("User not found")

        if user.role == UserRole.ADMIN.value:
            raise ValueError("Gli admin non vanno assegnati come direttori.")

        existing = self._execute_with_tracking(
            lambda: TournamentDirector.query.filter_by(
                user_id=user_id, tournament_id=tournament_id
            ).first()
        )

        if existing:
            return False  # Già esistente

        assignment = self._execute_with_tracking(
            lambda: TournamentDirector(
                user_id=user_id,
                tournament_id=tournament_id,
                assigned_by_id=assigned_by_id,
            )
        )
        db.session.add(assignment)
        return True

    @transactional(domain="tournament")
    def remove_director(self, tournament_id: int, user_id: int) -> bool:
        """Rimuove un co-direttore dal torneo.

        Returns:
            True se rimosso con successo, False se non trovato
        """
        # Track domain access
        self._track_domain_access()

        # Import locale per evitare import circolari
        from models.user.models import TournamentDirector

        assignment = self._execute_with_tracking(
            lambda: TournamentDirector.query.filter_by(
                user_id=user_id, tournament_id=tournament_id
            ).first()
        )

        if assignment:
            db.session.delete(assignment)
            return True

        return False

    @read_only(domain="tournament")
    def get_active_tournaments(self) -> List[Tournament]:
        """Restituisce i tornei attivi (non soft-deleted)."""
        # Track domain access
        self._track_domain_access()

        return self._execute_with_tracking(
            lambda: Tournament.get_active_tournaments().all()
        )

    @transactional(domain="tournament")
    def delete_tournament(self, tournament_id: int) -> None:
        """
        Cancella un torneo rispettando le regole di dominio e garantendo atomicità.
        - Blocca se esistono iscrizioni (regola attuale in Tournament.can_be_deleted()).
        - Esegue il delete con cascade ORM/DB.
        """
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        if not tournament.can_be_deleted():
            # Regola di dominio esistente: iscrizioni presenti ⇒ non cancellabile
            raise ValueError("Torneo non cancellabile: esistono iscrizioni.")

        db.session.delete(tournament)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            # Propaga: la route mapperà su HTTP 409 con messaggio user-friendly
            raise

    @transactional(domain="tournament")
    def soft_delete_tournament(
        self, tournament_id: int, reason: Optional[str] = None
    ) -> bool:
        """
        Perform soft delete on tournament with played matches.
        Returns True if successful, False if already deleted.
        """
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        if tournament.is_deleted:
            return False

        success = tournament.soft_delete(reason or "")
        return success

    @transactional(domain="tournament")
    def restore_tournament(self, tournament_id: int) -> bool:
        """
        Restore a soft-deleted tournament.
        Returns True if successful, False if not deleted.
        """
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        if not tournament.is_deleted:
            return False

        success = tournament.restore()
        return success

    @read_only(domain="tournament")
    def get_deleted_tournaments(self) -> List[Tournament]:
        """Get all soft-deleted tournaments."""
        # Track domain access
        self._track_domain_access()

        return self._execute_with_tracking(
            lambda: Tournament.get_deleted_tournaments().all()
        )

    @transactional(domain="tournament")
    def permanently_delete_tournament(self, tournament_id: int) -> None:
        """
        Permanently delete a tournament (hard delete).
        Only allowed if no matches have been played.
        """
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        if not tournament.can_be_hard_deleted():
            raise ValueError("Cannot permanently delete tournament with played matches")

        db.session.delete(tournament)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            raise

    @read_only(domain="tournament")
    def get_tournament_detail_data(self, tournament_id: int) -> Dict[str, Any]:
        """
        Get all data needed for the tournament detail page.
        This consolidates the complex queries from the tournament_detail route.

        Args:
            tournament_id: ID of the tournament to get data for

        Returns:
            Dictionary containing all tournament detail data
        """
        from models.competition.models import Prova
        from models.user.models import User
        from sqlalchemy import not_

        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        provas = self._execute_with_tracking(
            lambda: (
                Prova.query.filter_by(tournament_id=tournament_id)
                .order_by(Prova.number)
                .all()
            )
        )

        # ID dei direttori già assegnati a questo torneo
        assigned_ids = [td.user_id for td in tournament.directors_association]

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
            "tournament": tournament,
            "provas": provas,
            "candidate_directors": candidate_directors,
        }

    @read_only(domain="tournament")
    def get_candidate_directors(self, tournament_id: int) -> List[User]:
        """
        Get directors not already assigned to this tournament.

        Args:
            tournament_id: ID of the tournament

        Returns:
            List of candidate directors
        """
        from models.user.models import User
        from sqlalchemy import not_

        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        # ID dei direttori già assegnati a questo torneo
        assigned_ids = [td.user_id for td in tournament.directors_association]

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

    @read_only(domain="tournament")
    def calculate_tournament_status(self, tournament_id: int) -> str:
        """
        Calculate derived status information for a tournament.

        Args:
            tournament_id: ID of the tournament

        Returns:
            String representation of tournament status
        """
        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        return compute_tournament_status(tournament)

    @read_only(domain="tournament")
    def get_tournament_statistics(self, tournament_id: int) -> Dict[str, Any]:
        """
        Get tournament-level statistics.

        Args:
            tournament_id: ID of the tournament

        Returns:
            Dictionary containing tournament statistics
        """
        from models.competition.models import Prova, Inscription
        from models.match.models import Match

        # Track domain access
        self._track_domain_access()

        tournament = self._execute_with_tracking(
            lambda: db.session.get(Tournament, tournament_id)
        )
        if not tournament:
            raise ValueError("Tournament not found")

        # Get all provas for this tournament
        provas = self._execute_with_tracking(
            lambda: Prova.query.filter_by(tournament_id=tournament_id).all()
        )
        prova_ids = [p.id for p in provas]

        # Calculate statistics
        total_provas = len(provas)
        total_inscriptions = self._execute_with_tracking(
            lambda: (
                Inscription.query.filter(Inscription.prova_id.in_(prova_ids)).count()
                if prova_ids
                else 0
            )
        )
        total_matches = self._execute_with_tracking(
            lambda: (
                Match.query.filter(Match.prova_id.in_(prova_ids)).count()
                if prova_ids
                else 0
            )
        )

        # Status distribution
        status_counts = {}
        for prova in provas:
            status = getattr(prova, "status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_provas": total_provas,
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "status_distribution": status_counts,
        }


    @read_only(domain="tournament")
    def calculate_tournament_statistics(self, tournament_id: int) -> Dict[str, Any]:
        """Calcola statistiche avanzate del torneo."""
        from models.competition.models import Prova, Inscription
        from models.match.models import Match
        from sqlalchemy import func, distinct
        
        # Trova tutte le prove del torneo
        provas = db.session.query(Prova).filter_by(tournament_id=tournament_id).all()
        
        # Giocatori unici che hanno mai partecipato al torneo
        unique_players_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Prova, Inscription.prova_id == Prova.id)
            .filter(Prova.tournament_id == tournament_id)
        )
        total_unique_players = unique_players_query.count()
        
        # Giocatori attualmente iscritti a prove con iscrizioni aperte
        active_inscriptions_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Prova, Inscription.prova_id == Prova.id)
            .filter(
                Prova.tournament_id == tournament_id,
                Prova.status == 'inscription'  # Solo prove con iscrizioni aperte
            )
        )
        currently_inscribed_players = active_inscriptions_query.count()
        
        # Match totali completati in tutte le prove
        completed_matches_query = (
            db.session.query(func.count(Match.id))
            .join(Prova, Match.prova_id == Prova.id)
            .filter(
                Prova.tournament_id == tournament_id,
                Match.status == 'completed'
            )
        )
        total_completed_matches = completed_matches_query.scalar() or 0
        
        # Rack totali giocati (somma dei punteggi di tutti i match completati)
        rack_sum_query = (
            db.session.query(
                func.sum(Match.player1_score + Match.player2_score)
            )
            .join(Prova, Match.prova_id == Prova.id)
            .filter(
                Prova.tournament_id == tournament_id,
                Match.status == 'completed'
            )
        )
        total_racks_played = rack_sum_query.scalar() or 0
        
        return {
            'total_unique_players': total_unique_players,
            'currently_inscribed_players': currently_inscribed_players,
            'total_completed_matches': total_completed_matches,
            'total_racks_played': total_racks_played
        }
    
    @read_only(domain="tournament")
    def calculate_general_classification(self, tournament_id: int) -> List[tuple]:
        """Calcola la classifica generale del torneo basata su tutte le prove completate."""
        from models.competition.models import Prova
        from models.classification.models import RoundClassification
        from models.tournament.models import Tournament
        from models.user.models import User
        from sqlalchemy import func
        
        # Trova il torneo per verificare il tipo
        tournament = db.session.query(Tournament).filter_by(id=tournament_id).first()
        if not tournament:
            return []
        
        # Trova tutte le prove completate del torneo (incluse quelle "playing" ma finite)
        all_provas = (
            db.session.query(Prova)
            .filter_by(tournament_id=tournament_id)
            .filter(Prova.status.in_(['completed', 'playing']))
            .all()
        )
        
        # Filtra le prove che sono realmente completate
        completed_provas = []
        for prova in all_provas:
            if prova.status == 'completed':
                completed_provas.append(prova)
            elif prova.status == 'playing' and prova.current_round > prova.rounds_count:
                # Prova con tutti i round completati
                completed_provas.append(prova)
        
        if not completed_provas:
            return []
        
        # Raccoglie tutti i risultati per giocatore
        player_totals = {}
        
        for prova in completed_provas:
            # Ottieni la classifica finale di questa prova (ultimo turno)
            final_round = prova.rounds_count
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(prova_id=prova.id, round_number=final_round)
                .order_by(RoundClassification.position)
                .all()
            )
            
            for classification in classifications:
                user_id = classification.user_id
                if user_id not in player_totals:
                    player_totals[user_id] = {
                        'username': classification.user.username,
                        'total_matches_won': 0,
                        'total_rack_difference': 0,
                        'participations': 0
                    }
                
                # Per tornei Amalfi: somma match vinti e differenza rack
                player_totals[user_id]['total_matches_won'] += classification.matches_won or 0
                player_totals[user_id]['total_rack_difference'] += classification.rack_difference or 0
                player_totals[user_id]['participations'] += 1
        
        # Per tornei Amalfi: ordina per match vinti (decrescente), poi per differenza rack (decrescente)
        if tournament.tournament_type == 'Amalfi':
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]['total_matches_won'],  # Prima i match vinti
                    -x[1]['total_rack_difference']  # Poi la differenza rack
                )
            )
        else:
            # Per altri tipi di torneo, usa il sistema a punti
            position_points = {
                1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1, 10: 1
            }
            # Calcola punti per giocatore (logica precedente)
            for prova in completed_provas:
                final_round = prova.rounds_count
                classifications = (
                    db.session.query(RoundClassification)
                    .filter_by(prova_id=prova.id, round_number=final_round)
                    .order_by(RoundClassification.position)
                    .all()
                )
                
                for classification in classifications:
                    user_id = classification.user_id
                    if 'total_points' not in player_totals[user_id]:
                        player_totals[user_id]['total_points'] = 0
                    
                    points = position_points.get(classification.position, 0)
                    player_totals[user_id]['total_points'] += points
            
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1].get('total_points', 0),
                    -x[1]['total_rack_difference'],
                    -x[1]['total_matches_won']
                )
            )
        
        # Aggiungi posizioni e restituisci nel formato richiesto
        result = []
        for position, (user_id, data) in enumerate(sorted_players, 1):
            result.append((position, data))
        
        return result


# -----------------------------
# Funzione *pura* per lo stato derivato del Torneo
# -----------------------------


def compute_tournament_status(tournament: Tournament) -> str:
    """Calcola lo stato derivato del torneo in base agli stati delle Prove.

    Regole (soft, aderenti al comportamento attuale):
    - Se non ci sono Prove → SETUP
    - Se almeno una Prova è in PLAYING → IN_PROGRESS
    - Altrimenti, se almeno una Prova è in INSCRIPTION → REGISTRATION_OPEN
    - Altrimenti, se tutte le Prove esistono e sono COMPLETED → COMPLETED
    - In tutti gli altri casi → SETUP

    Ritorna la stringa dello stato (compat con UI/template esistenti).
    """
    provas = getattr(tournament, "provas", []) or []
    if not provas:
        return TournamentStatus.SETUP.value

    # Normalizza valori (stringhe) e valuta
    values = [getattr(p, "status", ProvaStatus.SETUP.value) for p in provas]

    if any(v == ProvaStatus.PLAYING.value for v in values):
        return TournamentStatus.IN_PROGRESS.value
    if any(v == ProvaStatus.INSCRIPTION.value for v in values):
        return TournamentStatus.REGISTRATION_OPEN.value
    if all(v == ProvaStatus.COMPLETED.value for v in values):
        return TournamentStatus.COMPLETED.value

    return TournamentStatus.SETUP.value


__all__ = ["TournamentService", "compute_tournament_status"]
