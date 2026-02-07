"""
RackService: Rack-level scoring, validation, and match reset logic.

Split from services.py for maintainability (Round 3 P4).
"""

from __future__ import annotations

from typing import Optional

from models.base import db
from models.status_enum import MatchStatus
from .models import Match, Rack
from models.transaction.manager import transactional


class RackService:
    """Service per gestione rack con business logic completa."""

    @staticmethod
    @transactional(domain="match")
    def add_rack_result(
        match_id: int,
        rack_number: int,
        winner_id: int,
        reported_by_id: int,
        *,
        confirmed_by_player: bool = False,
        validated_by_admin: bool = False,
        admin_note: Optional[str] = None,
        bypass_validation: bool = False,
    ) -> Rack:
        # Check if rack can be added (match not at max)
        match = db.session.get(Match, match_id)
        if match and not bypass_validation and not match.can_add_rack():
            raise ValueError(
                "Cannot add rack: match has reached maximum and needs validation"
            )

        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            confirmed_by_player=confirmed_by_player,
            validated_by_admin=validated_by_admin,
            admin_note=admin_note,
        )
        db.session.add(rack)

        # Update match scores when rack is added
        if match:
            # Update match scores based on winner
            if winner_id == match.player1_id:
                match.player1_score = (match.player1_score or 0) + 1
            elif winner_id == match.player2_id:
                match.player2_score = (match.player2_score or 0) + 1

            # Transizione soft: se il match è pending, portalo a playing
            if (match.status or MatchStatus.PENDING.value) == MatchStatus.PENDING.value:
                match.status = MatchStatus.PLAYING.value

            db.session.add(match)

        return rack

    @staticmethod
    @transactional(domain="match")
    def add_rack_with_score_update(
        match_id: int,
        winner_id: int,
        reported_by_id: int = 1,
        validated_by_admin: bool = True,
    ) -> dict:
        """Add rack with score update (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.add_rack_with_score_update(
            match_id, winner_id, reported_by_id, validated_by_admin
        )

    @staticmethod
    @transactional(domain="match")
    def set_match_result_direct(
        match_id: int, player1_score: int, player2_score: int
    ) -> None:
        """Set match result directly (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.set_match_result_direct(
            match_id, player1_score, player2_score
        )

    @staticmethod
    @transactional(domain="match")
    def reset_match_complete(match_id: int) -> None:
        """Reset completo di una partita eliminando tutti i rack.

        Il match viene riportato allo stato appropriato in base all'assegnazione
        del tavolo: PLAYING se ha un tavolo, PENDING altrimenti.

        IMPORTANT: Also deletes the PlayerEncounter record to maintain
        anti-rematch consistency. This ensures that when a match is reset,
        the players can be paired again in future rounds.

        For Trio matches, delegates to TrioScoringService.reset() which handles
        TrioRack deletion and trio-specific state reset.
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi resettare una partita bye!")

        # Handle Trio matches separately via TrioScoringService
        if match.is_trio and match.trio_match:
            from .trio_scoring_service import TrioScoringService
            TrioScoringService.reset(match.trio_match.id)
            return

        # Regular match reset: elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Delete PlayerEncounter to maintain anti-rematch consistency
        # This ensures players can be paired again after match reset
        if match.player2_id:  # Only for non-bye matches
            from models.classification.models import PlayerEncounter
            PlayerEncounter.delete_encounter(
                gara_id=match.gara_id,
                player1_id=match.player1_id,
                player2_id=match.player2_id
            )

        # Reset match scores
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None

        # Reset player confirmations
        match.player1_confirmed = False
        match.player2_confirmed = False
        match.player1_confirmed_at = None
        match.player2_confirmed_at = None

        # Stato intelligente basato su table_assignment:
        # - Se ha tavolo assegnato → PLAYING (pronto per essere giocato)
        # - Se non ha tavolo → PENDING (in attesa di assegnazione)
        if match.table_assignment:
            match.status = MatchStatus.PLAYING.value
        else:
            match.status = MatchStatus.PENDING.value

        # Clear validation flags se presenti
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = False

        # Clear forfeit flags on inscriptions for both players
        # This allows the player to continue competing after match reset
        from models.competition.models import Inscription
        for player_id in [match.player1_id, match.player2_id]:
            if player_id:  # player2_id could be None for bye matches
                inscription = (
                    db.session.query(Inscription)
                    .filter_by(
                        user_id=player_id,
                        gara_id=match.gara_id,
                        is_forfeit=True
                    )
                    .first()
                )
                if inscription:
                    inscription.is_forfeit = False
                    inscription.forfeit_at = None

        db.session.add(match)

    @staticmethod
    @transactional(domain="match")
    def remove_rack_admin(rack_id: int) -> dict:
        """Rimuove un rack e aggiorna il punteggio del match (admin).

        Returns:
            Dict con stato aggiornato del match
        """
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)
        match = rack.match

        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id

        # Rimuovi il rack
        db.session.delete(rack)

        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

        # Controlla sempre se il punteggio giustifica ancora il winner_id
        should_clear_winner = False
        if match.gara.is_race_to:
            winning_score = match.gara.distance_config.get_winning_racks()
            if max(match.player1_score, match.player2_score) < winning_score:
                should_clear_winner = True
        else:  # esatto numero
            if (match.player1_score + match.player2_score) < match.gara.distance:
                should_clear_winner = True

        if should_clear_winner:
            match.winner_id = None
            match.reset_confirmations()
            # Se era completed, rimettilo in playing
            if match.status == MatchStatus.COMPLETED.value:
                from .match_service import MatchService
                MatchService.to_playing(match.id)

        return {
            "success": True,
            "message": "Rack rimosso (Admin)",
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    @transactional(domain="match")
    def validate_rack_admin(rack_id: int) -> None:
        """Valida un rack (admin)."""
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)

        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = (
            True  # Automaticamente confermato se validato dall'admin
        )

    @staticmethod
    @transactional(domain="match")
    def remove_last_rack(match_id: int) -> Optional[Rack]:
        last = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        if last:
            db.session.delete(last)
        return last
