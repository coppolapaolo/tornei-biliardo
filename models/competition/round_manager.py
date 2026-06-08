"""
Module: models/competition/round_manager.py
Purpose: Advanced round management with locking and state control
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
from enum import Enum

from flask_babel import lazy_gettext as _

from models.base import db
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService
from models.tiebreaker.models import Tiebreaker, TiebreakerStatus
from models.transaction.manager import transactional


class RoundLockStatus(Enum):
    """Round lock status for advanced management."""

    UNLOCKED = "unlocked"
    LOCKED = "locked"


class AdvancedRoundManager:
    """Advanced round management with locking and modification control."""

    @staticmethod
    def get_round_lock_status(gara_id: int, round_number: int) -> RoundLockStatus:
        """Determine the lock status of a specific round.

        Business Rule: Match modification is allowed based on strategy behavior
        configured in models/matchmaking/configuration.py (StrategyBehaviorConfig).

        Strategies with supports_round_locking=True (Amalfi, Round-Robin, Elimination):
        - Only the current active round (highest with matches) is unlocked
        - Past rounds are locked to maintain historical integrity

        Strategies with supports_round_locking=False (Random):
        - ALL rounds are unlocked (matches can be played in any order)
        - This is because Random creates all rounds at startup
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Return special lock status for non-playing gare (with reason encoded)
        if gara.status != GaraStatus.PLAYING.value:
            # Return LOCKED but caller can check gara.status for reason
            return RoundLockStatus.LOCKED

        # Check strategy behavior for round locking support
        # Uses gara.supports_round_locking() which delegates to StrategyBehaviorConfig
        if not gara.supports_round_locking():
            return RoundLockStatus.UNLOCKED

        # Strategies with round locking: only the active round is unlocked
        # Find the highest round that has matches (the actual active round)
        highest_round_with_matches = (
            db.session.query(db.func.max(Match.round_number))
            .filter(Match.gara_id == gara_id)
            .scalar()
        ) or 0

        # The active round is the highest round with matches
        # This is what should be unlocked
        active_round = highest_round_with_matches

        # Fallback: if gara.current_round is higher (shouldn't happen normally),
        # use it instead
        if gara.current_round > active_round:
            active_round = gara.current_round

        # Unlock only the active round
        if round_number == active_round:
            return RoundLockStatus.UNLOCKED

        return RoundLockStatus.LOCKED

    @staticmethod
    def can_modify_match(match_id: int) -> Tuple[bool, str]:
        """Check if a match can be modified based on round locking rules."""
        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato"

        # Handle matches without gara (standalone)
        if not match.gara_id:
            return True, ""  # Standalone matches are always modifiable

        gara = db.session.get(Gara, match.gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Check gara status first for better error messages
        if gara.status != GaraStatus.PLAYING.value:
            if gara.status == GaraStatus.COMPLETED.value:
                return False, "La gara è già completata"
            elif gara.status == GaraStatus.INSCRIPTION.value:
                return False, "La gara è ancora in fase di iscrizione"
            else:
                return False, f"La gara non è in corso (stato: {gara.status})"

        lock_status = AdvancedRoundManager.get_round_lock_status(
            match.gara_id, match.round_number
        )

        if lock_status == RoundLockStatus.LOCKED:
            return (
                False,
                "Il turno è bloccato perché un turno successivo è già iniziato",
            )

        # ADR-026 residuo: lo spareggio (SSR/rally/playoff) certifica
        # implicitamente l'integrità dei match della gara. Qualsiasi
        # tiebreaker in stato != CANCELLED blocca il reset; il director
        # deve prima cancellare lo spareggio per modificare i match.
        if AdvancedRoundManager._gara_has_active_tiebreaker(gara.id):
            return (
                False,
                str(
                    _(
                        "Gara certificata da spareggio: annulla prima lo "
                        "spareggio per modificare i match"
                    )
                ),
            )

        return True, ""

    @staticmethod
    def _gara_has_active_tiebreaker(gara_id: int) -> bool:
        """True se la gara ha almeno un `Tiebreaker` non-CANCELLED.

        Implementa la semantica ADR-026 "SSR certifica i risultati":
        finché esiste uno spareggio non annullato, i match non possono
        essere modificati né il round cancellato. Usato sia da
        `can_modify_match` (single-match reset) che da `cancel_round`
        (round cancellation) per coerenza.

        Scope del blocco:
        - `Tiebreaker.gara_id == gara_id` — spareggio di gara (SSR/rally)
        - `Tiebreaker.campionato_id == gara.campionato_id` se la gara
          appartiene a un campionato — spareggio campionato-level
          (playoff match fra gare) ancora non annullato: modificare
          un match della gara sottostante invaliderebbe la ranking che
          ha portato al playoff
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False

        filters = [Tiebreaker.gara_id == gara_id]
        if gara.campionato_id is not None:
            filters.append(Tiebreaker.campionato_id == gara.campionato_id)

        return (
            db.session.query(Tiebreaker.id)
            .filter(
                db.or_(*filters),
                Tiebreaker.status != TiebreakerStatus.CANCELLED.value,
            )
            .first()
            is not None
        )

    @staticmethod
    @transactional(domain="competition")
    def reset_match_with_validation(match_id: int) -> Tuple[bool, str]:
        """Reset a match with validation, classification updates and round progression.

        Business Rules:
        - Validates round locking: blocked if subsequent rounds exist
        - Recalculates all classifications for affected rounds
        - Updates round progression (may decrement current_round)
        - Respects table_assignment for match state

        Returns:
            Tuple[bool, str]: (success, message)
                success=False if round is locked or error occurs
                message contains reason for failure or success confirmation

        Use Case 8 Requirement:
            Match modification blocked when subsequent rounds exist
            to maintain tournament integrity.
        """
        from models.match.services import RackService

        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato"

        # Always validate modification permission (no override)
        can_modify, reason = AdvancedRoundManager.can_modify_match(match_id)
        if not can_modify:
            return False, reason

        # Reset the match
        RackService.reset_match_complete(match_id)

        # Recalculate classifications for affected rounds
        AdvancedRoundManager._recalculate_affected_classifications(
            match.gara_id, match.round_number
        )

        # Update round progression if needed
        AdvancedRoundManager._update_round_progression_after_reset(
            match.gara_id, match.round_number
        )

        # Transaction managed by @transactional decorator
        return True, "Match resettato con successo"

    @staticmethod
    @transactional(domain="competition")
    def cancel_round(gara_id: int, round_number: int) -> Tuple[bool, str]:
        """Cancel an entire round with proper validation.

        Business Rules:
        - Can only cancel current round or future rounds
        - Cannot cancel if matches have partial results
        - Deletes all matches and racks in the round
        - Recalculates classifications for previous rounds

        Returns:
            Tuple[bool, str]: (success, message)
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # ADR-026: uno spareggio attivo certifica la gara. cancel_round
        # cancellerebbe tutti i match del round — incoerente con il blocco
        # del reset single-match. Il director deve annullare lo spareggio
        # prima di poter cancellare qualsiasi round.
        if AdvancedRoundManager._gara_has_active_tiebreaker(gara.id):
            return (
                False,
                str(
                    _(
                        "Gara certificata da spareggio: annulla prima lo "
                        "spareggio per cancellare il turno"
                    )
                ),
            )

        # Only allow canceling the current round or higher
        if round_number < gara.current_round:
            return False, "Non puoi cancellare un turno precedente a quello corrente"

        # Get all matches in the round
        round_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).all()

        if not round_matches:
            return False, f"Nessun match trovato per il turno {round_number}"

        # Check if any matches have partial results (ADR-026 extended scope).
        # A match "has partial results" only when at least one player has won
        # a rack (score > 0). Both `None` and `0` mean "no result": `None` for
        # never-played matches (column nullable until first flush), `0` for
        # reset matches (reset_match_complete zeroes scores, preserving pair
        # per ADR-026). Previous check `is not None` incorrectly blocked
        # cancel_round on reset matches, which reset_match_complete had
        # worked around by pre-cleaning encounters — a workaround removed
        # by ADR-026.
        # Bye matches are excluded: the bye's `player1_score = round_distance`
        # is a persistence convention for classification machinery, not a
        # user-entered result. Conceptually the bye is always "in initial
        # state" (no racks to play), so it does not count as partial result.
        # Walkovers (2-player forfeit, trio walkover) remain included — they
        # represent human actions (iscritto forfeit) and must be reset
        # deliberately before round cancellation.
        matches_with_results = [
            m
            for m in round_matches
            if not m.is_bye
            and ((m.player1_score or 0) > 0 or (m.player2_score or 0) > 0)
        ]
        if matches_with_results:
            return (
                False,
                "Alcuni match hanno già risultati parziali. "
                "Reset i match prima di cancellare il turno.",
            )

        # Delete all matches in the round
        for match in round_matches:
            # Delete associated racks first (bulk delete via query)
            from models.match.models import Rack

            Rack.query.filter_by(match_id=match.id).delete()
            db.session.delete(match)

        # Delete classifications for this round
        RoundClassification.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).delete()

        # Delete PlayerEncounters for this round to maintain anti-rematch consistency
        from models.classification.models import PlayerEncounter

        PlayerEncounter.delete_round_encounters(gara_id, round_number)

        # Update gara current round if we cancelled the current round
        if round_number == gara.current_round:
            gara.current_round = max(0, round_number - 1)

            # Update gara status if going back to round 0
            if gara.current_round == 0:
                gara.status = GaraStatus.INSCRIPTION.value

        # Transaction managed by @transactional decorator
        return True, f"Turno {round_number} cancellato con successo"

    @staticmethod
    @transactional(domain="competition")
    def bulk_reset_round_matches(
        gara_id: int, round_number: int
    ) -> Tuple[bool, str, Dict[str, int]]:
        """Reset all matches in a round with statistics."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata", {}

        # Get all completed matches in the round
        completed_matches = Match.query.filter_by(
            gara_id=gara_id,
            round_number=round_number,
            status=MatchStatus.COMPLETED.value,
        ).all()

        if not completed_matches:
            return (
                False,
                f"Nessun match completato trovato nel turno {round_number}",
                {},
            )

        reset_count = 0
        error_count = 0
        errors = []

        for match in completed_matches:
            try:
                success, message = AdvancedRoundManager.reset_match_with_validation(
                    match.id
                )
                if success:
                    reset_count += 1
                else:
                    error_count += 1
                    errors.append(f"Match {match.id}: {message}")
            except Exception as e:
                # Inner @transactional rolls back the savepoint;
                # we record the error and continue with remaining matches
                error_count += 1
                errors.append(f"Match {match.id}: {str(e)}")

        # Update gara status if all matches were reset
        if reset_count > 0:
            # Recalculate round progression
            AdvancedRoundManager._update_round_progression_after_reset(
                gara_id, round_number
            )

        # Transaction managed by @transactional decorator

        stats = {
            "reset_count": reset_count,
            "error_count": error_count,
            "total_matches": len(completed_matches),
        }

        if error_count == 0:
            return True, f"Tutti i {reset_count} match sono stati resettati", stats
        else:
            message = f"{reset_count} match resettati, {error_count} errori"
            return False, message, stats

    @staticmethod
    def get_round_modification_summary(gara_id: int) -> Dict[int, Dict[str, Any]]:
        """Get a summary of which rounds can be modified and their status."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return {}

        rounds_summary = {}

        # Get all rounds with matches
        rounds_with_matches = (
            db.session.query(Match.round_number)
            .filter_by(gara_id=gara_id)
            .distinct()
            .all()
        )

        for (round_number,) in rounds_with_matches:
            lock_status = AdvancedRoundManager.get_round_lock_status(
                gara_id, round_number
            )

            # Get round matches
            round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number
            ).all()

            # Count both COMPLETED and VALIDATED as finished
            completed_matches = [
                m
                for m in round_matches
                if m.status
                in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
            ]
            pending_matches = [
                m for m in round_matches if m.status == MatchStatus.PENDING.value
            ]

            # Check if matches can be modified
            modifiable_matches = []
            for match in round_matches:
                can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
                if can_modify:
                    modifiable_matches.append(match.id)

            rounds_summary[round_number] = {
                "lock_status": lock_status.value,
                "total_matches": len(round_matches),
                "completed_matches": len(completed_matches),
                "pending_matches": len(pending_matches),
                "modifiable_matches": len(modifiable_matches),
                "can_cancel_round": lock_status != RoundLockStatus.LOCKED,
                "can_bulk_reset": len(completed_matches) > 0
                and lock_status != RoundLockStatus.LOCKED,
            }

        return rounds_summary

    @staticmethod
    def _recalculate_affected_classifications(
        gara_id: int, affected_round: int
    ) -> None:
        """Recalculate classifications for affected rounds after match modification."""

        # Recalculate classification for the affected round and all subsequent rounds
        max_round = (
            db.session.query(db.func.max(Match.round_number))
            .filter_by(gara_id=gara_id)
            .scalar()
            or 0
        )

        for round_num in range(affected_round, max_round + 1):
            # Rimuovi la classifica esistente del round prima di ricalcolare: il
            # recalc fa upsert dai Match ma NON elimina i giocatori che dopo il
            # reset non hanno più match qualificati, quindi la delete preventiva
            # pulisce le righe stale.
            RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=round_num
            ).delete()

            # Ricalcola dai risultati dei match. NB: la vecchia implementazione
            # chiamava get_round_standings (che riquery la RoundClassification
            # appena SVUOTATA → sempre vuota) e trattava gli oggetti ORM come
            # dict (player_data["user_id"]) → TypeError ingoiato dal bare except,
            # lasciando la gara senza classifica. Il metodo canonico aggrega
            # invece dai Match e fa create/update idempotente.
            #
            # Nessun try/except: un errore deve propagarsi al @transactional del
            # chiamante (reset_match_with_validation) e fare rollback, invece di
            # committare le delete e segnalare comunque "successo".
            RoundClassificationService.calculate_and_save_round_classification(
                gara_id, round_num
            )

    @staticmethod
    def _update_round_progression_after_reset(
        gara_id: int, affected_round: int
    ) -> None:
        """Update round progression after match resets.

        Important: current_round should represent the HIGHEST round with matches
        (the active round), NOT the last fully completed round.

        This function:
        1. Does NOT delete subsequent rounds (they may have been started intentionally)
        2. Sets current_round to the highest round that has matches
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return

        # Find the highest round that has matches
        # This is the "active round" - the one being played
        highest_round_with_matches = (
            db.session.query(db.func.max(Match.round_number))
            .filter(Match.gara_id == gara_id)
            .scalar()
        ) or 0

        # Set current_round to the highest round with matches
        # This ensures the active round stays unlocked for modifications
        if highest_round_with_matches > 0:
            gara.current_round = highest_round_with_matches
        # Note: We do NOT automatically delete subsequent rounds.
        # If a director started round 2, it should stay even if round 1 is modified.
