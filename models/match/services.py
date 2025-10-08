"""
Module: models/match/services
Purpose: Service layer per il dominio Match (Match, Rack, MatchResult, TrioMatch)
         + state machine centralizzata per gli stati del Match.
Data Structures: MatchService, RackService, MatchResultService
Dependencies: models.base.db, models.match.models, models.status_enum

Nota sprint 4: aggiunte API di transizione di stato; preservati nomi/classi esistenti
per compatibilità con i test di separazione.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from models.orchestration.service import OperationResult

from models.base import db
from models.status_enum import MatchStatus
from .models import Match, Rack, TrioMatch
from models.transaction.manager import transactional

from models.exceptions import InvalidTransitionError


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
    # -----------------------------
    @staticmethod
    @transactional(domain="match")
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
        return match

    @staticmethod
    @transactional(domain="match")
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

        # Registra automaticamente l'encounter per anti-rematch logic
        # Usa il metodo esistente che gestisce correttamente bye e match normali
        from models.classification.services import PlayerEncounterService
        PlayerEncounterService.record_match_encounters(match)

        return match

    @staticmethod
    def reset_to_pending(
        match_id: int, clear_validation: bool = True
    ) -> "OperationResult":
        """Qualsiasi → pending. Opzione per azzerare flag di validazione admin.
        Non rimuove i rack (responsabilità di RackService).

        NOTE: This method is intentionally NOT decorated with @transactional
        because it implements custom transaction management with explicit
        rollback handling and OperationResult error reporting pattern.
        Migration to @transactional would require changing the interface.
        """
        from ..orchestration.service import OperationResult, OperationType
        from .models import Rack

        try:
            match = db.session.get(Match, match_id)
            if not match:
                return OperationResult.failure_result(
                    operation_type=OperationType.RESULT_PROCESSING,
                    errors=[f"Match {match_id} non trovato"],
                    execution_time_ms=0,
                    affected_domains=["match"],
                )

            old_status = match.status

            # Clear all racks
            existing_racks = Rack.query.filter_by(match_id=match_id).all()
            for rack in existing_racks:
                db.session.delete(rack)

            # Reset match scores
            match.player1_score = 0
            match.player2_score = 0
            match.winner_id = None
            match.status = MatchStatus.PENDING.value

            if clear_validation and hasattr(match, "validated_by_admin"):
                try:
                    match.validated_by_admin = False
                except Exception:
                    pass
            db.session.add(match)
            db.session.commit()

            return OperationResult.success_result(
                operation_type=OperationType.RESULT_PROCESSING,
                data={
                    "match_id": match_id,
                    "old_status": old_status,
                    "new_status": match.status,
                    "validation_cleared": clear_validation,
                },
                execution_time_ms=0,
                affected_domains=["match"],
            )

        except Exception as e:
            db.session.rollback()
            return OperationResult.failure_result(
                operation_type=OperationType.RESULT_PROCESSING,
                errors=[f"Errore nel reset match: {str(e)}"],
                execution_time_ms=0,
                affected_domains=["match"],
            )

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
        from models.orchestration.service import OperationResult, OperationType

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
        from models.orchestration.service import OperationResult, OperationType

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
        from models.orchestration.service import OperationResult, OperationType

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
    ) -> Rack:
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
        match = db.session.get(Match, match_id)
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
        """Aggiunge rack e aggiorna automaticamente il punteggio del match.

        Returns:
            Dict con stato aggiornato del match
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Verifica che il match non sia già finito usando RackScore
        if match.rack_score.is_complete():
            raise ValueError(
                "Il match è già finito, non è possibile aggiungere altri punti"
            )

        # Simula aggiunta del nuovo rack per validare
        temp_p1_score = match.player1_score
        temp_p2_score = match.player2_score

        if winner_id == match.player1_id:
            temp_p1_score += 1
        else:
            temp_p2_score += 1

        # Valida in base al tipo di match usando distance_config
        distance = match.gara.distance_config
        if distance.racks_best_of:  # "al meglio di N"
            winning_racks = distance.get_winning_racks()
            if temp_p1_score > winning_racks or temp_p2_score > winning_racks:
                raise ValueError(
                    f"Match già completato - limite raggiunto per "
                    f"'{distance.to_display_string()}'"
                )
        else:  # "esattamente N"
            total_racks = temp_p1_score + temp_p2_score
            if total_racks > distance.racks:
                raise ValueError(
                    f"Non è possibile superare il limite di {distance.racks} "
                    f"rack totali per questo match"
                )

        # Trova il prossimo numero rack
        last_rack = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

        # Crea il rack
        # NOTA: add_rack_result già aggiorna automaticamente il punteggio del match
        # quindi NON dobbiamo aggiornare player1_score/player2_score qui
        RackService.add_rack_result(
            match_id=match.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            validated_by_admin=validated_by_admin,
        )

        # Ricarica il match per ottenere i punteggi aggiornati da add_rack_result
        db.session.refresh(match)

        # Se il match è finito, imposta il vincitore usando RackScore
        if match.rack_score.is_complete():
            final_winner_id = match.rack_score.get_winner()
            if final_winner_id is None:
                # Tie - usa punteggio grezzo
                final_winner_id = (
                    match.player1_id
                    if match.player1_score > match.player2_score
                    else match.player2_id
                )
            else:
                # Converti player number (1,2) a player_id
                final_winner_id = (
                    match.player1_id if final_winner_id == 1
                    else match.player2_id
                )
            # Import locale per evitare cicli
            from models.match.services import MatchResultService

            MatchResultService.submit_result(match.id, final_winner_id)

        return {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    @transactional(domain="match")
    def set_match_result_direct(
        match_id: int, player1_score: int, player2_score: int
    ) -> None:
        """Imposta risultato completo di una partita sostituendo tutti i rack."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi modificare una partita bye!")

        # Validazione punteggi
        if player1_score < 0 or player2_score < 0:
            raise ValueError("I punteggi non possono essere negativi!")

        # Verifica che il risultato sia valido secondo le regole della gara
        total_racks = player1_score + player2_score

        if match.gara.best_of:
            # Al meglio di: uno dei due deve aver raggiunto la soglia
            winning_score = match.gara.get_winning_score()
            if max(player1_score, player2_score) < winning_score:
                raise ValueError(
                    f'Nel "al meglio di {match.gara.distance}", uno dei '
                    f"giocatori deve raggiungere {winning_score} punti!"
                )
        else:
            # Esatto numero: la somma deve essere esattamente la distanza
            if total_racks != match.gara.distance:
                raise ValueError(
                    f'Nel "{match.gara.distance} rack esatti", '
                    f"la somma deve essere esattamente {match.gara.distance}!"
                )

        # Determina il vincitore
        if player1_score > player2_score:
            winner_id = match.player1_id
        elif player2_score > player1_score:
            winner_id = match.player2_id
        else:
            raise ValueError("Non può esserci un pareggio!")

        # Elimina tutti i rack esistenti per questa partita
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Crea i nuovi rack basati sul risultato
        rack_number = 1

        # Crea rack per player1
        for i in range(player1_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player1_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Crea rack per player2
        for i in range(player2_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player2_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Aggiorna il match
        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id

        # Import locale per evitare cicli
        from models.match.services import MatchService
        from models.status_enum import MatchStatus

        # Solo transizione a completed se non è già completed
        if match.status != MatchStatus.COMPLETED.value:
            MatchService.to_completed(match.id)

    @staticmethod
    @transactional(domain="match")
    def reset_match_complete(match_id: int) -> None:
        """Reset completo di una partita eliminando tutti i rack."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi resettare una partita bye!")

        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Reset match
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None

        # Import locale per evitare cicli
        from models.match.services import MatchService

        MatchService.reset_to_pending(match.id, clear_validation=True)

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

        # Se il match era completato e ora non ha più i punti per essere vinto,
        # rimettilo in playing
        if match.status == MatchStatus.COMPLETED.value:
            if match.gara.best_of:
                winning_score = match.gara.get_winning_score()
                if max(match.player1_score, match.player2_score) < winning_score:
                    MatchService.to_playing(match.id)
                    match.winner_id = None
            else:  # esatto numero
                if (match.player1_score + match.player2_score) < match.gara.distance:
                    MatchService.to_playing(match.id)
                    match.winner_id = None

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


class MatchResultService:
    """Placeholder per gestione risultati/validazioni match."""

    @staticmethod
    @transactional(domain="match")
    def validate_by_admin(match_id: int) -> Match:
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = True
            db.session.add(match)
        return match

    @staticmethod
    @transactional(domain="match")
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

        # set vincitore
        match.winner_id = winner_id
        db.session.add(match)

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
