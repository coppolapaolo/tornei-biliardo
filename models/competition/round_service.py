"""
Round Service - Competition Domain

Service for managing round creation, progression, and match orchestration.
Extracted from GaraService to follow Single Responsibility Principle.

Business Operations:
- Round lifecycle management (start, cancel, progress)
- Match creation using different strategies
- Round preview without database side effects
- Integration with matchmaking strategies

Author: Refactoring Phase 1 - Task 1.2 (GaraService Decomposition)
Created: 2025-01-18
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime

from models.base import db, transactional
from models.status_enum import GaraStatus
from .models import Gara, Inscription


class RoundService:
    """Service for managing round creation and progression.

    Extracted from GaraService to follow Single Responsibility Principle.
    Handles all round-related operations including match creation and strategy integration.
    """

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
                # (SQLAlchemy autoflush should handle this, but explicit is safer)
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
                        # Match con X - assegnalo come completato con punteggio pieno
                        bye_score = round_distance  # Use round-specific distance
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
                        # Match normale
                        match = Match(
                            gara_id=gara_id,
                            round_number=round_num,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            is_bye=False,
                            discipline=round_discipline,
                            match_distance=round_distance,
                        )
                        db.session.add(match)
                    elif len(pairing.players) == 3:
                        # Match trio
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

                        # Crea il record TrioMatch con tutti e tre i giocatori
                        trio_match = TrioMatch(
                            match=match,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            player3_id=pairing.players[2],
                        )
                        db.session.add(trio_match)
                        trio_match.initialize_matchup()

            # Imposta il turno corrente al primo
            gara.current_round = 1
            # Use StateService instead of ProvaStateMachine for consistency
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        else:
            # Per altre strategie: crea solo il primo turno usando MatchmakingService
            from models.matchmaking.bootstrap import get_registry
            from models.match.models import Match

            registry = get_registry()

            # Mappatura nome strategia: enum -> registry
            strategy_mapping = {
                "amalfi": "amalfi",
                "advanced_amalfi": "amalfi",  # Alias per compatibilità
                "round_robin": "round_robin",
                "direct_elimination": "direct_elimination",
                "double_knockout": "double_knockout",
            }

            strategy_name = gara.matchmaking_strategy or "amalfi"
            registry_name = strategy_mapping.get(strategy_name, strategy_name)
            strategy = registry.get(registry_name)
            if not strategy:
                raise ValueError(f"Strategia {registry_name} non trovata nel registry")

            # Genera gli abbinamenti per il primo turno
            pairings = strategy.create_round(gara, 1)

            # Get round configuration for round 1 (discipline and distance overrides)
            from models.competition.round_configuration import RoundConfiguration

            round_config = RoundConfiguration.get_for_gara_round(gara_id, 1)
            round_discipline = round_config.discipline if round_config else None
            round_distance = round_config.get_effective_distance(gara.distance) if round_config else gara.distance

            # Crea i match nel database
            for pairing in pairings:
                if len(pairing.players) == 1 and pairing.is_bye:
                    # Match con X - assegnalo come completato con punteggio pieno
                    bye_score = round_distance  # Use round-specific distance
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
                    # Match normale
                    match = Match(
                        gara_id=gara_id,
                        round_number=1,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        is_bye=False,
                        discipline=round_discipline,
                        match_distance=round_distance,
                    )
                    db.session.add(match)
                elif len(pairing.players) == 3:
                    # Match trio
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

                    # Crea il record TrioMatch con tutti e tre i giocatori
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
    def cancel_first_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del primo turno se non sono stati inseriti risultati.

        Riporta la gara allo stato 'inscription' e rimuove tutte le partite del primo turno.
        Utilizzabile solo se il primo turno è stato avviato ma nessun risultato è stato inserito.
        """
        from models.match.models import Match, TrioMatch
        from models.status_enum import MatchStatus

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Per strategie che creano tutti i round all'avvio (es. Random),
        # permettiamo l'annullamento indipendentemente da current_round
        if not gara.creates_all_rounds_at_startup() and gara.current_round != 1:
            raise ValueError("Questa operazione è valida solo per il primo turno")

        # Verifica che non ci siano risultati inseriti in NESSUN round
        # (esclusi i bye che sono auto-completati)
        matches_with_results = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id)
            .filter(Match.winner_id.isnot(None))
            .filter(Match.is_bye == False)  # noqa: E712 - Exclude bye matches
            .count()
        )

        if matches_with_results > 0:
            raise ValueError(
                "Impossibile cancellare l'avvio: ci sono già dei risultati inseriti"
            )

        # Cancella le classifiche della gara
        from models.classification.models import RoundClassification, GaraClassification
        from models.competition.gara_challenge import (
            GaraChallenge,
            GaraChallengeAttempt,
            GaraChallengeClassification,
        )

        RoundClassification.query.filter_by(gara_id=gara_id).delete()
        GaraClassification.query.filter_by(gara_id=gara_id).delete()

        # Cancella tentativi e classifiche challenge (se presenti)
        GaraChallengeClassification.query.filter_by(gara_id=gara_id).delete()

        # Cancella i tentativi challenge associati alle challenge di questa gara
        gara_challenge_ids = [
            gc.id for gc in GaraChallenge.query.filter_by(gara_id=gara_id).all()
        ]
        if gara_challenge_ids:
            GaraChallengeAttempt.query.filter(
                GaraChallengeAttempt.gara_challenge_id.in_(gara_challenge_ids)
            ).delete(synchronize_session=False)

        # Cancella TUTTI i match della gara
        # Questo è necessario specialmente per la strategia 'random' che pre-genera tutto
        matches = (
            db.session.query(Match).filter_by(gara_id=gara_id).all()
        )

        # Prima cancella i TrioMatch associati
        for match in matches:
            trio_matches = (
                db.session.query(TrioMatch).filter_by(match_id=match.id).all()
            )
            for trio in trio_matches:
                db.session.delete(trio)

        # Poi cancella i match
        for match in matches:
            db.session.delete(match)

        # Riporta la gara allo stato inscription
        gara.current_round = 0
        from models.competition.state_service import StateService

        if gara.status == GaraStatus.PLAYING.value:
            # Note: StateService doesn't have a direct method to go back to inscription
            # For now, we'll manually set the status
            gara.status = GaraStatus.INSCRIPTION.value
            db.session.add(gara)

        return gara

    @staticmethod
    @transactional(domain="competition")
    def create_round_with_strategy(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Crea un turno usando la strategia configurata nella gara.

        Returns:
            Tuple con (total_matches, normal_matches, bye_matches, trio_matches)
        """
        return RoundService._create_round_impl(
            gara_id, round_number, discipline_override
        )

    @staticmethod
    @transactional(domain="competition")
    def start_next_round(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int, int]:
        """Create a round and advance the gara state.

        Combines round creation, state transition to PLAYING,
        current_round update, and table assignment in one transaction.

        Returns:
            Tuple: (total, normal, bye, trio, tables_assigned)
        """
        from models.competition.state_service import StateService
        from models.match.table_assignment_service import TableAssignmentService

        total, n_normal, n_bye, n_trio = RoundService._create_round_impl(
            gara_id, round_number, discipline_override
        )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.status != GaraStatus.PLAYING.value:
            StateService.start_playing(gara)
            db.session.refresh(gara)

        gara.current_round = round_number

        tables_assigned = TableAssignmentService.assign_tables_to_round(
            gara_id, round_number
        )

        return total, n_normal, n_bye, n_trio, tables_assigned

    @staticmethod
    def _create_round_impl(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Core round creation logic (no @transactional — called within a transaction)."""
        from models.match.models import Match, TrioMatch

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica precondizioni
        if round_number < 1 or round_number > gara.rounds_count:
            raise ValueError(f"Turno {round_number} non valido")

        # Verifica se esistono già match per questo turno
        existing_matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .count()
        )
        if existing_matches > 0:
            # I match esistono già, ritorna i conteggi attuali
            matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number)
                .all()
            )
            normal_matches = sum(
                1
                for m in matches
                if not m.is_bye and not getattr(m, "is_trio", False)
            )
            bye_matches = sum(1 for m in matches if m.is_bye)
            trio_matches = sum(1 for m in matches if getattr(m, "is_trio", False))
            return (len(matches), normal_matches, bye_matches, trio_matches)

        # Ottieni la strategia configurata
        strategy_name = gara.matchmaking_strategy or "amalfi"

        # Usa il registry per tutte le strategie
        from models.matchmaking.bootstrap import get_registry

        registry = get_registry()

        # Mappatura nome strategia: enum -> registry
        strategy_mapping = {
            "random": "random_anti_rematch",
            "amalfi": "amalfi",
            "advanced_amalfi": "amalfi",  # Alias per compatibilità
            "round_robin": "round_robin",
            "direct_elimination": "direct_elimination",
            "double_knockout": "double_knockout",
        }

        registry_name = strategy_mapping.get(strategy_name, strategy_name)
        strategy = registry.get(registry_name)
        if not strategy:
            raise ValueError(f"Strategia '{strategy_name}' non trovata")

        # Genera gli abbinamenti usando l'interfaccia della strategia
        pairings = strategy.create_round(gara, round_number)

        # Get forfeit players for this gara to handle completed matches
        from models.competition.withdraw_policy_service import WithdrawPolicyService
        forfeit_user_ids = set(
            inscription.user_id
            for inscription in WithdrawPolicyService.get_forfeit_inscriptions(gara_id)
        )

        # Get round configuration for distance override
        from models.competition.round_configuration import RoundConfiguration
        round_config = RoundConfiguration.get_for_gara_round(gara_id, round_number)
        round_distance = round_config.get_effective_distance(gara.distance) if round_config else gara.distance
        # Use discipline_override if provided, otherwise check round_config
        effective_discipline = discipline_override or (round_config.discipline if round_config else None)

        # Crea i match nel database
        for pairing in pairings:
            if len(pairing.players) == 1 and pairing.is_bye:
                # Match con X - assegnalo come completato con punteggio pieno
                bye_score = round_distance  # Use round-specific distance
                match = Match(
                    gara_id=gara_id,
                    round_number=round_number,
                    player1_id=pairing.players[0],
                    player2_id=None,
                    is_bye=True,
                    player1_score=bye_score,
                    winner_id=pairing.players[0],
                    status="completed",
                    discipline=effective_discipline,
                    match_distance=round_distance,
                )
                db.session.add(match)
            elif len(pairing.players) == 2 and not pairing.is_bye:
                # Check if any player is forfeit - create completed match
                player1_forfeit = pairing.players[0] in forfeit_user_ids
                player2_forfeit = pairing.players[1] in forfeit_user_ids

                if player1_forfeit or player2_forfeit:
                    # At least one player forfeited - match is auto-completed
                    winning_score = round_distance  # Use round-specific distance

                    if player1_forfeit and player2_forfeit:
                        # Both forfeit - player1 wins (arbitrary but consistent)
                        winner_id = pairing.players[0]
                        player1_score = winning_score
                        player2_score = 0
                    elif player1_forfeit:
                        # Player1 forfeit - player2 wins
                        winner_id = pairing.players[1]
                        player1_score = 0
                        player2_score = winning_score
                    else:
                        # Player2 forfeit - player1 wins
                        winner_id = pairing.players[0]
                        player1_score = winning_score
                        player2_score = 0

                    match = Match(
                        gara_id=gara_id,
                        round_number=round_number,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        is_bye=False,
                        player1_score=player1_score,
                        player2_score=player2_score,
                        winner_id=winner_id,
                        status="completed",
                        discipline=effective_discipline,
                        match_distance=round_distance,
                    )
                    db.session.add(match)
                else:
                    # Match normale - nessun forfait
                    match = Match(
                        gara_id=gara_id,
                        round_number=round_number,
                        player1_id=pairing.players[0],
                        player2_id=pairing.players[1],
                        is_bye=False,
                        discipline=effective_discipline,
                        match_distance=round_distance,
                    )
                    db.session.add(match)
            elif len(pairing.players) == 3:
                # Match trio
                match = Match(
                    gara_id=gara_id,
                    round_number=round_number,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    is_bye=False,
                    is_trio=True,
                    discipline=effective_discipline,
                    match_distance=round_distance,
                )
                db.session.add(match)
                db.session.flush()  # Assicura che il match abbia un ID

                # Crea il record TrioMatch con tutti e tre i giocatori
                trio_match = TrioMatch(
                    match_id=match.id,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    player3_id=pairing.players[2],
                )
                db.session.add(trio_match)
                db.session.flush()  # Assicura che il TrioMatch sia visibile
                trio_match.initialize_matchup()

        # Conta i risultati
        matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .all()
        )
        normal_matches = sum(1 for m in matches if not m.is_bye and not m.is_trio)
        bye_matches = sum(1 for m in matches if m.is_bye)
        trio_matches = (
            db.session.query(TrioMatch)
            .join(Match)
            .filter(Match.gara_id == gara_id, Match.round_number == round_number)
            .count()
        )
        total_matches = len(matches)

        # Lock previous round matches when creating a new round
        if round_number > 1:
            previous_round_matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number - 1)
                .all()
            )
            for match in previous_round_matches:
                match.round_locked = True
                db.session.add(match)

        return (total_matches, normal_matches, bye_matches, trio_matches)


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

        # Controlla ogni turno per vedere se è completato e aggiorna current_round
        for round_num in range(1, gara.rounds_count + 1):
            round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_num
            ).all()

            if not round_matches:
                # Nessun match in questo turno, ferma qui
                break

            # Controlla se tutti i match del turno sono completati
            # Note: VALIDATED (bilateral player confirmation) also counts as finished
            all_completed = all(
                m.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]
                for m in round_matches
            )

            if all_completed:
                # Aggiorna current_round se necessario
                if gara.current_round < round_num:
                    gara.current_round = round_num

                # Calcola/aggiorna classificazione per questo turno se non esiste
                existing_classification = RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                ).first()

                if not existing_classification:
                    print(f"Calculating classification for round {round_num}")
                    RoundClassification.calculate_classification_after_round(
                        gara_id, round_num
                    )
            else:
                # Turno incompleto, ferma qui
                break


    @staticmethod
    @transactional(domain="competition")
    def cancel_current_round_startup(gara_id: int) -> Gara:
        """Cancella l'avvio del turno corrente se non sono stati inseriti risultati.

        Decrementa il current_round e rimuove tutte le partite del turno corrente.
        Utilizzabile solo se non sono stati inseriti risultati (anche parziali).
        """
        from models.match.models import Match, TrioMatch

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


__all__ = ["RoundService"]
