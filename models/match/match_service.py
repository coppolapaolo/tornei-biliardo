"""
MatchService: Business logic and state machine facade for Match lifecycle.

Split from services.py for maintainability (Round 3 P4).
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from models.shared.operation_result import OperationResult

from models.base import db, utc_now
from models.status_enum import MatchStatus
from .models import Match, Rack, TrioMatch
from models.transaction.manager import transactional


class MatchService:
    """Operazioni di business sui Match + state machine facade."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    @transactional(domain="match")
    def create_match(
        gara_id: int,
        round_number: int,
        player1_id: int,
        player2_id: Optional[int] = None,
        is_bye: bool = False,
    ) -> Match:
        """Crea un match. Imposta lo stato iniziale a 'pending'."""
        # Get gara to fetch the distance
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        match = Match(
            gara_id=gara_id,
            round_number=round_number,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=is_bye,
            status=MatchStatus.PENDING.value,
            match_distance=gara.distance,
        )
        db.session.add(match)
        return match

    @staticmethod
    def get_matches_by_gara(gara_id: int) -> List[Match]:
        return Match.query.filter_by(gara_id=gara_id).all()

    @staticmethod
    @transactional(domain="match")
    def create_trio_match(match_id: int, player3_id: int) -> TrioMatch:
        """Crea l'entità TrioMatch e marca il match come trio (compat)."""
        trio = TrioMatch(match_id=match_id, waiting_player_id=player3_id)
        db.session.add(trio)
        match = db.session.get(Match, match_id)
        if match is not None:
            match.is_trio = True  # compat con modello esistente
            db.session.add(match)
        return trio

    # -----------------------------
    # STATE MACHINE FACADE
    # Delegates to MatchStateService
    # -----------------------------
    @staticmethod
    def to_playing(match_id: int) -> Match:
        """pending/completed → playing (delegates to MatchStateService)."""
        from .state_service import MatchStateService

        return MatchStateService.to_playing(match_id)

    @staticmethod
    def to_completed(match_id: int, closed_by_director: bool = False) -> Match:
        """playing → completed (delegates to MatchStateService)."""
        from .state_service import MatchStateService

        return MatchStateService.to_completed(
            match_id, closed_by_director=closed_by_director
        )

    @staticmethod
    @transactional(domain="match")
    def update_times(
        match_id: int,
        start_time_str: Optional[str] = None,
        end_time_str: Optional[str] = None,
    ) -> Match:
        """Update match start and end times.

        Times are provided as HH:MM strings. The method infers the correct date
        based on the gara's date and time, handling midnight crossings.

        Date inference logic:
        - started_at: If start_time < gara.time → next day
        - ended_at: If end_time <= start_time → next day from started_at

        Args:
            match_id: ID of the match to update
            start_time_str: Start time in "HH:MM" format (optional)
            end_time_str: End time in "HH:MM" format (optional)

        Returns:
            The updated Match object

        Raises:
            ValueError: If match not found or times are invalid
        """
        from datetime import time as datetime_time, timedelta

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        gara = match.gara
        if not gara:
            raise ValueError(
                "Match senza gara associata non supportato per update_times"
            )

        gara_date = gara.date
        gara_time = gara.time or datetime_time(0, 0)

        # Parse start_time and calculate started_at
        if start_time_str:
            try:
                parts = start_time_str.split(":")
                start_time = datetime_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                raise ValueError(f"Formato ora non valido: {start_time_str}")

            # If start_time < gara.time → next day
            if start_time < gara_time:
                start_date = gara_date + timedelta(days=1)
            else:
                start_date = gara_date

            match.started_at = datetime.combine(start_date, start_time)

        # Parse end_time and calculate ended_at
        if end_time_str:
            try:
                parts = end_time_str.split(":")
                end_time = datetime_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                raise ValueError(f"Formato ora non valido: {end_time_str}")

            # Base date is started_at.date() if available, else gara.date
            if match.started_at:
                base_date = match.started_at.date()
                # Get start_time for comparison
                start_time_for_cmp = match.started_at.time()
            else:
                base_date = gara_date
                start_time_for_cmp = gara_time

            # If end_time <= start_time → next day
            if end_time <= start_time_for_cmp:
                end_date = base_date + timedelta(days=1)
            else:
                end_date = base_date

            match.ended_at = datetime.combine(end_date, end_time)

        db.session.add(match)
        return match

    @staticmethod
    def add_rack_to_completed_match(
        match_id: int,
        rack_number: int,
        winner_id: int,
        modifier_id: int,
    ) -> "OperationResult":
        """
        Add a rack to a completed match (admin function).

        Args:
            match_id: ID of the match
            rack_number: Rack number to add
            winner_id: ID of the winner of this rack
            modifier_id: ID of the admin making the modification

        Returns:
            OperationResult indicating success or failure
        """
        from models.shared.operation_result import OperationResult, OperationType
        from .rack_service import RackService

        match = db.session.get(Match, match_id)
        if not match:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Check if match is locked
        if match.is_locked or match.round_locked:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match is locked and cannot be modified"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Add the rack
        try:
            RackService.add_rack_result(
                match_id=match_id,
                rack_number=rack_number,
                winner_id=winner_id,
                reported_by_id=modifier_id,
                validated_by_admin=True,
                admin_note=f"Added by admin {modifier_id}",
            )

            return OperationResult.success_result(
                operation_type=OperationType.RESULT_PROCESSING,
                data={
                    "match_id": match_id,
                    "rack_number": rack_number,
                    "winner_id": winner_id,
                    "modifier_id": modifier_id,
                },
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        except Exception as e:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=[str(e)],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

    @staticmethod
    @transactional(domain="match")
    def admin_unlock_match(
        match_id: int,
        admin_id: int,
        unlock_reason: str,
    ) -> "OperationResult":
        """
        Admin override to unlock a match for modifications.

        Args:
            match_id: ID of the match to unlock
            admin_id: ID of the admin performing the unlock
            unlock_reason: Reason for unlocking

        Returns:
            OperationResult indicating success or failure
        """
        from models.shared.operation_result import OperationResult, OperationType

        match = db.session.get(Match, match_id)
        if not match:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Unlock the match
        match.is_locked = False
        match.round_locked = False
        db.session.add(match)

        return OperationResult.success_result(
            operation_type=OperationType.RESULT_PROCESSING,
            data={
                "match_id": match_id,
                "admin_id": admin_id,
                "unlock_reason": unlock_reason,
                "was_locked": True,
            },
            execution_time_ms=0.0,
            affected_domains=["match"],
        )

    @staticmethod
    def apply_batch_corrections(
        gara_id: int,
        corrections: List[Dict[str, Any]],
        admin_id: int,
    ) -> "OperationResult":
        """
        Apply batch corrections to multiple matches.

        Args:
            gara_id: ID of the tournament
            corrections: List of correction dictionaries
            admin_id: ID of the admin performing corrections

        Returns:
            OperationResult with batch correction results
        """
        from models.shared.operation_result import OperationResult, OperationType
        from .rack_service import RackService

        results = []
        errors = []

        for correction in corrections:
            try:
                match_id = correction["match_id"]
                correction_type = correction["correction_type"]
                new_winner_score = correction["new_winner_score"]
                new_loser_score = correction["new_loser_score"]
                reason = correction.get("reason", "Batch correction")

                match = db.session.get(Match, match_id)
                if not match:
                    error_msg = f"Match {match_id} not found"
                    errors.append(error_msg)
                    results.append(
                        {
                            "match_id": match_id,
                            "success": False,
                            "error": error_msg,
                        }
                    )
                    continue

                if match.gara_id != gara_id:
                    error_msg = (
                        f"Match {match_id} does not belong to specified tournament"
                    )
                    errors.append(error_msg)
                    results.append(
                        {
                            "match_id": match_id,
                            "success": False,
                            "error": error_msg,
                        }
                    )
                    continue

                # Apply score correction
                if correction_type == "score_adjustment":
                    # Use existing method to set the result
                    RackService.set_match_result_direct(
                        match_id=match_id,
                        player1_score=new_winner_score,
                        player2_score=new_loser_score,
                    )

                    results.append(
                        {
                            "match_id": match_id,
                            "success": True,
                            "correction_type": correction_type,
                            "new_scores": {
                                "winner": new_winner_score,
                                "loser": new_loser_score,
                            },
                            "reason": reason,
                            "admin_id": admin_id,
                        }
                    )
                else:
                    # Tipo di correzione sconosciuto: senza questo ramo la
                    # correzione veniva silenziosamente saltata e overall_success
                    # restava True (l'admin credeva di aver applicato la modifica).
                    error_msg = (
                        f"Match {match_id}: tipo di correzione sconosciuto "
                        f"'{correction_type}', nessuna modifica applicata"
                    )
                    errors.append(error_msg)
                    results.append(
                        {
                            "match_id": match_id,
                            "success": False,
                            "error": error_msg,
                        }
                    )

            except Exception as e:
                error_msg = str(e)
                errors.append(error_msg)
                results.append(
                    {
                        "match_id": correction.get("match_id", "unknown"),
                        "success": False,
                        "error": error_msg,
                    }
                )

        # Determine overall success
        overall_success = len(errors) == 0

        if overall_success:
            return OperationResult.success_result(
                operation_type=OperationType.RESULT_PROCESSING,
                data={
                    "corrections_applied": len(results),
                    "results": results,
                    "admin_id": admin_id,
                },
                execution_time_ms=0.0,
                affected_domains=["match", "competition"],
            )
        else:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={"results": results},
                errors=errors,
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match", "competition"],
            )

    # ---------------------------------------
    # SIMPLIFIED UX - Delegates to ScoringService
    # ---------------------------------------
    @staticmethod
    def add_rack_for_player(
        match_id: int,
        user_id: int,
        winner_id: int,
        authoritative: bool = False,
    ) -> Rack:
        """Add a rack won by specified player (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.add_rack_for_player(
            match_id, user_id, winner_id, authoritative=authoritative
        )

    @staticmethod
    def remove_rack_for_player(match_id: int, user_id: int, player_id: int) -> None:
        """Remove last rack won by specified player (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.remove_rack_for_player(match_id, user_id, player_id)

    @staticmethod
    def register_lag(
        match_id: int, lag_winner_id: int, first_break_player_id: int
    ) -> None:
        """Esito dell'acchito (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.register_lag(
            match_id, lag_winner_id, first_break_player_id
        )

    @staticmethod
    def toggle_run_out(match_id: int, rack_id: int) -> dict:
        """Marca/smarca un triangolo come runout (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.toggle_run_out(match_id, rack_id)

    @staticmethod
    @transactional(domain="match")
    def confirm_match_result(match_id: int, user_id: int) -> Match:
        """
        Confirm match result by a player (new UX).

        Uses BaseMatchMixin.confirm_result() method.
        When both players confirm, the match is completed and table is reassigned.

        Args:
            match_id: ID of the match
            user_id: ID of player confirming

        Returns:
            The updated Match object

        Raises:
            ValueError: If user not in match or match not ready
        """
        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        # Con la seconda firma la partita si chiude e il tavolo passa alla
        # partita in attesa: lo fa `Match._complete_match_after_confirmation`,
        # che vale per ogni strada che firma, non solo per questa.
        match.confirm_result(user_id)

        return match

    @staticmethod
    @transactional(domain="match")
    def reject_match_result(match_id: int, user_id: int) -> Match:
        """
        Reject match result - removes last rack (new UX).

        Uses BaseMatchMixin.reject_result() method.

        Args:
            match_id: ID of the match
            user_id: ID of player rejecting

        Returns:
            The updated Match object

        Raises:
            ValueError: If user not in match or match not ready
        """
        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.reject_result(user_id)
        return match

    @staticmethod
    def forfeit_match(match_id: int, user_id: int) -> Match:
        """Forfeit match (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.forfeit_match(match_id, user_id)

    # ---------------------------------------
    # MULTI-SET MATCH OPERATIONS
    # ---------------------------------------
    @staticmethod
    @transactional(domain="match")
    def start_next_set(match_id: int):
        """Start the next set in a multi-set match.

        Creates a new Set record and transitions it to 'playing' status.
        If no sets exist yet, creates the first set.

        Args:
            match_id: ID of the match

        Returns:
            The newly created Set

        Raises:
            ValueError: If match not found, not multi-set, or match already complete
        """
        from .set_models import Set

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if not match.is_multi_set:
            raise ValueError("Match non è configurato come multi-set")

        # Check if match is already complete
        match_winning_sets = match.match_distance or 1
        if match.distance_config.is_race_to_sets:
            if (
                match.player1_score >= match_winning_sets
                or match.player2_score >= match_winning_sets
            ):
                raise ValueError("Match già completato")
        else:
            total_sets = match.player1_score + match.player2_score
            if total_sets >= match_winning_sets:
                raise ValueError("Match già completato")

        # Check if current set is complete or doesn't exist
        current_set = match.get_current_set()
        if current_set and current_set.status == MatchStatus.PLAYING.value:
            raise ValueError(f"Set {current_set.set_number} ancora in corso")

        # Determine next set number
        existing_sets = match.sets or []
        next_set_number = len(existing_sets) + 1

        # Get distance from gara or match configuration
        gara = match.gara
        set_distance = gara.distance if gara else 5  # Default to 5 if no gara

        # Create new set
        new_set = Set(
            match_id=match_id,
            set_number=next_set_number,
            distance=set_distance,
            is_race_to=gara.is_race_to if gara else True,
            status="playing",
            started_at=utc_now(),
        )
        db.session.add(new_set)

        # Update match current set number
        match.current_set_number = next_set_number

        # Ensure match is in playing status
        if match.status == MatchStatus.PENDING.value:
            match.status = MatchStatus.PLAYING.value

        db.session.add(match)

        return new_set

    @staticmethod
    @transactional(domain="match")
    def add_rack_to_current_set(match_id: int, winner_id: int):
        """Add a rack to the current set in a multi-set match.

        Args:
            match_id: ID of the match
            winner_id: ID of player who won the rack

        Returns:
            The newly created SetRack

        Raises:
            ValueError: If match not found, not multi-set, no active set, or
                winner invalid
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if not match.is_multi_set:
            raise ValueError("Match non è configurato come multi-set")

        current_set = match.get_current_set()
        if not current_set:
            raise ValueError("Nessun set attivo. Inizia un nuovo set.")

        if current_set.status != MatchStatus.PLAYING.value:
            raise ValueError(f"Set {current_set.set_number} non è in corso")

        # Use Set's add_rack_result method which handles score updates and completion
        rack = current_set.add_rack_result(winner_id=winner_id)

        # Note: Set.add_rack_result calls _check_set_completion which calls
        # match.complete_set() when the set is won, updating match scores

        return rack

    @staticmethod
    @transactional(domain="match")
    def set_current_set_racks(match_id: int, player1_racks: int, player2_racks: int):
        """Porta il set in corso a `player1_racks`–`player2_racks`.

        E' il gesto degli stepper della card del direttore: un tocco cambia un
        numero di uno. Un triangolo in meno toglie **l'ultimo vinto da quel
        giocatore** (non l'ultimo del set, che puo' essere dell'altro) e
        ricompatta la numerazione; uno in piu' passa da `Set.add_rack_result`,
        che chiude il set alla sua distanza e la partita ai set.

        Returns:
            Il set su cui si e' segnato.

        Raises:
            ValidationError: non e' una partita a set, o il punteggio supera la
                distanza del set.
            ConflictError: il set non e' in corso (va iniziato il prossimo).
        """
        from flask_babel import gettext as _

        from models.exceptions import ConflictError, ValidationError

        from .set_models import SetRack

        match = db.session.get(Match, match_id)
        if match is None or not match.is_multi_set:
            raise ValidationError(_("Questa non è una partita a set."))
        corrente = match.get_current_set()
        if corrente is None or corrente.status != MatchStatus.PLAYING.value:
            raise ConflictError(_("Il set non è in corso: inizia il prossimo."))

        distanza = corrente.distance
        if player1_racks < 0 or player2_racks < 0:
            raise ValidationError(_("Punteggio non valido."))
        if corrente.is_race_to:
            fuori = player1_racks > distanza or player2_racks > distanza
            fuori = fuori or (player1_racks == distanza and player2_racks == distanza)
        else:
            fuori = player1_racks + player2_racks > distanza
        if fuori:
            raise ValidationError(
                _("Il set si gioca al %(n)s: il punteggio va oltre.", n=distanza)
            )

        lati = [
            (match.player1_id, "player1_racks", player1_racks),
            (match.player2_id, "player2_racks", player2_racks),
        ]
        # Prima si tolgono i triangoli in piu'.
        for giocatore_id, campo, obiettivo in lati:
            while getattr(corrente, campo) > obiettivo:
                ultimo = (
                    SetRack.query.filter_by(set_id=corrente.id, winner_id=giocatore_id)
                    .order_by(SetRack.rack_number.desc())
                    .first()
                )
                if ultimo is None:
                    setattr(corrente, campo, obiettivo)
                    break
                numero = ultimo.rack_number
                db.session.delete(ultimo)
                db.session.flush()
                dopo = (
                    SetRack.query.filter(
                        SetRack.set_id == corrente.id, SetRack.rack_number > numero
                    )
                    .order_by(SetRack.rack_number.asc())
                    .all()
                )
                for rack in dopo:
                    rack.rack_number -= 1
                    db.session.flush()
                setattr(corrente, campo, getattr(corrente, campo) - 1)

        # Poi quelli che mancano, per ultimo il lato che chiude il set: se lo
        # chiudesse prima, l'altro troverebbe il set gia' finito.
        def chiude(lato) -> bool:
            return corrente.is_race_to and lato[2] >= distanza

        for giocatore_id, campo, obiettivo in sorted(lati, key=chiude):
            while (
                getattr(corrente, campo) < obiettivo
                and corrente.status == MatchStatus.PLAYING.value
            ):
                corrente.add_rack_result(winner_id=giocatore_id)
                db.session.flush()

        db.session.add(corrente)
        db.session.add(match)
        return corrente

    @staticmethod
    @transactional(domain="match")
    def remove_rack_from_current_set(match_id: int) -> None:
        """Remove the last rack from the current set in a multi-set match.

        Args:
            match_id: ID of the match

        Raises:
            ValueError: If match not found, not multi-set, or no racks to remove
        """
        from .set_models import SetRack

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if not match.is_multi_set:
            raise ValueError("Match non è configurato come multi-set")

        current_set = match.get_current_set()
        if not current_set:
            raise ValueError("Nessun set attivo")

        # Find last rack in current set
        last_rack = (
            SetRack.query.filter_by(set_id=current_set.id)
            .order_by(SetRack.rack_number.desc())
            .first()
        )

        if not last_rack:
            raise ValueError("Nessun rack da rimuovere")

        # Update set scores
        if last_rack.winner_id == match.player1_id:
            current_set.player1_racks = max(0, current_set.player1_racks - 1)
        else:
            current_set.player2_racks = max(0, current_set.player2_racks - 1)

        # If set was completed, reopen it
        if current_set.status == MatchStatus.CLOSED_UNILATERALLY.value:
            current_set.status = MatchStatus.PLAYING.value
            current_set.winner_id = None
            current_set.completed_at = None

            # Also need to decrement match set scores
            if last_rack.winner_id == match.player1_id:
                match.player1_score = max(0, match.player1_score - 1)
            else:
                match.player2_score = max(0, match.player2_score - 1)

            # If match was completed, reopen it
            if match.status == MatchStatus.CLOSED_UNILATERALLY.value:
                match.status = MatchStatus.PLAYING.value
                match.winner_id = None

        # Delete the rack
        db.session.delete(last_rack)
        db.session.add(current_set)
        db.session.add(match)
