"""
Module: models/match/services
Purpose: Service layer per il dominio Match (Match, Rack, MatchResult, TrioMatch)
         + state machine centralizzata per gli stati del Match.
Data Structures: MatchService, RackService, MatchResultService
Dependencies: models.base.db, models.match.models, models.status_enum
ADR Reference: docs/ADR/ADR-0018-state-machine-and-status-enums.md

Nota sprint 4: aggiunte API di transizione di stato; preservati nomi/classi esistenti
per compatibilità con i test di separazione.
"""

from __future__ import annotations

from typing import List, Optional

from models.base import db
from models.status_enum import MatchStatus
from .models import Match, Rack, TrioMatch


class InvalidTransitionError(ValueError):
    """Errore per transizioni di stato non ammesse."""


class MatchService:
    """Operazioni di business sui Match + state machine facade."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    def create_match(
        prova_id: int,
        round_number: int,
        player1_id: int,
        player2_id: Optional[int] = None,
        is_bye: bool = False,
    ) -> Match:
        """Crea un match. Imposta lo stato iniziale a 'pending'."""
        match = Match(
            prova_id=prova_id,
            round_number=round_number,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=is_bye,
            status=MatchStatus.PENDING.value,
        )
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def get_matches_by_prova(prova_id: int) -> List[Match]:
        return Match.query.filter_by(prova_id=prova_id).all()

    @staticmethod
    def create_trio_match(match_id: int, player3_id: int) -> TrioMatch:
        """Crea l'entità TrioMatch e marca il match come trio (compat)."""
        trio = TrioMatch(match_id=match_id, waiting_player_id=player3_id)
        db.session.add(trio)
        match = db.session.get(Match, match_id)
        if match is not None:
            match.is_trio = True  # compat con modello esistente
            db.session.add(match)
        db.session.commit()
        return trio

    # -----------------------------
    # STATE MACHINE FACADE
    # -----------------------------
    @staticmethod
    def to_playing(match_id: int) -> Match:
        """pending/completed → playing
        (riapertura consentita in flussi admin o dopo rimozione rack)"""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if (match.status or MatchStatus.PENDING.value) not in (
            MatchStatus.PENDING.value,
            MatchStatus.COMPLETED.value,
        ):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → playing"
            )
        match.status = MatchStatus.PLAYING.value
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def to_completed(match_id: int) -> Match:
        """playing → completed (consente anche pending →
        completed per amministratore)."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if match.status not in (MatchStatus.PLAYING.value, MatchStatus.PENDING.value):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → completed"
            )
        match.status = MatchStatus.COMPLETED.value
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def reset_to_pending(match_id: int, clear_validation: bool = True) -> Match:
        """Qualsiasi → pending. Opzione per azzerare flag di validazione admin.
        Non rimuove i rack (responsabilità di RackService).
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        match.status = MatchStatus.PENDING.value
        if clear_validation and hasattr(match, "validated_by_admin"):
            try:
                match.validated_by_admin = False
            except Exception:
                pass
        db.session.add(match)
        db.session.commit()
        return match


class RackService:
    """Placeholder compatibile per future estrazioni di logica relativa ai rack."""

    @staticmethod
    def add_rack_result(
        match_id: int,
        rack_number: int,
        winner_id: int,
        reported_by_id: int,
        *,
        confirmed_by_player: bool = False,
        validated_by_admin: bool = False,
    ) -> Rack:
        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            confirmed_by_player=confirmed_by_player,
            validated_by_admin=validated_by_admin,
        )
        db.session.add(rack)
        db.session.commit()
        # Transizione soft: se il match è pending, portalo a playing
        match = db.session.get(Match, match_id)
        if (
            match
            and (match.status or MatchStatus.PENDING.value) == MatchStatus.PENDING.value
        ):
            match.status = MatchStatus.PLAYING.value
            db.session.add(match)
            db.session.commit()
        return rack

    @staticmethod
    def remove_last_rack(match_id: int) -> Optional[Rack]:
        last = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        if last:
            db.session.delete(last)
            db.session.commit()
        return last


class MatchResultService:
    """Placeholder per gestione risultati/validazioni match."""

    @staticmethod
    def validate_by_admin(match_id: int) -> Match:
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = True
            db.session.add(match)
            db.session.commit()
        return match

    @staticmethod
    def submit_result(match_id: int, winner_id: int) -> Match:
        """
        Imposta il vincitore del match e porta lo stato a 'completed'
        tramite la state machine.
        Non tocca Trio né logiche rack: è il percorso 'set result' da form.
        """
        match: Optional[Match] = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # winner deve appartenere al match (2-players match)
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("winner_id non appartiene ai giocatori del match")

        # set vincitore e commit prima della transizione
        match.winner_id = winner_id
        db.session.add(match)
        db.session.commit()

        # transizione centralizzata
        # import locale per evitare cicli
        from models.match.services import MatchService
        MatchService.to_completed(match.id)

        # ricarica o restituisci l'oggetto aggiornato
        return match


__all__ = [
    "MatchService",
    "RackService",
    "MatchResultService",
    "InvalidTransitionError",
]
