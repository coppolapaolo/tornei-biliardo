"""
Module: models/matchmaking/strategies/round_robin.py
Purpose: Round Robin pairing strategy implementation
Requirements: SPECIFICHE.md - Round Robin campionato format
"""

from __future__ import annotations

import logging
from typing import Sequence, List, Optional, Tuple, Dict, Any, TYPE_CHECKING

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    # Lo schedule è deterministico a partire dall'ordine del sorteggio: quello
    # è l'ordine di partenza, letto dagli accoppiamenti del primo turno, e dal
    # turno 2 il calendario si ricostruisce da lì (`_calendar_order`).
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
            player_ids = self._calendar_order(gara)
            if len(player_ids) < 2:
                return []

            # Chi non gioca piu' (escluso dalla regola EXCLUDE, o comunque non
            # piu' fra gli attivi) resta al suo posto nel calendario e diventa
            # un "fantasma": il suo avversario di quel turno riposa, come
            # vuole la gestione del dispari (SPECIFICHE.md, «policy per il
            # forfait»). Con FORFEIT invece l'iscrizione resta attiva: la
            # partita nasce e `create_matches_from_pairings` la chiude a
            # tavolino.
            active_ids = {i.user_id for i in self._get_active_inscriptions(gara)}

            schedule = self._generate_round_robin_schedule(player_ids)
            if round_number > len(schedule):
                return []

            pairings: List[Pairing] = []
            for pairing in schedule[round_number - 1]:
                players = tuple(p for p in pairing if p in active_ids)
                if not players:
                    continue
                pairings.append(
                    Pairing(
                        players=players,
                        round_number=round_number,
                        is_bye=(len(players) == 1),
                    )
                )
            return pairings

        except Exception:
            # La lista vuota non e' piu' un esito silenzioso: dal 2026-08-28
            # `_create_round_impl` rifiuta un turno senza accoppiamenti (issue
            # #239), quindi chi ha chiesto il turno vede un errore. Quello che
            # mancava era il **perche'**: l'eccezione originale finiva in un
            # `print` e non arrivava a GlitchTip, lasciando a valle solo un
            # «non produce accoppiamenti» senza causa. `exc_info=True` porta
            # lo stack dove qualcuno lo guarda.
            logger.error(
                "Errore nella generazione degli abbinamenti Round Robin "
                "(gara=%s, turno=%s)",
                getattr(gara, "id", None),
                round_number,
                exc_info=True,
            )
            return []

    def _calendar_order(self, gara: object) -> List[int]:
        """L'ordine su cui si costruisce il calendario, fisso per tutta la gara.

        Il calendario si genera di nuovo a ogni turno, quindi l'ordine deve
        essere lo stesso ogni volta. Dal turno 2 in poi viene dalla classifica
        di partenza persistita (`SeedingService`), che si scrive al turno 1 e
        contiene anche chi nel frattempo si e' ritirato: con la regola EXCLUDE
        la sua iscrizione viene cancellata, e ricalcolare su chi resta
        spostava tutte le coppie dei turni successivi.

        Prima che il seeding esista (il turno 1) l'ordine e' quello del
        sorteggio scritto da `start_first_round` in `initial_order`, e a
        parita' l'ordine d'iscrizione. Fino al 2026-10-06 si leggeva
        `gara.inscriptions`, una relazione senza ordinamento: il sorteggio non
        contava, e la stabilita' fra un turno e l'altro dipendeva dall'ordine
        in cui SQLite restituiva le righe.
        """
        active = self._get_active_inscriptions(gara)
        seeding = self._seeding_order(gara)
        if not seeding:
            ordered = sorted(
                active,
                key=lambda i: (
                    getattr(i, "initial_order", None) is None,
                    getattr(i, "initial_order", None) or 0,
                    getattr(i, "id", 0) or 0,
                ),
            )
            return [i.user_id for i in ordered]

        order = self.order_from_seeding(seeding)
        # Chi e' entrato dopo l'avvio (una promozione dalla lista d'attesa)
        # non ha un posto nel seeding: si accoda, in ordine d'iscrizione.
        known = set(order)
        late = sorted(
            (i for i in active if i.user_id not in known),
            key=lambda i: getattr(i, "id", 0) or 0,
        )
        return order + [i.user_id for i in late]

    @staticmethod
    def _seeding_order(gara: object) -> List[int]:
        """La classifica di partenza della gara, o lista vuota se non c'e'."""
        gara_id = getattr(gara, "id", None)
        if gara_id is None:
            return []
        from models.classification.seeding_service import SeedingService

        return [rc.user_id for rc in SeedingService.get_seeding(gara_id)]

    @classmethod
    def order_from_seeding(cls, seeding: List[int]) -> List[int]:
        """Ricostruisce l'ordine del calendario dalla classifica di partenza.

        Il seeding non e' l'ordine del calendario: `SeedingService` lo legge
        dagli abbinamenti del turno 1, nell'ordine in cui i giocatori vi
        compaiono. Col metodo del poligono il turno 1 accoppia la posizione
        `i` con la `size - 1 - i`, quindi il seeding elenca le posizioni
        0, size-1, 1, size-2, ... saltando il fantasma del dispari (che sta in
        coda). Qui si fa il percorso inverso: e' l'unico ordine che rigenera
        esattamente il turno 1 gia' giocato.
        """
        n = len(seeding)
        size = n + (n % 2)
        visit: List[int] = []
        for i in range(size // 2):
            visit.extend((i, size - 1 - i))
        if n % 2 == 1:
            visit.remove(size - 1)  # il posto del fantasma

        order: List[int] = [0] * n
        for slot, player_id in zip(visit, seeding):
            order[slot] = player_id
        return order

    # Sentinella "giocatore fantasma" per il caso dispari: chi viene accoppiato
    # con essa in un dato turno riposa (bye). None è sicuro perché gli id reali
    # sono interi positivi.
    _BYE_SENTINEL: Optional[int] = None

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

        # Round robin a giro (circle method). Con N dispari il fantasma (la
        # sentinella None) occupa un posto e produce il bye; la lunghezza
        # diventa pari e si ruotano gli altri tenendo fisso il primo elemento.
        players: List[Optional[int]] = list(player_ids)
        if n % 2 == 1:
            players.append(self._BYE_SENTINEL)

        size = len(players)  # sempre pari
        rounds = size - 1  # == n se dispari, n-1 se pari

        schedule: List[List[Tuple[int, ...]]] = []
        for _ in range(rounds):
            round_pairings: List[Tuple[int, ...]] = []

            for i in range(size // 2):
                # Filtra la sentinella: se uno dei due slot è il fantasma,
                # l'altro giocatore riposa (tupla a 1 → bye); altrimenti coppia.
                pair = tuple(
                    p
                    for p in (players[i], players[size - 1 - i])
                    if p is not self._BYE_SENTINEL
                )
                round_pairings.append(pair)

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
