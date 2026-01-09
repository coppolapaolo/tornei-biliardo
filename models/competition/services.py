"""
Module: models/competition/services
Purpose: Service layer per il dominio Competition (Gara) +
         state machine per le transizioni di stato di Gara.
Data Structures: GaraService, ProvaStateMachine, RoundService
Dependencies: models.base.db, models.competition.models, models.status_enum
Note: InscriptionService extracted to inscription_service.py (Task 1.2)

Nota sprint 4 (migrazione soft):
- Le colonne DB restano VARCHAR; gli Enum sono string-based (compatibili).
- Le route non devono più assegnare .status direttamente: usare le API qui esposte.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.orchestration.service import OperationResult
from datetime import date, datetime

from models.base import db
from models.status_enum import GaraStatus
from .models import Gara, Inscription
from models.transaction.manager import transactional
from .round_service import RoundService
from .state_service import StateService

from models.exceptions import InvalidTransitionError
from models.events.base import EventBus
from models.events.competition_events import (
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent
)


class GaraService:
    """Operazioni di business su Gara (creazione, query, validazione, transizioni)."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    @transactional(domain="competition")
    def create_gara(
        number: int,
        name: str,
        date,
        discipline: str,
        distance: int,
        campionato_id: Optional[int] = None,
        director_id: Optional[int] = None,
        **kwargs,
    ) -> Gara:
        """Crea una Gara (anche standalone se `campionato_id` è None)."""
        # Business Rule: ogni gara deve avere un responsabile
        # - Gara di campionato: gestita dai directors del campionato
        # - Gara standalone: richiede director_id esplicito (tipicamente
        #   l'admin/director che la crea)
        if not campionato_id and not director_id:
            raise ValueError(
                "Una Gara deve avere un campionato_id o un director_id (standalone)."
            )

        # Validazione data - non può essere nel passato
        from datetime import date as date_type

        if isinstance(date, date_type) and date < date_type.today():
            raise ValueError("Data della gara non può essere nel passato")

        # Validazione time - obbligatorio (defaults to 20:00 if missing for backward compatibility/tests)
        if "time" not in kwargs or kwargs["time"] is None:
            from datetime import time as time_type

            kwargs["time"] = time_type(20, 0)

        # Estrai configurazione strategia se presente
        strategy_config = kwargs.pop("strategy_config", None)

        gara = Gara(
            number=number,
            name=name,
            date=date,
            discipline=discipline,
            distance=distance,
            campionato_id=campionato_id,
            director_id=director_id,
            **kwargs,
        )

        # Applica configurazione strategia se fornita
        if strategy_config:
            from models.matchmaking.configuration import StrategyConfiguration

            if isinstance(strategy_config, StrategyConfiguration):
                config_dict = strategy_config.to_dict()
            else:
                config_dict = strategy_config

            # Applica i campi di configurazione
            for key, value in config_dict.items():
                if hasattr(gara, key):
                    setattr(gara, key, value)

        # Valida la configurazione
        errors = gara.validate_strategy_configuration()
        if errors:
            raise ValueError(f"Configurazione non valida: {', '.join(errors)}")

        db.session.add(gara)
        return gara

    @staticmethod
    def get_gara_by_id(gara_id: int) -> Optional[Gara]:
        """Retrieve a Gara by ID using service layer.

        Args:
            gara_id: ID of the gara to retrieve

        Returns:
            Gara: The gara instance if found, None otherwise
        """
        return db.session.get(Gara, gara_id)

    @staticmethod
    @transactional(domain="competition")
    def update_gara(gara_id: int, **kwargs) -> Gara:
        """Aggiorna una gara con i campi forniti."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_be_modified():
            raise ValueError(
                "Impossibile modificare la gara: ci sono già delle iscrizioni!"
            )

        # Aggiorna solo i campi forniti
        for field, value in kwargs.items():
            if hasattr(gara, field):
                setattr(gara, field, value)

        # Gestione speciale per date
        if "date_str" in kwargs:
            from datetime import datetime

            gara.date = datetime.strptime(kwargs["date_str"], "%Y-%m-%d").date()

        # Gestione speciale per time
        if "time_str" in kwargs:
            from datetime import datetime

            gara.time = datetime.strptime(kwargs["time_str"], "%H:%M").time()

        return gara

    @staticmethod
    @transactional(domain="competition")
    def delete_gara(gara_id: int) -> None:
        """Cancella una gara se possibile."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_be_deleted():
            raise ValueError(
                "Impossibile cancellare la gara: ci sono già delle iscrizioni!"
            )

        db.session.delete(gara)

    @staticmethod
    @transactional(domain="competition")
    def cancel_gara_with_notifications(gara_id: int, cancelled_by_id: int) -> None:
        """Cancella una gara inviando notifiche a tutti i partecipanti iscritti."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica che la gara possa essere cancellata
        if gara.status not in ["setup", "inscription"]:
            raise ValueError("La gara non può essere cancellata in questo stato!")

        # Ottieni tutti gli iscritti prima di cancellare
        inscriptions = db.session.query(Inscription).filter_by(gara_id=gara_id).all()
        participant_ids = [inscription.user_id for inscription in inscriptions]

        # Prepara le informazioni per le notifiche
        gara_name = gara.name
        campionato_name = gara.campionato.name if gara.campionato else "Standalone"

        # Cancella la gara
        db.session.delete(gara)

        # Invia notifiche a tutti i partecipanti
        if participant_ids:
            from models.notification.models import (
                NotificationPriority,
                NotificationType,
            )

            message = f"La {gara_name}"
            if gara.campionato:
                message += f" del campionato '{campionato_name}'"
            message += f" del {gara.date.strftime('%d/%m/%Y')} è stata cancellata."

            # Use NotificationFactory for bulk notifications with error handling
            from models.notification.factory import NotificationFactory

            NotificationFactory.create_bulk_notification(
                user_ids=participant_ids,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                title="Gara Cancellata",
                message=message,
                priority=NotificationPriority.HIGH,
                continue_on_error=True,
            )

    @staticmethod
    def start_first_round(gara_id: int) -> Gara:
        """Avvia il primo turno della gara con controlli e sorteggio."""
        return RoundService.start_first_round(gara_id)

    @staticmethod
    @transactional(domain="competition")
    def cancel_first_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del primo turno se non sono stati inseriti risultati."""
        return RoundService.cancel_first_round_startup(gara_id)

    @staticmethod
    @transactional(domain="competition")
    def cancel_current_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del turno corrente se non sono stati inseriti risultati.

        Decrementa il current_round e rimuove tutte le partite del turno corrente.
        Utilizzabile solo se non sono stati inseriti risultati (anche parziali).
        """
        from models.match.models import Match, TrioMatch
        from models.status_enum import MatchStatus, GaraStatus

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica che siamo in stato playing
        if gara.status != GaraStatus.PLAYING.value:
            raise ValueError("La gara deve essere in stato playing")

        current_round = gara.current_round
        if current_round <= 0:
            raise ValueError("Non c'è un turno corrente da cancellare")

        # Verifica che non ci siano risultati inseriti (neanche parziali)
        current_round_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=current_round
        ).all()

        if not current_round_matches:
            raise ValueError("Non ci sono partite del turno corrente da cancellare")

        # Controlla che non ci siano risultati inseriti (neanche parziali)
        # Note: match.status == PLAYING just means a table was assigned,
        # not that results have been entered. Only check actual scores.
        for match in current_round_matches:
            if (
                match.player1_score > 0
                or match.player2_score > 0
                or match.winner_id is not None
            ):
                raise ValueError(
                    "Impossibile cancellare l'avvio: sono già stati inseriti "
                    "risultati (anche parziali)"
                )

        # Rimuovi tutte le partite del turno corrente e dati correlati
        from models.classification.models import (
            PlayerEncounter,
            RoundClassification,
        )

        # Rimuovi eventuali trii collegati
        for match in current_round_matches:
            trio = db.session.query(TrioMatch).filter_by(match_id=match.id).first()
            if trio:
                db.session.delete(trio)

        # Rimuovi i PlayerEncounter del turno corrente per ripristinare l'anti-rematch
        encounters_to_remove = (
            db.session.query(PlayerEncounter)
            .filter_by(gara_id=gara_id, round_number=current_round)
            .all()
        )
        for encounter in encounters_to_remove:
            db.session.delete(encounter)

        # Rimuovi le RoundClassification del turno corrente
        classifications_to_remove = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=current_round)
            .all()
        )
        for classification in classifications_to_remove:
            db.session.delete(classification)

        # Rimuovi tutte le partite
        for match in current_round_matches:
            db.session.delete(match)

        # Decrementa il current_round
        gara.current_round = current_round - 1

        # Se torniamo al turno 0, riporta allo stato inscription
        if gara.current_round == 0:
            gara.status = GaraStatus.INSCRIPTION.value

        db.session.add(gara)
        return gara

    @staticmethod
    def create_round_with_strategy(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Facade: delegate to RoundService."""
        from models.competition.round_service import RoundService

        return RoundService.create_round_with_strategy(
            gara_id, round_number, discipline_override
        )

    @staticmethod
    def create_amalfi_round(
        gara_id: int, round_number: int
    ) -> tuple[int, int, int, int]:
        """Legacy compatibility wrapper."""
        return GaraService.create_round_with_strategy(gara_id, round_number)

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
            from flask import abort

            abort(404)

        # Verifica che il vincitore sia tra i giocatori del trio
        if winner_id not in [trio.player1_id, trio.player2_id, trio.player3_id]:
            raise ValueError("Vincitore non valido per questo trio")

        # Aggiungi rack e gestisci rotazione
        trio.add_rack_win(winner_id)

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
        from routes.sse import emit_trio_event

        emit_trio_event(trio_id, "rack_added", result)

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
            from flask import abort

            abort(404)

        # Use the new reset method on TrioMatch
        trio.reset()

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
            from flask import abort

            abort(404)

        # Remove last rack
        removed_rack = trio.remove_last_rack(removed_by_id)
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
        from routes.sse import emit_trio_event

        emit_trio_event(trio_id, "rack_removed", result)

        return result

    @staticmethod
    @transactional(domain="competition")
    def confirm_trio_result(trio_id: int) -> dict:
        """Conferma il risultato del trio e completa la partita.

        Called after all racks are played and trio is awaiting_confirmation.

        Returns:
            Dict con stato aggiornato del trio
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            from flask import abort

            abort(404)

        if not trio.awaiting_confirmation:
            raise ValueError("Trio non in attesa di conferma")

        # Confirm the result
        success = trio.confirm_result()
        if not success:
            raise ValueError("Impossibile confermare il risultato")

        return {
            "success": True,
            "trio_completed": trio.is_completed,
            "winner_id": trio.winner_id,
        }

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
            from flask import abort

            abort(404)

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
        from models.match.models import TrioMatch, Match  # noqa: F811

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            from flask import abort

            abort(404)

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

        # Use the new set_result_direct method
        trio.set_result_direct(player1_racks, player2_racks, player3_racks)

        # Also mark as validated by admin
        match = db.session.get(Match, trio.match_id)
        if match:
            match.validated_by_admin = True

        return {
            "success": True,
            "winner_id": trio.winner_id,  # May be None if tie
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

    # -----------------------------
    # VALIDAZIONE DATI (type-safe)
    # -----------------------------
    @staticmethod
    def validate_gara_data(data: dict) -> dict:
        """Valida i campi della Gara e restituisce errori per campo."""
        errors: dict = {}

        # name
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = "Nome obbligatorio"

        # discipline
        discipline = (data.get("discipline") or "").strip()
        if not discipline:
            errors["discipline"] = "Disciplina obbligatoria"

        # distance
        dist_raw = data.get("distance")
        if dist_raw in (None, ""):
            errors["distance"] = "Distanza obbligatoria"
        else:
            try:
                distance = int(dist_raw)
                if distance < 1:
                    errors["distance"] = "Distanza deve essere almeno 1"
            except (TypeError, ValueError):
                errors["distance"] = "Distanza non valida"

        # entry_fee (opzionale)
        fee_raw = data.get("entry_fee")
        if fee_raw not in (None, ""):
            try:
                fee = float(fee_raw)
                if fee < 0:
                    errors["entry_fee"] = "Quota non può essere negativa (>= 0)"
            except (TypeError, ValueError):
                errors["entry_fee"] = "Quota deve essere un numero valido"

        # number (opzionale)
        number_raw = data.get("number")
        if number_raw not in (None, ""):
            try:
                number = int(number_raw)
                if number < 1:
                    errors["number"] = "Numero gara deve essere almeno 1"
            except (TypeError, ValueError):
                errors["number"] = "Numero gara non valido"

        # min_participants (default 2)
        min_p_raw = data.get("min_participants")
        try:
            min_p = 2 if min_p_raw in (None, "") else int(min_p_raw)
            if min_p < 2:
                errors["min_participants"] = "Minimo 2 partecipanti"
        except (TypeError, ValueError):
            errors["min_participants"] = "Numero partecipanti minimo non valido"
            min_p = None  # type: ignore[assignment]

        # max_participants (opzionale, >= min)
        max_p_raw = data.get("max_participants")
        if max_p_raw not in (None, ""):
            try:
                max_p = int(max_p_raw)
                if isinstance(min_p, int) and max_p < min_p:
                    errors["max_participants"] = "Max participants deve essere >= min"
            except (TypeError, ValueError):
                errors["max_participants"] = "Numero partecipanti massimo non valido"

        # inscription dates (opzionali): end deve essere >= start
        start_raw = data.get("inscription_start")
        end_raw = data.get("inscription_end")

        def _parse_date(v):
            if not v:
                return None
            if isinstance(v, date):
                return v
            try:
                return date.fromisoformat(str(v))
            except Exception:
                return None

        # Valida formato data di inizio
        if start_raw:  # Se è fornita, deve essere valida
            start_dt = _parse_date(start_raw)
            if start_dt is None:
                errors["inscription_start"] = "Formato data non valido (usa YYYY-MM-DD)"
        else:
            start_dt = None

        # Valida formato data di fine
        if end_raw:  # Se è fornita, deve essere valida
            end_dt = _parse_date(end_raw)
            if end_dt is None:
                errors["inscription_end"] = "Formato data non valido (usa YYYY-MM-DD)"
        else:
            end_dt = None

        if start_dt and end_dt and end_dt < start_dt:
            errors[
                "inscription_end"
            ] = "La data di fine iscrizioni deve essere >= della data di inizio"

        # rounds_count (opzionale): >= 1
        rounds_raw = data.get("rounds_count")
        rounds_count: Optional[int] = None
        if rounds_raw not in (None, ""):
            try:
                rounds_count = int(rounds_raw)
                if rounds_count < 1:
                    errors["rounds_count"] = "Il numero di turni deve essere almeno 1"
            except (TypeError, ValueError):
                errors["rounds_count"] = "Numero di turni non valido"

        # Anti-rematch constraint: with N players, max N-1 rounds possible
        # This validation applies when:
        # - anti_rematch_enabled is True
        # - max_participants is set (known limit)
        # - rounds_count is set
        anti_rematch = data.get("anti_rematch_enabled", False)
        if anti_rematch and max_p_raw not in (None, "") and rounds_count is not None:
            try:
                max_p_val = int(max_p_raw)
                max_rounds = max_p_val - 1
                if rounds_count > max_rounds:
                    errors["rounds_count"] = (
                        f"Con anti-rematch attivo e {max_p_val} partecipanti massimi, "
                        f"puoi avere al massimo {max_rounds} turni "
                        f"(ogni giocatore può incontrare al massimo {max_rounds} avversari unici)"
                    )
            except (TypeError, ValueError):
                pass  # max_p validation already handled above

        return errors

    # -----------------------------
    # STATE MACHINE FACADE
    # -----------------------------
    @staticmethod
    def to_inscription(
        gara_id: int, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Validazione finestra (se entrambe presenti)
        if start is not None and end is not None and start > end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        # Imposta campi data se forniti PRIMA della transizione di stato
        if start is not None:
            gara.inscription_start = start
        if end is not None:
            gara.inscription_end = end

        gara = StateService.to_inscription(gara)

        return gara

    @staticmethod
    def reopen_setup(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return StateService.reopen_setup(gara)

    @staticmethod
    def start_playing(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return StateService.start_playing(gara)

    @staticmethod
    def complete(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return StateService.complete(gara)

    @staticmethod
    @transactional(domain="competition")
    def add_director(gara_id: int, user_id: int, assigned_by_id: int) -> bool:
        """Aggiunge un co-direttore alla gara.

        Returns:
            True se aggiunto con successo, False se già esistente

        Raises:
            ValueError se l'utente è admin
        """
        from models.user.models import User, DirectorAssignment

        # Verifica che l'utente non sia admin
        user = db.session.get(User, user_id)
        if user and user.is_admin:
            raise ValueError("Gli admin non possono essere direttori di gara")

        # Controlla se già esiste
        existing = (
            db.session.query(DirectorAssignment)
            .filter_by(entity_type="gara", entity_id=gara_id, user_id=user_id)
            .first()
        )
        if existing:
            return False

        # Crea associazione
        director_assoc = DirectorAssignment(
            entity_type="gara",
            entity_id=gara_id,
            user_id=user_id,
            assigned_by_id=assigned_by_id,
        )
        db.session.add(director_assoc)

        # Pubblica evento per notifica (pattern event-driven)
        gara = db.session.get(Gara, gara_id)
        gara_name = gara.name or f"Gara {gara.number}"

        if gara.campionato:
            gara_name += f" del campionato '{gara.campionato.name}'"

        event = DirectorAssignmentAddedEvent(
            entity_type="gara",
            entity_id=gara_id,
            entity_name=gara_name,
            user_id=user_id,
            username=user.username,
            assigned_by_id=assigned_by_id
        )
        EventBus.publish(event)

        return True

    # -----------------------------
    # STRATEGY CONFIGURATION
    # -----------------------------

    @staticmethod
    def get_available_strategies() -> dict:
        """Restituisce le strategie disponibili con le loro configurazioni."""
        from models.matchmaking.configuration import (
            STRATEGY_CONSTRAINTS,
            MatchmakingStrategy,
        )

        strategies = {}
        for strategy in MatchmakingStrategy:
            constraints = STRATEGY_CONSTRAINTS.get(strategy, {})
            strategies[strategy.value] = {
                "name": strategy.value,
                "display_name": strategy.value.replace("_", " ").title(),
                "description": constraints.get("description", ""),
                "constraints": constraints,
            }
        return strategies

    @staticmethod
    @transactional(domain="competition")
    def remove_director(gara_id: int, user_id: int) -> bool:
        """Rimuove un co-direttore dalla gara.

        Returns:
            True se rimosso con successo, False se non trovato
        """
        from models.user.models import DirectorAssignment, User

        director_assoc = (
            db.session.query(DirectorAssignment)
            .filter_by(entity_type="gara", entity_id=gara_id, user_id=user_id)
            .first()
        )
        if not director_assoc:
            return False

        # Recupera dati per evento prima di eliminare
        user = db.session.get(User, user_id)
        gara = db.session.get(Gara, gara_id)
        gara_name = gara.name or f"Gara {gara.number}"

        if gara.campionato:
            gara_name += f" del campionato '{gara.campionato.name}'"

        # Elimina associazione
        db.session.delete(director_assoc)

        # Pubblica evento per notifica (pattern event-driven)
        event = DirectorAssignmentRemovedEvent(
            entity_type="gara",
            entity_id=gara_id,
            entity_name=gara_name,
            user_id=user_id,
            username=user.username,
            removed_by_id=director_assoc.assigned_by_id  # chi ha aggiunto
        )
        EventBus.publish(event)

        return True

    @staticmethod
    def update_round_progression(gara_id: int) -> None:
        """Facade: delegate to RoundService."""
        from models.competition.round_service import RoundService

        return RoundService.update_round_progression(gara_id)

    @staticmethod
    def modify_inscription_dates(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> "Gara":
        """Facade: delegate to InscriptionService."""
        from models.competition.inscription_service import InscriptionService

        return InscriptionService.modify_inscription_dates(
            gara_id, inscription_start, inscription_end
        )

    @staticmethod
    def open_inscriptions(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> "Gara":
        """Facade: delegate to InscriptionService."""
        from models.competition.inscription_service import InscriptionService

        return InscriptionService.open_inscriptions(
            gara_id, inscription_start, inscription_end
        )

    @staticmethod
    def can_start_with_current_inscriptions(gara_id: int) -> bool:
        """Facade: delegate to InscriptionService."""
        from models.competition.inscription_service import InscriptionService

        return InscriptionService.can_start_with_current_inscriptions(gara_id)

    @staticmethod
    @transactional(domain="competition")
    def reset_tournament_to_round(
        gara_id: int, target_round: int, admin_id: int, reset_reason: str
    ) -> "OperationResult":
        """
        Reset tournament to a specific round, removing all subsequent rounds and data.

        Args:
            gara_id: ID of the tournament
            target_round: Round number to reset to
            admin_id: ID of the admin performing the reset
            reset_reason: Reason for the reset

        Returns:
            OperationResult with success status and details
        """
        from models.match.models import Match
        from models.classification.models import RoundClassification
        from models.orchestration.service import OperationResult, OperationType

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return OperationResult(
                success=False,
                operation_type=OperationType.TOURNAMENT_RESET,
                data={},
                errors=["Tournament not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["competition"],
            )

        if target_round < 1 or target_round > gara.current_round:
            return OperationResult(
                success=False,
                operation_type=OperationType.TOURNAMENT_RESET,
                data={},
                errors=[
                    f"Invalid target round {target_round}. Must be between 1 "
                    f"and {gara.current_round}"
                ],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["competition"],
            )

        # Delete matches from rounds after target_round
        matches_to_delete = Match.query.filter(
            Match.gara_id == gara_id, Match.round_number > target_round
        ).all()

        deleted_matches = len(matches_to_delete)
        for match in matches_to_delete:
            db.session.delete(match)

        # Delete round classifications from rounds after target_round
        classifications_to_delete = RoundClassification.query.filter(
            RoundClassification.gara_id == gara_id,
            RoundClassification.round_number > target_round,
        ).all()

        deleted_classifications = len(classifications_to_delete)
        for classification in classifications_to_delete:
            db.session.delete(classification)

        # Reset current round
        gara.current_round = target_round

        # Unlock previous rounds for modification
        previous_matches = Match.query.filter(
            Match.gara_id == gara_id, Match.round_number <= target_round
        ).all()
        for match in previous_matches:
            match.is_locked = False
            match.round_locked = False

        db.session.add(gara)
        # Transaction managed by @transactional decorator

        return OperationResult.success_result(
            operation_type=OperationType.TOURNAMENT_RESET,
            data={
                "deleted_matches": deleted_matches,
                "deleted_classifications": deleted_classifications,
                "current_round": target_round,
                "admin_id": admin_id,
                "reason": reset_reason,
            },
            execution_time_ms=0.0,
            affected_domains=["competition", "classification"],
        )

    @staticmethod
    @transactional(domain="competition")
    def soft_delete_gara(
        gara_id: int,
        deleted_by_id: int,
        cascade_option: str,
        reason: str = ""
    ) -> None:
        """Soft delete a gara with cascade options.

        Admin-only operation. Marks the gara as deleted without physical removal.
        Related matches can be either detached (kept as standalone) or logically
        deleted along with the gara.

        Args:
            gara_id: ID of gara to soft delete
            deleted_by_id: ID of admin performing the deletion
            cascade_option: "delete_all" or "keep_matches"
                - delete_all: Matches stay linked (will be hidden by gara filter)
                - keep_matches: Matches become standalone (gara_id = NULL)
            reason: Optional reason for deletion

        Raises:
            ValueError: If gara not found
        """
        from models.match.models import Match

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # If keep_matches: detach all matches from gara
        if cascade_option == "keep_matches":
            Match.query.filter_by(gara_id=gara_id).update({"gara_id": None})

        # Soft delete the gara
        gara.deleted_at = datetime.utcnow()
        gara.deleted_reason = reason

        db.session.add(gara)

    @staticmethod
    @transactional(domain="competition")
    def cancel_tournament(
        gara_id: int,
        admin_id: int,
        cancellation_reason: str,
        refund_entry_fees: bool = False,
        notify_participants: bool = True,
    ) -> "OperationResult":
        """
        Cancel a tournament completely.

        Args:
            gara_id: ID of the tournament
            admin_id: ID of the admin performing the cancellation
            cancellation_reason: Reason for the cancellation
            refund_entry_fees: Whether to refund entry fees
            notify_participants: Whether to notify participants

        Returns:
            OperationResult with success status and details
        """
        from models.orchestration.service import OperationResult, OperationType

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return OperationResult(
                success=False,
                operation_type=OperationType.TOURNAMENT_CANCELLATION,
                data={},
                errors=["Tournament not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["competition"],
            )

        # Change status to cancelled
        gara.status = GaraStatus.CANCELLED.value
        db.session.add(gara)
        # Transaction managed by @transactional decorator

        return OperationResult.success_result(
            operation_type=OperationType.TOURNAMENT_CANCELLATION,
            data={
                "gara_id": gara_id,
                "admin_id": admin_id,
                "cancellation_reason": cancellation_reason,
                "refund_entry_fees": refund_entry_fees,
                "notify_participants": notify_participants,
                "status": gara.status,
            },
            execution_time_ms=0.0,
            affected_domains=["competition", "notification"],
        )

    # Note: InscriptionService and RoundService have been extracted as separate services
    # GaraService retains existing methods for backward compatibility
    # New code should use InscriptionService and RoundService directly


from models.competition.inscription_service import InscriptionService

__all__ = [
    "GaraService",
    "InscriptionService",
    "InvalidTransitionError",
]
