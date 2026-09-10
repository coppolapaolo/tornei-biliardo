"""
Round Service - Competition Domain

Facade for round lifecycle management. Delegates to:
- round_creation.py: Round creation and match generation
- round_cancellation.py: Round cancellation operations

Keeps start_first_round and update_round_progression locally as they
are orchestrator methods tightly coupled to gara state transitions.
"""

from __future__ import annotations

import logging

from models.base import db, transactional
from models.matchmaking.configuration import MatchmakingStrategy
from .models import Gara
from .round_creation import RoundCreationService
from .round_cancellation import RoundCancellationService

logger = logging.getLogger(__name__)


class RoundService:
    """Service for managing round creation and progression.

    Facade that delegates to RoundCreationService and RoundCancellationService.
    """

    # --- Delegated to RoundCreationService ---
    create_round_with_strategy = RoundCreationService.create_round_with_strategy
    start_next_round = RoundCreationService.start_next_round
    _create_round_impl = RoundCreationService._create_round_impl

    # --- Delegated to RoundCancellationService ---
    cancel_first_round_startup = RoundCancellationService.cancel_first_round_startup
    cancel_current_round_startup = RoundCancellationService.cancel_current_round_startup

    # --- Kept locally (orchestrators) ---

    @staticmethod
    @transactional(domain="competition")
    def start_first_round(
        gara_id: int, bye_to_last_inscribed: bool | None = None
    ) -> Gara:
        """Avvia il primo turno della gara con controlli e sorteggio.

        `bye_to_last_inscribed` è la risposta del direttore alla domanda su chi
        riceve la X del primo turno (`None` = non gliel'abbiamo chiesta, resta
        quel che la gara ha già). Va registrata **prima** del sorteggio: sono
        le strategie a leggerla dalla gara. Vedi
        `models/matchmaking/bye_preference.py`.
        """
        from models.competition.models import Inscription
        import random
        import secrets

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.current_round != 0:
            raise ValueError("La gara è già iniziata!")

        if bye_to_last_inscribed is not None:
            gara.bye_to_last_inscribed = bool(bye_to_last_inscribed)

        # Verifica numero minimo partecipanti (escludi lista d'attesa)
        inscriptions = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_waitlist=False)
            .all()
        )
        if len(inscriptions) < gara.min_participants:
            raise ValueError(
                f"Servono almeno {gara.min_participants} iscritti per avviare la gara!"
            )

        # Seme del sorteggio: generato una volta sola e persistito, così il
        # tabellone e' riproducibile e contestabile a posteriori.
        # `cancel_first_round_startup` lo azzera, quindi riavviare il turno 1
        # significa risorteggiare davvero.
        if gara.draw_seed is None:
            gara.draw_seed = secrets.randbelow(2**31)

        # Genera il sorteggio iniziale
        random.shuffle(inscriptions)

        # Assegna ordine sorteggio
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i

        # Forfeit routing: identical pattern to _create_round_impl so that
        # players marked is_forfeit=True BEFORE gara start are properly
        # converted to walkovers by create_matches_from_pairings (both the
        # 2-player and trio branches). Computed once here because for the
        # random strategy we generate all rounds in the same transaction.
        from models.competition.withdraw_policy_service import WithdrawPolicyService

        forfeit_user_ids = WithdrawPolicyService.get_forfeit_user_ids(gara_id)

        # Gestione diversa per strategia Random vs altre strategie
        if gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value:
            # Per strategia Random: crea tutti i turni subito usando la strategia
            from models.matchmaking.bootstrap import get_registry

            registry = get_registry()

            # Mappatura nome strategia: enum -> registry
            strategy_mapping = {
                "random": "random_anti_rematch",
                "amalfi": "amalfi",
                "round_robin": "round_robin",
                "direct_elimination": "direct_elimination",
                "double_knockout": "double_knockout",
            }

            registry_name = strategy_mapping.get(gara.matchmaking_strategy)
            if not registry_name:
                raise ValueError(
                    f"Mapping per strategia {gara.matchmaking_strategy} non trovato"
                )

            strategy = registry.get(registry_name)
            if not strategy:
                raise ValueError(f"Strategia {registry_name} non trovata nel registry")

            # Crea tutti i turni contemporaneamente (per random)
            from models.competition.round_creation import (
                create_matches_from_pairings,
                resolve_round_overrides,
            )

            for round_num in range(1, gara.rounds_count + 1):
                # Flush before pairings so anti-rematch can see previous rounds
                if round_num > 1:
                    db.session.flush()

                pairings = strategy.create_round(gara, round_num)

                # Classifica di partenza: il sorteggio del primo turno.
                if round_num == 1:
                    from models.classification.seeding_service import SeedingService

                    SeedingService.persist_first_round_seeding(
                        gara_id, strategy, pairings
                    )

                # ADR-027: propaga override per turno.
                overrides = resolve_round_overrides(gara, round_num)
                create_matches_from_pairings(
                    gara=gara,
                    pairings=pairings,
                    round_number=round_num,
                    forfeit_user_ids=forfeit_user_ids,
                    **overrides,
                )

            gara.current_round = 1
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        else:
            # Per altre strategie: crea solo il primo turno
            from models.matchmaking.bootstrap import get_registry
            from models.competition.round_creation import (
                create_matches_from_pairings,
                resolve_round_overrides,
            )

            registry = get_registry()

            strategy_mapping = {
                "amalfi": "amalfi",
                "advanced_amalfi": "amalfi",
                "round_robin": "round_robin",
                "direct_elimination": "direct_elimination",
                "double_knockout": "double_knockout",
            }

            strategy_name = gara.matchmaking_strategy or "amalfi"
            registry_name = strategy_mapping.get(strategy_name, strategy_name)
            strategy = registry.get(registry_name)
            if not strategy:
                raise ValueError(f"Strategia {registry_name} non trovata nel registry")

            pairings = strategy.create_round(gara, 1)

            # Classifica di partenza: Amalfi l'ha già salvata durante il
            # pairing (le serve come input), le altre la derivano dagli
            # accoppiamenti appena generati.
            from models.classification.seeding_service import SeedingService

            SeedingService.persist_first_round_seeding(gara_id, strategy, pairings)

            # ADR-027: propaga override per turno (anche per il primo round).
            overrides = resolve_round_overrides(gara, 1)
            create_matches_from_pairings(
                gara=gara,
                pairings=pairings,
                round_number=1,
                forfeit_user_ids=forfeit_user_ids,
                **overrides,
            )

            gara.current_round = 1
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        # Assign tables to matches after round creation
        from models.match.table_assignment_service import TableAssignmentService

        TableAssignmentService.assign_tables_to_round(gara_id, round_number=1)

        # Chi ha la pagina della gara aperta deve vedere il turno comparire.
        # L'evento viaggia con questa transazione (ADR-057). Con la strategia
        # casuale i turni nascono tutti insieme, ma per chi guarda è un
        # avvio solo.
        from routes.sse import emit_gara_event

        emit_gara_event(
            gara_id, "round_started", {"gara_id": gara_id, "round_number": 1}
        )

        return gara

    @staticmethod
    @transactional(domain="competition")
    def update_round_progression(gara_id: int) -> None:
        """Aggiorna progressione dei turni e calcola classifiche se necessario."""
        from models.match.models import Match
        from models.status_enum import MatchStatus
        from models.classification.models import RoundClassification

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return

        for round_num in range(1, gara.rounds_count + 1):
            round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_num
            ).all()

            if not round_matches:
                break

            all_completed = all(
                m.status
                in [
                    MatchStatus.CLOSED_UNILATERALLY.value,
                    MatchStatus.CONFIRMED_BY_BOTH.value,
                ]
                for m in round_matches
            )

            if all_completed:
                if gara.current_round < round_num:
                    gara.current_round = round_num

                existing_classification = RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                ).first()

                if not existing_classification:
                    logger.debug("Calcolo la classifica del turno %s", round_num)
                    RoundClassification.calculate_classification_after_round(
                        gara_id, round_num
                    )
            else:
                break


__all__ = ["RoundService"]
