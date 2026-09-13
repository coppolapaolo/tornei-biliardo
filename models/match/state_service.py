"""
MatchStateService - State machine for Match lifecycle.

Extracted from MatchService to follow Single Responsibility Principle.
Handles all state transitions: pending → playing → completed.
"""

from __future__ import annotations


from flask_babel import gettext as _

from models.base import db, utc_now
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from models.exceptions import InvalidTransitionError
from .models import Match


class MatchStateService:
    """Service for managing Match state transitions.

    State Machine:
        pending ──→ playing ──→ completed
          ↑           ↓
          └───────────┘ (admin reset)
    """

    # -----------------------------
    # STATE TRANSITIONS
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def to_playing(match_id: int) -> Match:
        """Transition pending/completed → playing.

        Reopening is allowed in admin flows or after rack removal.

        Args:
            match_id: ID of the match to transition

        Returns:
            The updated Match object

        Raises:
            ValueError: If match not found
            InvalidTransitionError: If transition not allowed from current state
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Bye matches should never be transitioned to playing - they are auto-completed
        if match.is_bye:
            raise InvalidTransitionError(
                "I match bye non possono essere messi in stato 'playing'"
            )

        # `CONFIRMED_BY_BOTH` è riapribile quanto `CLOSED_UNILATERALLY`: sono
        # i due stati finali, e riaprire vuol dire disfare un risultato — che
        # i due giocatori si siano messi d'accordo o che l'abbia messo agli
        # atti il direttore. Finché mancava, la correzione di un risultato
        # (issue #90) poteva toccare solo metà delle partite chiuse, e proprio
        # quella metà che il direttore ha inserito di persona.
        if (match.status or MatchStatus.PENDING.value) not in (
            MatchStatus.PENDING.value,
            MatchStatus.CLOSED_UNILATERALLY.value,
            MatchStatus.CONFIRMED_BY_BOTH.value,
        ):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → playing"
            )

        was_completed = MatchStatus.is_finished(match.status)

        match.status = MatchStatus.PLAYING.value

        # Riapertura da completed: annulla i delta di rating applicati (revert).
        # Punto centrale che copre tutti i flussi che riaprono via to_playing
        # (rimozione rack, replace-all-racks, ecc.). No-op se non c'era history.
        if was_completed:
            MatchStateService.emit_reopened_event(match)

        # Auto-set started_at if not already manually set
        if match.started_at is None:
            match.started_at = utc_now()

        db.session.add(match)
        return match

    @staticmethod
    @transactional(domain="match")
    def to_completed(
        match_id: int,
        closed_by_director: bool = False,
        confirmed_by_players: bool = False,
    ) -> Match:
        """Transition playing/pending → uno dei due stati finali.

        Side effects:
        - Records PlayerEncounter for anti-rematch logic
        - Releases and reassigns table
        - Emits MatchCompletedEvent for gamification

        Args:
            match_id: ID of the match to complete
            closed_by_director: la partita la sta chiudendo il **direttore**,
                che può farlo anche se non è mai iniziata — risultato inserito
                a mano, turno importato, partita chiusa d'ufficio. Senza
                questo, una partita ancora PENDING non può passare a
                COMPLETED (vedi il guard qui sotto).

                Prima questo parametro non esisteva: chi ne aveva bisogno
                scriveva `match.validated_by_admin = True` sull'istanza e
                questo metodo lo rileggeva con
                `getattr(match, "validated_by_admin", False)`. Su `Match`
                quella colonna non esiste — vive su `Rack` — quindi era un
                attributo di sola memoria, valido per la durata della
                richiesta e invisibile a chiunque leggesse il modello. Un
                parametro passato di nascosto attraverso l'oggetto, insomma:
                `round_creation.py` aveva dovuto perfino zittire il type
                checker con un `# type: ignore[attr-defined]`, che è il
                momento in cui il codice dice a voce alta di essere sbagliato.
            confirmed_by_players: la partita la chiudono i **giocatori**, che
                hanno confermato tutti. Porta a `CONFIRMED_BY_BOTH` invece che
                a `CLOSED_UNILATERALLY`, e quindi lascia aperta la finestra in
                cui l'ultimo triangolo si puo' ancora annullare.

                Serve al trio. La partita a due non passa di qui: chiude da
                `_complete_match_after_confirmation()`, che lo stato se lo
                scrive da se'. Il trio invece ha bisogno dei quattro effetti
                collaterali di questo metodo (anti-reincontro, rilascio del
                tavolo, evento SSE, classifica), e prima li otteneva al prezzo
                di finire sempre nello stato sbagliato: chiuso dai tre
                giocatori o firmato dal direttore, per il modello era la stessa
                cosa. Il riquadro «Risultato validato» del trio nasceva da li'
                — cercava su `Match` un flag che non esiste, perche' la
                distinzione che voleva mostrare non veniva scritta da nessuna
                parte.

        Returns:
            The updated Match object

        Raises:
            ValueError: If match not found
            InvalidTransitionError: If transition not allowed from current state
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.status not in (MatchStatus.PLAYING.value, MatchStatus.PENDING.value):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → completed"
            )

        if (
            match.status == MatchStatus.PENDING.value
            and not match.is_bye
            and not match.is_trio
            and not closed_by_director
        ):
            raise InvalidTransitionError(
                _("Non è possibile completare una partita che non è ancora iniziata")
            )

        # Quale dei due stati finali. Non e' una sfumatura di etichetta: da qui
        # dipende se i giocatori possono ancora annullare l'ultimo triangolo.
        # `CONFIRMED_BY_BOTH` e' quel che i giocatori hanno concordato, e resta
        # disfacibile finche' il direttore non mette agli atti; `CLOSED_
        # UNILATERALLY` e' gia' agli atti (`scoring_service.py`, ramo `riapri`).
        #
        # Il default resta la chiusura d'ufficio, che e' quella storica di
        # questo metodo: forfait, bye, risultato inserito a mano, turno gia'
        # deciso. Solo chi sa di star chiudendo *per accordo* lo dichiara.
        match.status = (
            MatchStatus.CONFIRMED_BY_BOTH.value
            if confirmed_by_players
            else MatchStatus.CLOSED_UNILATERALLY.value
        )

        # Auto-set ended_at if not already manually set
        if match.ended_at is None:
            match.ended_at = utc_now()

        db.session.add(match)

        # Post-completion side effects
        MatchStateService._record_encounter(match)
        MatchStateService._release_table(match)
        MatchStateService._emit_completion_event(match)
        MatchStateService._update_classification_if_needed(match)

        return match

    # -----------------------------
    # HELPER METHODS (Internal)
    # -----------------------------

    @staticmethod
    def _record_encounter(match: Match) -> None:
        """Record PlayerEncounter for anti-rematch logic.

        Uses PlayerEncounterService which handles bye matches correctly.
        """
        from models.classification.services import PlayerEncounterService

        PlayerEncounterService.record_match_encounters(match)

    @staticmethod
    def _release_table(match: Match) -> None:
        """Release table and reassign to next waiting match."""
        from models.match.table_assignment_service import TableAssignmentService

        TableAssignmentService.release_and_reassign_table(match.id)

    @staticmethod
    def _emit_completion_event(match: Match) -> None:
        """Emit MatchCompletedEvent for gamification.

        Skips bye matches and matches without both players.
        """
        if match.is_bye or not match.player1_id or not match.player2_id:
            return

        from models.events.match_events import MatchCompletedEvent
        from models.events.base import EventBus

        # Get player names
        player1_name = match.player1.username if match.player1 else "Player 1"
        player2_name = match.player2.username if match.player2 else "Player 2"
        winner_name = None
        if match.winner_id:
            winner_name = match.winner.username if match.winner else None

        # Build score string
        score = f"{match.player1_score}-{match.player2_score}"

        # Full participant roster — trio p3 is not exposed via player1/2 fields.
        player_ids: list[int] = []
        if match.is_trio and match.trio_match is not None:
            player_ids = [pid for pid in match.trio_match.player_ids if pid is not None]
        else:
            player_ids = [
                pid for pid in (match.player1_id, match.player2_id) if pid is not None
            ]

        event = MatchCompletedEvent(
            match_id=match.id,
            player1_id=match.player1_id,
            player1_name=player1_name,
            player2_id=match.player2_id,
            player2_name=player2_name,
            winner_id=match.winner_id,
            winner_name=winner_name,
            score=score,
            gara_id=match.gara_id,  # For SSE routing
            player_ids=player_ids,
        )
        EventBus.publish(event)

    @staticmethod
    def emit_reopened_event(match: Match) -> None:
        """Emit MatchReopenedEvent quando un match viene riaperto/resettato.

        Il rating handler annulla (revert) i delta Elo applicati per il match.
        No-op lato handler se non c'era history (es. bye, match mai processato).
        """
        if match.is_bye or not match.player1_id or not match.player2_id:
            return

        from models.events.match_events import MatchReopenedEvent
        from models.events.base import EventBus

        EventBus.publish(MatchReopenedEvent(match_id=match.id))

    @staticmethod
    def _update_classification_if_needed(match: Match) -> None:
        """Update classification if strategy requires it on match completion.

        For strategies with ClassificationUpdateTiming.ON_MATCH_COMPLETE (e.g., Random),
        this recalculates the overall classification after each match.

        For strategies with ON_ROUND_COMPLETE (e.g., Amalfi), this does nothing -
        classification is calculated by RoundService.update_round_progression().
        """
        if not match.gara_id:
            return

        gara = match.gara
        if not gara:
            return

        # Use the new strategy behavior config to check timing
        if not gara.should_update_classification_on_match_complete():
            return

        # For strategies that update on match complete, recalculate classification
        # using the highest round number to aggregate ALL matches
        from models.classification.models import RoundClassification

        # Find the highest round with matches (for overall classification)
        highest_round = (
            db.session.query(db.func.max(Match.round_number))
            .filter(Match.gara_id == gara.id)
            .scalar()
        ) or 1

        # Recalculate overall classification
        # For Random, this aggregates all rounds and sorts by racks_won
        RoundClassification.calculate_classification_after_round(gara.id, highest_round)


__all__ = ["MatchStateService"]
