"""
Module: models/matchmaking/strategies/round_robin.py
Purpose: Round Robin pairing strategy implementation
Requirements: SPECIFICHE.md - Round Robin campionato format
"""

from __future__ import annotations

from typing import Sequence, List, Tuple, Dict, Any, TYPE_CHECKING

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    pass


class RoundRobinStrategy(BaseStrategy):
    """Round Robin pairing strategy where everyone plays everyone else."""

    # PairingStrategy metadata
    name = "round_robin"
    display_name = "Round Robin"
    description = "Round Robin campionato where everyone plays everyone else"
    min_players = 3
    max_players = 16
    supports_byes = True
    requires_classification = False
    # Lo schedule è deterministico a partire dall'ordine di iscrizione: quello
    # è l'ordine di partenza, letto dagli accoppiamenti del primo turno.
    persists_seeding = True

    def __init__(self):
        super().__init__()
        self.strategy_name = "round_robin"

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        """Validate Round Robin specific requirements."""
        errors = []
        warnings = []

        try:
            # Get active inscriptions
            inscriptions = getattr(gara, "inscriptions", [])
            active_inscriptions = [
                i
                for i in inscriptions
                if not getattr(i, "is_withdrawn", False)
                and not getattr(i, "is_waitlist", False)
            ]
            player_count = len(active_inscriptions)

            # Calculate required rounds
            required_rounds = (
                (player_count - 1 if player_count % 2 == 0 else player_count)
                if player_count > 0
                else 0
            )

            # Check if gara has rounds_count and validate
            if hasattr(gara, "rounds_count"):
                rounds_count = getattr(gara, "rounds_count", 0)
                if rounds_count and rounds_count < required_rounds:
                    errors.append(
                        f"Round Robin requires {required_rounds} rounds, "
                        f"but gara has {rounds_count}"
                    )

        except Exception as e:
            warnings.append(f"Round Robin validation warning: {str(e)}")

        return {"errors": errors, "warnings": warnings}

    def preview(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(gara, round_number)

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        """Generate Round Robin pairings for the round."""
        gara = processed_data["gara"]
        return self._generate_round_pairings(gara, round_number)

    def _generate_round_pairings(
        self, gara: object, round_number: int
    ) -> List[Pairing]:
        """Generate pairings for a specific round using Round Robin algorithm."""
        try:
            # Get active players
            inscriptions = getattr(gara, "inscriptions", [])
            active_inscriptions = [
                i
                for i in inscriptions
                if not i.is_withdrawn and not getattr(i, "is_waitlist", False)
            ]
            player_ids = [i.user_id for i in active_inscriptions]

            if len(player_ids) < 2:
                return []

            # Generate complete round robin schedule
            schedule = self._generate_round_robin_schedule(player_ids)

            # Return pairings for the specific round
            if round_number <= len(schedule):
                round_pairings = schedule[round_number - 1]  # 0-indexed
                return [
                    Pairing(
                        players=pairing,
                        round_number=round_number,
                        is_bye=(len(pairing) == 1),
                    )
                    for pairing in round_pairings
                ]

            return []

        except Exception as e:
            print(f"Error generating Round Robin pairings: {e}")
            return []

    # Sentinella "giocatore fantasma" per il caso dispari: chi viene accoppiato
    # con essa in un dato turno riposa (bye). None è sicuro perché gli id reali
    # sono interi positivi.
    _BYE_SENTINEL = None

    def _generate_round_robin_schedule(
        self, player_ids: List[int]
    ) -> List[List[Tuple[int, ...]]]:
        """Generate complete Round Robin schedule using the classic polygon method.

        Per N dispari si aggiunge un "giocatore fantasma" (`_BYE_SENTINEL`) per
        rendere il numero pari: si applica lo stesso metodo del poligono del
        caso pari (fissa il primo, ruota gli altri) e chi è accoppiato col
        fantasma in quel turno riposa. Così la GEOMETRIA degli accoppiamenti
        ruota davvero ad ogni turno, garantendo che ogni coppia si incontri
        esattamente una volta e che ogni giocatore abbia esattamente un bye.

        (Bug pregresso: il vecchio ramo dispari ricalcolava gli attivi
        dall'ordine fisso e accoppiava sempre simmetricamente, senza ruotare —
        coppie ripetute e coppie mai giocate.)
        """
        n = len(player_ids)

        if n < 2:
            return []

        # Round robin a giro (circle method). Con N dispari il fantasma occupa
        # un posto e produce il bye; la lunghezza diventa pari e si ruotano gli
        # altri tenendo fisso il primo elemento.
        players: List[int] = player_ids[:]
        if n % 2 == 1:
            players.append(self._BYE_SENTINEL)  # type: ignore[arg-type]

        size = len(players)  # sempre pari
        rounds = size - 1  # == n se dispari, n-1 se pari

        schedule: List[List[Tuple[int, ...]]] = []
        for _ in range(rounds):
            round_pairings: List[Tuple[int, ...]] = []

            for i in range(size // 2):
                player1 = players[i]
                player2 = players[size - 1 - i]

                if player1 is self._BYE_SENTINEL:
                    round_pairings.append((player2,))
                elif player2 is self._BYE_SENTINEL:
                    round_pairings.append((player1,))
                else:
                    round_pairings.append((player1, player2))

            schedule.append(round_pairings)

            # Ruota: tieni fisso il primo, sposta gli altri di una posizione.
            if size > 2:
                first = players[0]
                rest = players[1:]
                players = [first] + [rest[-1]] + rest[:-1]

        return schedule

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Calculate total rounds needed for Round Robin."""
        if player_count < 2:
            return 0
        return player_count - 1 if player_count % 2 == 0 else player_count

    def get_matches_per_player(self, player_count: int) -> int:
        """Calculate matches per player in Round Robin."""
        return max(0, player_count - 1)


class RoundRobinPairingStrategy(RoundRobinStrategy):
    """Alias for compatibility with existing strategy registry."""
