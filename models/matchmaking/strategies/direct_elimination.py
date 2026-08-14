"""
Module: models/matchmaking/strategies/direct_elimination.py
Purpose: Direct Elimination (single knockout) pairing strategy implementation
Requirements: SPECIFICHE.md - Direct elimination campionato format

Il tabellone e' **persistito** sui Match (`bracket_type` / `bracket_round` /
`bracket_slot`, vedi Step 2): questa strategia lo costruisce al primo turno e
dal secondo si limita a leggerlo. L'aritmetica sta in
``models/matchmaking/bracket.py``, che non conosce ne' Flask ne' il DB.
"""

from __future__ import annotations

import logging
import random
from typing import Sequence, List, Dict, Any, Optional, TYPE_CHECKING, cast

from ..bracket import (
    BRACKET_WINNERS,
    MIN_BRACKET_SIZE_DIRECT_ELIMINATION,
    bracket_levels,
    bracket_size,
    standard_bracket_order,
)
from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    from models.competition.models import Gara
    from models.matchmaking.registry import PairingContext

logger = logging.getLogger(__name__)

# Posizione fittizia per chi non ha il dato richiesto dalla first_round_policy
# (nessuna classifica, nessun rating): finisce in coda, non a meta' griglia.
# Allineata a NO_SEEDING_POSITION di models/classification/seeding_service.py.
NO_SEEDING_POSITION = 10**6


def resolve_draw_seed(gara: object) -> int:
    """Seme del sorteggio di questa gara.

    ``Gara.draw_seed`` viene generato e persistito una volta sola all'avvio del
    primo turno, cosi' che il tabellone non cambi da solo fra due letture, e
    azzerato dall'annullamento del turno 1: riavviare significa risorteggiare.

    Se manca (gare precedenti all'introduzione del campo, o chiamate fuori dal
    flusso normale) si ricade sull'id della gara: arbitrario ma **stabile**,
    che e' l'unica proprieta' che serve qui.
    """
    seed = getattr(gara, "draw_seed", None)
    if seed is not None:
        return int(seed)
    return int(getattr(gara, "id", 0) or 0)


class DirectEliminationStrategy(BaseStrategy):
    """Direct Elimination (single knockout) pairing strategy."""

    # PairingStrategy metadata
    name = "direct_elimination"
    display_name = "Direct Elimination"
    description = "Single knockout campionato format"
    min_players = 4
    max_players = 128
    supports_byes = True
    requires_classification = False

    # Pavimento della dimensione del tabellone. Il doppio KO lo alza a 8
    # (sotto, il losers bracket e' troppo corto per avere senso).
    min_bracket_size = MIN_BRACKET_SIZE_DIRECT_ELIMINATION
    # Il doppio KO ha bisogno di 2k+1 turni; l'eliminazione diretta di k.
    double_elimination = False

    def __init__(self):
        super().__init__()
        self.strategy_name = "direct_elimination"
        # RNG iniettato esplicitamente (test, replay). Quando e' None il
        # sorteggio deriva il proprio RNG da gara.draw_seed, cosi' il
        # determinismo non dipende dalla collaborazione del chiamante.
        self._injected_rng: Optional[random.Random] = None

    def set_context(self, context: "PairingContext") -> None:
        """Inietta un RNG deterministico (vedi registry.PairingContext)."""
        self._injected_rng = context.get_rng()

    def _rng_for(self, gara: object) -> random.Random:
        if self._injected_rng is not None:
            return self._injected_rng
        return random.Random(resolve_draw_seed(gara))

    # ── Validazione ───────────────────────────────────────────────────────

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        """Valida i requisiti specifici dell'eliminazione diretta."""
        errors: List[str] = []
        warnings: List[str] = []

        try:
            player_count = len(self._active_inscriptions(gara))
            if player_count == 0:
                return {"errors": errors, "warnings": warnings}

            if player_count < self.min_players:
                errors.append(
                    f"{self.display_name} richiede almeno {self.min_players} "
                    f"iscritti, ne ha {player_count}"
                )
                return {"errors": errors, "warnings": warnings}

            required_rounds = self.get_total_rounds_needed(player_count)
            rounds_count = getattr(gara, "rounds_count", None)
            if rounds_count and rounds_count < required_rounds:
                errors.append(
                    f"{self.display_name} richiede {required_rounds} turni, "
                    f"la gara ne ha {rounds_count}"
                )
        except Exception as e:  # pragma: no cover - difensivo
            warnings.append(f"{self.display_name} validation warning: {str(e)}")

        return {"errors": errors, "warnings": warnings}

    # ── Ingresso ──────────────────────────────────────────────────────────

    def preview(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Accoppiamenti di un turno senza effetti collaterali."""
        return self._generate_round_pairings(gara, round_number)

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        gara = processed_data["gara"]
        return self._generate_round_pairings(gara, round_number)

    def _generate_round_pairings(
        self, gara: object, round_number: int
    ) -> List[Pairing]:
        """Accoppiamenti del turno richiesto.

        Nessun `try/except` globale: un errore qui deve emergere. La versione
        precedente lo trasformava in "zero accoppiamenti" con un `print`, e il
        turno risultava vuoto senza che niente lo segnalasse.
        """
        gara_typed = cast("Gara", gara)
        if round_number == 1:
            return self._generate_first_round_pairings(gara_typed)
        return self._generate_subsequent_round_pairings(gara_typed, round_number)

    def _apply_side_effects(
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> None:
        """Fissa `rounds_count` sugli iscritti effettivi (solo al turno 1).

        In fase di creazione il numero di turni e' una **stima** ricavata da
        `max_participants`, perche' gli iscritti non ci sono ancora. Il
        sorteggio e' l'unico momento in cui il dato e' certo: 16 posti con 6
        presenti significa tabellone da 8 e 3 turni, non 4.
        """
        if round_number != 1 or not pairings:
            return

        size = 2 * len(pairings)
        needed = self.total_rounds_for_size(size)
        if getattr(gara, "rounds_count", None) != needed:
            setattr(gara, "rounds_count", needed)

    # ── Turno 1: costruzione del tabellone ────────────────────────────────

    def _generate_first_round_pairings(self, gara: "Gara") -> List[Pairing]:
        """Colloca i giocatori sugli slot canonici e genera i nodi del turno 1.

        Il bye **e' un nodo pieno dell'albero**, non un'eccezione: la coppia di
        slot in cui uno dei due e' un buco produce comunque un Match, con la
        sua posizione. Cosi' il turno 2 legge i propri alimentatori senza casi
        speciali.
        """
        inscriptions = self._active_inscriptions(gara)
        player_ids = self._get_seeded_players(gara, inscriptions)
        n = len(player_ids)
        if n < self.min_players:
            return []

        size = self.bracket_size_for(n)
        slots = self._assign_slots(gara, player_ids, size)

        pairings: List[Pairing] = []
        for slot_index in range(size // 2):
            first = slots[2 * slot_index]
            second = slots[2 * slot_index + 1]

            if first is not None and second is not None:
                pairings.append(
                    Pairing(
                        players=(first, second),
                        round_number=1,
                        bracket_type=BRACKET_WINNERS,
                        bracket_round=1,
                        bracket_slot=slot_index,
                    )
                )
            elif first is not None or second is not None:
                pairings.append(
                    Pairing(
                        players=(cast(int, first if first is not None else second),),
                        is_bye=True,
                        round_number=1,
                        bracket_type=BRACKET_WINNERS,
                        bracket_round=1,
                        bracket_slot=slot_index,
                    )
                )
            else:
                # Impossibile per costruzione: S e' la potenza di 2
                # immediatamente superiore a n, quindi i buchi sono meno della
                # meta' degli slot. Se accade, il tabellone e' incoerente e
                # tacere produrrebbe un turno con lacune silenziose.
                raise ValueError(
                    f"Slot {2 * slot_index} e {2 * slot_index + 1} entrambi "
                    f"vuoti con {n} iscritti su tabellone da {size}"
                )

        return pairings

    def _assign_slots(
        self, gara: "Gara", player_ids: List[int], size: int
    ) -> List[Optional[int]]:
        """Slot del primo turno: `slots[i]` = giocatore, oppure None (buco).

        Collocazione canonica: lo slot `i` ospita la testa di serie
        `standard_bracket_order(size)[i]`, e le teste di serie oltre il numero
        di iscritti sono i buchi — che finiscono cosi' davanti ai primi seed,
        dando loro il bye.

        La separazione dei compagni di squadra si innesta qui (Step 6).
        """
        order = standard_bracket_order(size)
        n = len(player_ids)
        return [player_ids[seed - 1] if seed <= n else None for seed in order]

    # ── Turni successivi ──────────────────────────────────────────────────

    def _generate_subsequent_round_pairings(
        self, gara: "Gara", round_number: int
    ) -> List[Pairing]:
        """Accoppia i vincitori secondo il tabellone (Step 5)."""
        # Implementato nello Step 5; per ora comportamento invariato.
        from ...match.models import Match
        from models.status_enum import MatchStatus

        previous_round = round_number - 1
        previous_matches = Match.query.filter(
            Match.gara_id == gara.id,
            Match.round_number == previous_round,
            Match.status.in_(MatchStatus.finished_values()),
        ).all()

        total_previous_matches = Match.query.filter_by(
            gara_id=gara.id, round_number=previous_round
        ).count()

        if len(previous_matches) != total_previous_matches:
            return []

        winners = []
        for match in previous_matches:
            if match.winner_id:
                winners.append(match.winner_id)
            elif match.is_bye and match.player1_id:
                winners.append(match.player1_id)
            elif match.is_bye and match.player2_id:
                winners.append(match.player2_id)
            else:
                raise ValueError(
                    f"Match {match.id} completato senza vincitore "
                    f"(turno {previous_round})"
                )

        pairings = []
        winners = list(winners)
        while len(winners) >= 2:
            player1 = winners.pop(0)
            player2 = winners.pop(0)
            pairings.append(
                Pairing(players=(player1, player2), round_number=round_number)
            )

        if len(winners) == 1:
            pairings.append(
                Pairing(players=(winners[0],), is_bye=True, round_number=round_number)
            )

        return pairings

    # ── Seeding ───────────────────────────────────────────────────────────

    def _active_inscriptions(self, gara: object) -> List:
        """Iscrizioni che partecipano davvero: no ritirati, no lista d'attesa."""
        return [
            i
            for i in list(getattr(gara, "inscriptions", []) or [])
            if not getattr(i, "is_withdrawn", False)
            and not getattr(i, "is_waitlist", False)
        ]

    def _get_seeded_players(self, gara: "Gara", inscriptions: List) -> List[int]:
        """Iscritti in ordine di testa di serie, secondo la `first_round_policy`.

        La policy e' una scelta del director e finora era **dichiarata ma
        ignorata**: si guardava solo se la gara appartenesse a un campionato e
        altrimenti si mescolava.

        Chi non ha il dato richiesto (nessuna classifica, nessun rating) va in
        coda **in ordine casuale**, non a meta' classifica: mancanza di dato non
        e' un piazzamento intermedio. L'ordine casuale di base e' anche il
        criterio di parita' fra chi ha lo stesso dato.
        """
        rng = self._rng_for(gara)
        ordered = list(inscriptions)
        rng.shuffle(ordered)

        policy = (getattr(gara, "first_round_policy", None) or "random").lower()
        if policy == "classification":
            rank = self._classification_rank(gara)
        elif policy == "rating":
            rank = self._rating_rank(gara, ordered)
        else:
            return [i.user_id for i in ordered]

        # sort stabile: chi ha la stessa chiave conserva l'ordine casuale.
        ordered.sort(key=lambda i: rank.get(i.user_id, NO_SEEDING_POSITION))
        return [i.user_id for i in ordered]

    def _classification_rank(self, gara: "Gara") -> Dict[int, float]:
        """Posizione in classifica generale di campionato (1 = migliore)."""
        if not getattr(gara, "campionato_id", None):
            return {}

        from ...classification.models import Classification

        rows = Classification.query.filter_by(campionato_id=gara.campionato_id).all()
        return {c.user_id: c.position for c in rows if c.position is not None}

    def _rating_rank(self, gara: "Gara", inscriptions: List) -> Dict[int, float]:
        """Rating decrescente, tradotto in "posizione" (piu' basso = migliore).

        Quale rating usare e' un'opzione della gara (`seeding_rating`). Oggi
        solo `elo` e' alimentato: `fargo_rating` esiste come colonna ma nessuno
        lo scrive, quindi la voce resta predisposta e non selezionabile in UI.
        """
        field = (getattr(gara, "seeding_rating", None) or "elo").lower()
        attribute = "fargo_rating" if field == "fargo" else "elo_rating"

        rank: Dict[int, float] = {}
        for inscription in inscriptions:
            user = getattr(inscription, "user", None)
            rating = getattr(user, attribute, None) if user else None
            if rating is not None:
                rank[inscription.user_id] = -float(rating)
        return rank

    # ── Aritmetica del tabellone ──────────────────────────────────────────

    def bracket_size_for(self, player_count: int) -> int:
        """Dimensione del tabellone per un dato numero di iscritti."""
        return max(bracket_size(player_count), self.min_bracket_size)

    def total_rounds_for_size(self, size: int) -> int:
        levels = bracket_levels(size)
        return 2 * levels + 1 if self.double_elimination else levels

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Turni necessari per un dato numero di iscritti."""
        if player_count < self.min_players:
            return 0
        return self.total_rounds_for_size(self.bracket_size_for(player_count))

    def get_bracket_size(self, player_count: int) -> int:
        """Dimensione del tabellone (potenza di 2)."""
        if player_count < self.min_players:
            return 0
        return self.bracket_size_for(player_count)

    def get_byes_needed(self, player_count: int) -> int:
        """Numero di bye del primo turno."""
        size = self.get_bracket_size(player_count)
        return max(size - player_count, 0)


class DirectEliminationPairingStrategy(DirectEliminationStrategy):
    """Alias for compatibility with existing strategy registry."""
