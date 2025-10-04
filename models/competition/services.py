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
        for match in current_round_matches:
            if (
                match.player1_score > 0
                or match.player2_score > 0
                or match.status != MatchStatus.PENDING.value
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

        return {
            "success": True,
            "trio_completed": trio.is_completed,
            "winner_id": trio.winner_id,
            "current_state": {
                "current_players": [
                    {"id": p.id, "username": p.username}
                    for p in state["current_players"]
                ],
                "waiting_player": (
                    {
                        "id": state["waiting_player"].id,
                        "username": state["waiting_player"].username,
                    }
                    if state["waiting_player"]
                    else None
                ),
                "scores": state["scores"],
            },
        }

    @staticmethod
    @transactional(domain="competition")
    def reset_trio(trio_id: int) -> None:
        """Reset completo di una partita trio."""
        from models.match.models import TrioMatch, Match
        from models.match.services import MatchService

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            from flask import abort

            abort(404)

        # Reset scores
        trio.player1_racks = 0
        trio.player2_racks = 0
        trio.player3_racks = 0

        # Reset state
        trio.current_player1_id = trio.player1_id
        trio.current_player2_id = trio.player2_id
        trio.waiting_player_id = trio.player3_id
        trio.is_completed = False
        trio.winner_id = None

        # Reset match associato
        MatchService.reset_to_pending(trio.match.id, clear_validation=True)
        # Access the match object directly using db.session.get to avoid
        # relationship property issues
        match_obj = db.session.get(Match, trio.match_id)
        if match_obj:
            match_obj.winner_id = None

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
        if rounds_raw not in (None, ""):
            try:
                rounds = int(rounds_raw)
                if rounds < 1:
                    errors["rounds_count"] = "Il numero di turni deve essere almeno 1"
            except (TypeError, ValueError):
                errors["rounds_count"] = "Numero di turni non valido"

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

        # Invia notifica al nuovo co-direttore
        try:
            from models.notification.factory import NotificationFactory
            from models.notification.models import NotificationPriority
            from models.competition.models import Gara

            gara = db.session.get(Gara, gara_id)
            gara_name = gara.name or f"Gara {gara.number}"

            if gara.campionato:
                gara_name += f" del campionato '{gara.campionato.name}'"

            notification_result = (
                NotificationFactory.create_account_update_notification(
                    user_id=user_id,
                    title="Nominato co-direttore",
                    message=f"Sei stato nominato co-direttore della {gara_name}",
                    priority=NotificationPriority.NORMAL,
                    update_type="co_director_assignment",
                    related_entities={"gara_id": gara_id, "gara_name": gara_name},
                )
            )
            print(
                f"DEBUG: Director notification created for user {user_id}: "
                f"{notification_result}"
            )
        except Exception as e:
            print(
                f"DEBUG: Error creating director notification for user {user_id}: {e}"
            )

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
        from models.user.models import DirectorAssignment

        director_assoc = (
            db.session.query(DirectorAssignment)
            .filter_by(entity_type="gara", entity_id=gara_id, user_id=user_id)
            .first()
        )
        if director_assoc:
            db.session.delete(director_assoc)
            return True
        return False

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


__all__ = [
    "GaraService",
    "InvalidTransitionError",
]
