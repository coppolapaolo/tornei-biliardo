"""
Module: models/competition/trio_service
Purpose: Service layer for trio match operations (scoring, reset, confirmation).
         Extracted from GaraService (Round 3 P1) to respect SRP.
Dependencies: models.base.db, models.match.models.TrioMatch,
              models.match.trio_scoring_service.TrioScoringService
"""

from __future__ import annotations

from models.base import db
from models.transaction.manager import transactional


class TrioMatchService:
    """Operations on trio matches: rack management, confirmation, forfeit, reset."""

    @staticmethod
    @transactional(domain="competition")
    def add_trio_rack(trio_id: int, winner_id: int) -> dict:
        """Aggiunge un rack a una partita trio con validazione.

        Returns:
            Dict con stato aggiornato del trio
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        # Verifica che il vincitore sia tra i giocatori del trio
        if winner_id not in [trio.player1_id, trio.player2_id, trio.player3_id]:
            raise ValueError("Vincitore non valido per questo trio")

        # Aggiungi rack e gestisci rotazione
        from models.match.trio_scoring_service import TrioScoringService
        TrioScoringService.add_rack_win(trio.id, winner_id)

        # Prepara risposta con nuovo stato
        state = trio.get_current_state()

        # Extract current matchup (the two players currently facing each other)
        matchup = state["current_matchup"]
        current_players = []
        if matchup["player1"]:
            current_players.append(
                {"id": matchup["player1"].id, "username": matchup["player1"].username}
            )
        if matchup["player2"]:
            current_players.append(
                {"id": matchup["player2"].id, "username": matchup["player2"].username}
            )

        waiting = matchup.get("waiting")
        waiting_player = (
            {"id": waiting.id, "username": waiting.username} if waiting else None
        )

        # Extract scores from players dict
        scores = {
            "player1": state["players"]["player1"]["racks"],
            "player2": state["players"]["player2"]["racks"],
            "player3": state["players"]["player3"]["racks"],
        }

        result = {
            "success": True,
            "trio_completed": trio.is_completed,
            "awaiting_confirmation": trio.awaiting_confirmation,
            "winner_id": trio.winner_id,
            "current_state": {
                "current_players": current_players,
                "waiting_player": waiting_player,
                "scores": scores,
            },
        }

        # Emit SSE event for real-time updates
        from routes.sse import emit_trio_event, emit_gara_event

        emit_trio_event(trio_id, "rack_added", result)

        # Emit gara event for directors watching gara detail page
        if trio.match and trio.match.gara_id:
            emit_gara_event(trio.match.gara_id, "match_updated", {
                "match_id": trio.match.id,
                "trio_id": trio_id,
                "event": "rack_added",
            })

        return result

    @staticmethod
    @transactional(domain="competition")
    def reset_trio(trio_id: int) -> None:
        """Reset completo di una partita trio.

        Uses the new TrioMatch.reset() method which handles:
        - Resetting all scores to 0
        - Resetting round-robin tracking (current_round, racks_played, etc.)
        - Resetting the associated match status
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        # Use TrioScoringService for reset
        from models.match.trio_scoring_service import TrioScoringService
        TrioScoringService.reset(trio.id)

    @staticmethod
    @transactional(domain="competition")
    def remove_trio_rack(trio_id: int, removed_by_id: int) -> dict:
        """Rimuove l'ultimo rack da una partita trio (undo).

        Returns:
            Dict con stato aggiornato del trio
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        # Remove last rack via service
        from models.match.trio_scoring_service import TrioScoringService
        removed_rack = TrioScoringService.remove_last_rack(trio.id, removed_by_id)
        if not removed_rack:
            raise ValueError("Nessun rack da rimuovere")

        # Prepare response with new state
        state = trio.get_current_state()

        # Extract current matchup
        matchup = state["current_matchup"]
        current_players = []
        if matchup["player1"]:
            current_players.append(
                {"id": matchup["player1"].id, "username": matchup["player1"].username}
            )
        if matchup["player2"]:
            current_players.append(
                {"id": matchup["player2"].id, "username": matchup["player2"].username}
            )

        waiting = matchup.get("waiting")
        waiting_player = (
            {"id": waiting.id, "username": waiting.username} if waiting else None
        )

        # Extract scores
        scores = {
            "player1": state["players"]["player1"]["racks"],
            "player2": state["players"]["player2"]["racks"],
            "player3": state["players"]["player3"]["racks"],
        }

        result = {
            "success": True,
            "removed_rack_winner_id": removed_rack.winner_id,
            "trio_completed": trio.is_completed,
            "current_state": {
                "current_players": current_players,
                "waiting_player": waiting_player,
                "scores": scores,
                "last_rack_winner_id": trio.last_rack.winner_id if trio.last_rack else None,
            },
        }

        # Emit SSE event for real-time updates
        from routes.sse import emit_trio_event, emit_gara_event

        emit_trio_event(trio_id, "rack_removed", result)

        # Emit gara event for directors watching gara detail page
        if trio.match and trio.match.gara_id:
            emit_gara_event(trio.match.gara_id, "match_updated", {
                "match_id": trio.match.id,
                "trio_id": trio_id,
                "event": "rack_removed",
            })

        return result

    @staticmethod
    @transactional(domain="competition")
    def confirm_trio_result(trio_id: int) -> dict:
        """Conferma il risultato del trio da admin/director (bypassa conferme player).

        Called after all racks are played and trio is awaiting_confirmation.
        Admin/director confirmation completes the match immediately.

        Returns:
            Dict con stato aggiornato del trio
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        result = trio.confirm_result_by_admin()

        # Emit SSE for real-time updates
        from routes.sse import emit_trio_event, emit_gara_event

        emit_trio_event(trio_id, "result_confirmed", {
            "is_completed": result["is_completed"],
            "validated_by_admin": True,
        })

        if trio.match and trio.match.gara_id:
            emit_gara_event(trio.match.gara_id, "match_completed", {
                "match_id": trio.match.id,
                "trio_id": trio_id,
            })

        return {
            "success": True,
            "trio_completed": trio.is_completed,
            "winner_id": trio.winner_id,
            "message": result.get("message"),
        }

    @staticmethod
    @transactional(domain="competition")
    def confirm_trio_result_by_player(trio_id: int, user_id: int) -> dict:
        """Conferma il risultato del trio da parte di un giocatore.

        Richiede la conferma di tutti e 3 i giocatori per completare.

        Args:
            trio_id: ID del trio match
            user_id: ID del giocatore che conferma

        Returns:
            Dict con stato conferme e completamento
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        result = trio.confirm_result_by_player(user_id)

        # Emit SSE for real-time updates
        from routes.sse import emit_trio_event, emit_gara_event

        emit_trio_event(trio_id, "player_confirmed", {
            "user_id": user_id,
            "confirmations": result["confirmations"],
            "is_completed": result["is_completed"],
        })

        if result["is_completed"] and trio.match and trio.match.gara_id:
            emit_gara_event(trio.match.gara_id, "match_completed", {
                "match_id": trio.match.id,
                "trio_id": trio_id,
            })

        return result

    @staticmethod
    @transactional(domain="competition")
    def forfeit_trio(trio_id: int, forfeiting_player_id: int, added_by_id: int) -> dict:
        """Handle player forfeit in trio match.

        Auto-completes remaining racks where the forfeiting player would play,
        awarding those racks to their opponents.

        Args:
            trio_id: ID of the trio match
            forfeiting_player_id: ID of the player forfeiting
            added_by_id: ID of user who registered the forfeit

        Returns:
            Dict with updated trio state
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        success = trio.handle_forfeit(forfeiting_player_id, added_by_id)
        if not success:
            raise ValueError("Impossibile registrare il forfait")

        result = {
            "success": True,
            "trio_completed": trio.is_completed,
            "awaiting_confirmation": trio.awaiting_confirmation,
            "forfeit_player_id": trio.forfeit_player_id,
        }

        # Emit SSE event for real-time updates
        from routes.sse import emit_trio_event

        emit_trio_event(trio_id, "forfeit", result)

        return result

    @staticmethod
    @transactional(domain="competition")
    def set_trio_result(
        trio_id: int, player1_racks: int, player2_racks: int, player3_racks: int
    ) -> dict:
        """Imposta direttamente il risultato di una partita trio.

        The trio uses a round-robin system where each player can win up to
        `distance` racks total (including bonus if applicable).
        See ADR-005 for full specification.

        Args:
            trio_id: ID del TrioMatch
            player1_racks: Rack vinti dal player1
            player2_racks: Rack vinti dal player2
            player3_racks: Rack vinti dal player3

        Returns:
            Dict con risultato dell'operazione

        Raises:
            ValueError: Se i punteggi non sono validi per la distanza configurata
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            raise ValueError("Trio match non trovato")

        # Get configuration based on gara distance
        config = trio.trio_config

        # Validate scores against configuration
        scores = [player1_racks, player2_racks, player3_racks]
        max_allowed = config.max_racks_per_player

        # Check no score exceeds max allowed
        for score in scores:
            if score < 0:
                raise ValueError("I punteggi non possono essere negativi")
            if score > max_allowed:
                raise ValueError(
                    f"Punteggio massimo per giocatore: {max_allowed} "
                    f"(distanza {config.distance})"
                )

        # Use TrioScoringService for direct result setting
        from models.match.trio_scoring_service import TrioScoringService
        TrioScoringService.set_result_direct(trio.id, player1_racks, player2_racks, player3_racks)

        return {
            "success": True,
            "winner_id": trio.winner_id,
            "is_tie": trio.winner_id is None,
            "scores": {
                "player1": player1_racks,
                "player2": player2_racks,
                "player3": player3_racks,
            },
            "config": {
                "distance": config.distance,
                "num_rounds": config.num_rounds,
                "bonus_racks": config.bonus_racks,
            },
        }
