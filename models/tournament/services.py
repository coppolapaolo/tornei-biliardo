"""
Module: models/tournament/services
Purpose: Service layer per il dominio Tournament + funzione pura di calcolo
         dello stato derivato del torneo.
Data Structures: TournamentService, compute_tournament_status
Dependencies: models.base.db, models.tournament.models, models.status_enum
ADR Reference: docs/ADR/ADR-0018-state-machine-and-status-enums.md
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
        """Restituisce i tornei attivi (campo booleano `is_active`)."""
        return Tournament.query.filter_by(is_active=True).all()

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
