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

from models.base import db
from models.status_enum import GaraStatus
from .models import Gara, Inscription


class RoundService:
    """Service for managing round creation and progression.

    Extracted from GaraService to follow Single Responsibility Principle.
    Handles all round-related operations including match creation and strategy integration.
    """

    @staticmethod
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
                pairings = strategy.propose(gara, round_num)

                # Get discipline configuration for this round
                from models.competition.round_configuration import RoundConfiguration

                round_config = RoundConfiguration.get_for_gara_round(gara_id, round_num)
                round_discipline = round_config.discipline if round_config else None

                # Crea i match nel database
                for pairing in pairings:
                    if len(pairing.players) == 1 and pairing.is_bye:
                        # Match con X - assegnalo come completato con punteggio pieno
                        bye_score = (
                            gara.get_winning_score() if gara.best_of else gara.distance
                        )
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

            # Imposta il turno corrente al primo
            gara.current_round = 1
            # Use StateService instead of ProvaStateMachine for consistency
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        else:
            # Per altre strategie: crea solo il primo turno
            from utils import create_round_matches  # Import locale

            create_round_matches(gara, inscriptions, 1)

            gara.current_round = 1
            from models.competition.state_service import StateService

            gara = StateService.start_playing(gara)

        return gara

    @staticmethod
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

        if gara.current_round != 1:
            raise ValueError("Questa operazione è valida solo per il primo turno")

        # Verifica che non ci siano risultati inseriti
        matches_with_results = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=1)
            .filter(Match.winner_id.isnot(None))
            .count()
        )

        if matches_with_results > 0:
            raise ValueError(
                "Impossibile cancellare il primo turno: ci sono già dei risultati inseriti"
            )

        # Cancella tutti i match del primo turno
        matches = (
            db.session.query(Match).filter_by(gara_id=gara_id, round_number=1).all()
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

        db.session.commit()
        return gara

    @staticmethod
    def create_round_with_strategy(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Crea un turno usando la strategia configurata nella gara.

        Returns:
            Tuple con (total_matches, normal_matches, bye_matches, trio_matches)
        """
        from models.match.models import Match, TrioMatch

        try:
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

            # Se è Amalfi, usa il binding esistente per compatibilità
            if strategy_name in ["amalfi", "advanced_amalfi"]:
                from amalfi import create_amalfi_round_matches

                create_amalfi_round_matches(gara, round_number)
            else:
                # Usa il registry per altre strategie
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

                registry_name = strategy_mapping.get(strategy_name, strategy_name)
                strategy = registry.get(registry_name)
                if not strategy:
                    raise ValueError(f"Strategia '{strategy_name}' non trovata")

                # Genera gli abbinamenti usando l'interfaccia della strategia
                pairings = strategy.propose(gara, round_number)

                # Crea i match nel database
                for pairing in pairings:
                    if len(pairing.players) == 1 and pairing.is_bye:
                        # Match con X - assegnalo come completato con punteggio pieno
                        bye_score = (
                            gara.get_winning_score() if gara.best_of else gara.distance
                        )
                        match = Match(
                            gara_id=gara_id,
                            round_number=round_number,
                            player1_id=pairing.players[0],
                            player2_id=None,
                            is_bye=True,
                            player1_score=bye_score,
                            winner_id=pairing.players[0],
                            status="completed",
                            discipline=discipline_override,
                        )
                        db.session.add(match)
                    elif len(pairing.players) == 2 and not pairing.is_bye:
                        # Match normale
                        match = Match(
                            gara_id=gara_id,
                            round_number=round_number,
                            player1_id=pairing.players[0],
                            player2_id=pairing.players[1],
                            is_bye=False,
                            discipline=discipline_override,
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
                            discipline=discipline_override,
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

            db.session.commit()
            return (total_matches, normal_matches, bye_matches, trio_matches)

        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Errore durante la creazione del turno: {str(e)}")

    @staticmethod
    def preview_round_with_strategy(gara_id: int, round_number: int) -> Dict[str, Any]:
        """Anteprima di un turno usando la strategia configurata nella gara.

        Returns:
            Dict con informazioni sull'anteprima
        """
        try:
            gara = db.session.get(Gara, gara_id)
            if not gara:
                raise ValueError(f"Gara {gara_id} non trovata")

            # Verifica precondizioni
            if round_number < 1 or round_number > gara.rounds_count:
                raise ValueError(f"Turno {round_number} non valido")

            # Ottieni la strategia configurata
            strategy_name = gara.matchmaking_strategy or "amalfi"

            if strategy_name in ["amalfi", "advanced_amalfi"]:
                # Per Amalfi l'anteprima è gestita dal motore specifico
                raise ValueError("Preview Amalfi deve essere gestito dal controller")
            else:
                # Usa il registry per altre strategie
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

                registry_name = strategy_mapping.get(strategy_name, strategy_name)
                strategy = registry.get(registry_name)
                if not strategy:
                    raise ValueError(f"Strategia '{strategy_name}' non trovata")

                # Ottieni i giocatori iscritti (escludi lista d'attesa)
                from models.user.models import User

                # Genera gli abbinamenti di anteprima usando l'interfaccia della strategia
                pairings = strategy.preview(gara, round_number)

                # Converti in formato per il template
                matches = []
                normal_count = 0
                bye_count = 0
                trio_count = 0

                for pairing in pairings:
                    if len(pairing.players) == 1 and pairing.is_bye:
                        # Match con X
                        bye_count += 1
                        player1 = User.query.get(pairing.players[0])
                        matches.append(
                            {
                                "player1": {
                                    "id": player1.id,
                                    "username": player1.username,
                                },
                                "player2": None,
                                "is_bye": True,
                                "type": "bye",
                            }
                        )
                    elif len(pairing.players) == 2 and not pairing.is_bye:
                        # Match normale
                        normal_count += 1
                        player1 = User.query.get(pairing.players[0])
                        player2 = User.query.get(pairing.players[1])
                        matches.append(
                            {
                                "player1": {
                                    "id": player1.id,
                                    "username": player1.username,
                                },
                                "player2": {
                                    "id": player2.id,
                                    "username": player2.username,
                                },
                                "is_bye": False,
                                "type": "normal",
                            }
                        )
                    elif len(pairing.players) == 3:
                        # Match trio
                        trio_count += 1
                        players = [User.query.get(pid) for pid in pairing.players]
                        matches.append(
                            {
                                "players": [
                                    {"id": p.id, "username": p.username}
                                    for p in players
                                ],
                                "is_trio": True,
                                "type": "trio",
                            }
                        )

                return {
                    "matches": matches,
                    "stats": {
                        "total": len(matches),
                        "normal": normal_count,
                        "bye": bye_count,
                        "trio": trio_count,
                    },
                }

        except Exception as e:
            raise ValueError(f"Errore durante l'anteprima del turno: {str(e)}")

    @staticmethod
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
            all_completed = all(
                m.status == MatchStatus.COMPLETED.value for m in round_matches
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

        db.session.commit()


__all__ = ["RoundService"]
