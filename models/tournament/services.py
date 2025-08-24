"""
Module: models/tournament/services
Purpose: Service layer per il dominio Tournament + funzione pura di calcolo
         dello stato derivato del torneo.
Data Structures: TournamentService, compute_tournament_status
Dependencies: models.base.db, models.tournament.models, models.status_enum
"""

from __future__ import annotations

from typing import List
from sqlalchemy.exc import IntegrityError

from models.base import db
from models.status_enum import TournamentStatus, ProvaStatus
from .models import Tournament


class TournamentService:
    """Operazioni di business sui Tornei (API di base conservate)."""

    @staticmethod
    def create_tournament(name: str, **kwargs) -> Tournament:
        """Crea e persiste un torneo (API compatibile con test esistenti)."""
        tournament = Tournament(name=name, **kwargs)
        db.session.add(tournament)
        db.session.commit()
        return tournament

    @staticmethod
    def get_active_tournaments() -> List[Tournament]:
        """Restituisce i tornei attivi (non soft-deleted)."""
        return Tournament.get_active_tournaments().all()

    @staticmethod
    def delete_tournament(tournament_id: int) -> None:
        """
        Cancella un torneo rispettando le regole di dominio e garantendo atomicità.
        - Blocca se esistono iscrizioni (regola attuale in Tournament.can_be_deleted()).
        - Esegue il delete con cascade ORM/DB.
        """
        tournament = Tournament.query.get_or_404(tournament_id)
        if not tournament.can_be_deleted():
            # Regola di dominio esistente: iscrizioni presenti ⇒ non cancellabile
            raise ValueError("Torneo non cancellabile: esistono iscrizioni.")

        db.session.delete(tournament)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # Propaga: la route mapperà su HTTP 409 con messaggio user-friendly
            raise
    
    @staticmethod
    def soft_delete_tournament(tournament_id: int, reason: str = None) -> bool:
        """
        Perform soft delete on tournament with played matches.
        Returns True if successful, False if already deleted.
        """
        tournament = Tournament.query.get_or_404(tournament_id)
        
        if tournament.is_deleted:
            return False
            
        success = tournament.soft_delete(reason)
        if success:
            db.session.commit()
        return success
    
    @staticmethod
    def restore_tournament(tournament_id: int) -> bool:
        """
        Restore a soft-deleted tournament.
        Returns True if successful, False if not deleted.
        """
        tournament = Tournament.query.get_or_404(tournament_id)
        
        if not tournament.is_deleted:
            return False
            
        success = tournament.restore()
        if success:
            db.session.commit()
        return success
    
    @staticmethod
    def get_deleted_tournaments() -> List[Tournament]:
        """Get all soft-deleted tournaments."""
        return Tournament.get_deleted_tournaments().all()
    
    @staticmethod
    def permanently_delete_tournament(tournament_id: int) -> None:
        """
        Permanently delete a tournament (hard delete).
        Only allowed if no matches have been played.
        """
        tournament = Tournament.query.get_or_404(tournament_id)
        
        if not tournament.can_be_hard_deleted():
            raise ValueError("Cannot permanently delete tournament with played matches")
            
        db.session.delete(tournament)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise


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
