"""
Round Service - Competition Domain

Facade for round lifecycle management. Delegates to:
- round_creation.py: Round creation and match generation
- round_cancellation.py: Round cancellation operations

Keeps start_first_round and update_round_progression locally as they
are orchestrator methods tightly coupled to gara state transitions.
"""

from __future__ import annotations

from models.base import db, transactional
from .models import Gara
from .round_creation import RoundCreationService
from .round_cancellation import RoundCancellationService


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
    def start_first_round(gara_id: int) -> Gara:
        """Avvia il primo turno della gara con controlli e sorteggio."""
        from models.competition.models import Inscription
        import random

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.current_round != 0:
            raise ValueError("La gara è già iniziata!")

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

        # Genera il sorteggio iniziale
        random.shuffle(inscriptions)

        # Assegna ordine sorteggio
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i

        # Gestione diversa per strategia Random vs altre strategie
        if gara.matchmaking_strategy == "random":
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

            # Crea tutti i turni contemporaneamente
            from models.match.models import Match

            for round_num in range(1, gara.rounds_count + 1):
                # Flush before generating pairings so anti-rematch can see previous rounds
                if round_num > 1:
                    db.session.flush()

                pairings = strategy.create_round(gara, round_num)

                # Get round configuration for this round (discipline and distance overrides)
                from models.competition.round_configuration import RoundConfiguration

                round_config = RoundConfiguration.get_for_gara_round(gara_id, round_num)
                round_discipline = round_config.discipline if round_config else None
                round_distance = round_config.get_effective_distance(gara.distance) if round_config else gara.distance

                # Crea i match nel database
                for pairing in pairings:
                    if len(pairing.players) == 1 and pairing.is_bye:
                        bye_score = round_distance
                        match = Match(
                            gara_id=gara_id,
                            round_number=round_num,
                            player1_id=pairing.players[0],
                            player2_id=None,
                            is_bye=True,
                            player1_score=bye_score,
                            winner_id=pairing.players[0],
                            status="completed",
                            discipline=round_discipline,
                            match_distance=round_distance,
                        )
                        db.session.add(match)
                    elif len(pairing.players) == 2 and not pairing.is_bye:
                        match = Match(
                            gara_id=gara_id,
                            round_number=round_num,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            is_bye=False,
                            discipline=round_discipline,
                            match_distance=round_distance,
                            is_multi_set=gara.is_multi_set,
                        )
                        db.session.add(match)
                    elif len(pairing.players) == 3:
                        from models.match.models import TrioMatch

                        match = Match(
                            gara_id=gara_id,
                            round_number=round_num,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            is_bye=False,
                            is_trio=True,
                            discipline=round_discipline,
                            match_distance=round_distance,
                        )
                        db.session.add(match)

                        trio_match = TrioMatch(
                            match=match,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            player3_id=pairing.players[2],
                        )
                        db.session.add(trio_match)
                        trio_match.initialize_matchup()

            gara.current_round = 1
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        else:
            # Per altre strategie: crea solo il primo turno
            from models.matchmaking.bootstrap import get_registry
            from models.match.models import Match

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

            from models.competition.round_configuration import RoundConfiguration

            round_config = RoundConfiguration.get_for_gara_round(gara_id, 1)
            round_discipline = round_config.discipline if round_config else None
            round_distance = round_config.get_effective_distance(gara.distance) if round_config else gara.distance

            for pairing in pairings:
                if len(pairing.players) == 1 and pairing.is_bye:
                    bye_score = round_distance
                    match = Match(
                        gara_id=gara_id,
                        round_number=1,
                        player1_id=pairing.players[0],
                        player2_id=None,
                        is_bye=True,
                        player1_score=bye_score,
                        winner_id=pairing.players[0],
                        status="completed",
                        discipline=round_discipline,
                        match_distance=round_distance,
                    )
                    db.session.add(match)
                elif len(pairing.players) == 2 and not pairing.is_bye:
                    match = Match(
                        gara_id=gara_id,
                        round_number=1,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        is_bye=False,
                        discipline=round_discipline,
                        match_distance=round_distance,
                        is_multi_set=gara.is_multi_set,
                    )
                    db.session.add(match)
                elif len(pairing.players) == 3:
                    from models.match.models import TrioMatch

                    match = Match(
                        gara_id=gara_id,
                        round_number=1,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        is_bye=False,
                        is_trio=True,
                        discipline=round_discipline,
                        match_distance=round_distance,
                    )
                    db.session.add(match)

                    trio_match = TrioMatch(
                        match=match,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        player3_id=pairing.players[2],
                    )
                    db.session.add(trio_match)
                    trio_match.initialize_matchup()

            gara.current_round = 1
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        # Assign tables to matches after round creation
        from models.match.table_assignment_service import TableAssignmentService

        TableAssignmentService.assign_tables_to_round(gara_id, round_number=1)

        return gara

    @staticmethod
    @transactional(domain="competition")
    def update_round_progression(gara_id: int) -> None:
        """Aggiorna la progressione dei turni e calcola le classifiche quando necessario."""
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
                m.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
                for m in round_matches
            )

            if all_completed:
                if gara.current_round < round_num:
                    gara.current_round = round_num

                existing_classification = RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                ).first()

                if not existing_classification:
                    print(f"Calculating classification for round {round_num}")
                    RoundClassification.calculate_classification_after_round(
                        gara_id, round_num
                    )
            else:
                break


__all__ = ["RoundService"]
