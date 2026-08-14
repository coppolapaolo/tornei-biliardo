"""
Module: models/matchmaking/strategies/double_knockout.py
Purpose: Double Knockout (double elimination) pairing strategy implementation
Requirements: SPECIFICHE.md - Double knockout campionato format

Il tabellone e' **persistito** sui Match (`bracket_type` / `bracket_round` /
`bracket_slot`) e questa strategia si limita a leggerlo per coordinate. Prima
lo ricostruiva a ogni turno dallo storico delle sconfitte — sei metodi di
derivazione a runtime — e accoppiava il losers bracket da `list(set(...))`,
cioe' in ordine non deterministico. Ora ogni giocatore ha una destinazione
**calcolata**: chi vince sale di un nodo nel winners bracket, chi perde scende
nel nodo di losers bracket che gli compete.

Lo schedule (quale round di bracket si gioca a quale turno di gara) e i
conteggi stanno in ``models/matchmaking/bracket.py``, che non conosce ne'
Flask ne' il DB.

**Formula FISBB** (Step 12). Con ``gara.double_ko_rounds`` valorizzato la
gara diventa a due fasi: prima `g` gironi giocati in parallelo, ciascuno un
doppio KO da `G = 2^(w+1)` fermato dopo `w` round di winners, poi un
tabellone finale a eliminazione diretta fra i `4g` qualificati (2 diretti e 2
ripescati per girone). Non e' un formato nuovo: e' lo stesso generatore, con
le coordinate qualificate dal girone (``Match.bracket_group``) e la fase
finale delegata all'eliminazione diretta.
"""

from __future__ import annotations

import logging
from typing import Sequence, List, Dict, Optional, Tuple, TYPE_CHECKING, Any, cast

from ..bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_WINNERS,
    MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT,
    MIN_GROUP_DOUBLE_KO_ROUNDS,
    BracketRound,
    bracket_schedule,
    group_phase_is_feasible,
    group_format_total_rounds,
    group_size_for,
    losers_feed_permutation,
)
from .base import Pairing, BaseStrategy
from .direct_elimination import DirectEliminationStrategy

if TYPE_CHECKING:
    from models.competition.models import Gara
    from models.matchmaking.registry import PairingContext

logger = logging.getLogger(__name__)

# Chiave di un nodo del tabellone: (bracket_type, bracket_round, bracket_slot).
NodeKey = Tuple[str, int, int]
# Nodi indicizzati per girone. La chiave None e' il tabellone finale della
# formula FISBB, ed e' anche l'unica presente nel doppio KO classico.
GroupedNodes = Dict[Optional[int], Dict[NodeKey, Any]]


def group_rounds_of(gara: object) -> Optional[int]:
    """`w` se la gara ha una fase a gironi, `None` se e' un doppio KO classico.

    Lo zero e' trattato come assenza: "zero turni di doppio KO nel girone" non
    e' un formato, e un campo lasciato a 0 da una form vale "non configurato".
    """
    value = getattr(gara, "double_ko_rounds", None)
    return int(value) if value else None


class _WinnersBracketSeeding(DirectEliminationStrategy):
    """Il sorteggio del turno 1: identico all'eliminazione diretta.

    Sottoclasse invece di riuso diretto perche' il doppio KO cambia due sole
    costanti: il pavimento del tabellone (8 invece di 4 — sotto, il losers
    bracket sarebbe troppo corto per avere senso) e il conteggio dei turni
    (`2k + 1` invece di `k`). Tutto il resto — slot canonici, bye, seeding per
    `first_round_policy`, separazione delle squadre — e' lo stesso codice.
    """

    name = "double_knockout_seeding"
    display_name = "Double Knockout (sorteggio)"
    min_players = MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT
    min_bracket_size = MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT
    double_elimination = True


class DoubleKnockoutStrategy(BaseStrategy):
    """Double Knockout (double elimination) pairing strategy."""

    # PairingStrategy metadata
    name = "double_knockout"
    display_name = "Double Knockout"
    description = "Double elimination campionato format with winners and losers bracket"
    # Sotto gli 8 iscritti il losers bracket non ha abbastanza round per
    # significare qualcosa: e' il pavimento dichiarato in US-4.
    min_players = MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT
    max_players = 64
    supports_byes = True
    requires_classification = False

    def __init__(self):
        super().__init__()
        self.strategy_name = "double_knockout"
        self._seeding = _WinnersBracketSeeding()

    def set_context(self, context: "PairingContext") -> None:
        """Inietta l'RNG deterministico nel sorteggio del turno 1."""
        self._seeding.set_context(context)

    # ── Validazione ───────────────────────────────────────────────────────

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        errors: List[str] = []
        warnings: List[str] = []

        try:
            # Il filtro sulla lista d'attesa mancava, a differenza della DE:
            # chi e' in attesa non gioca e non deve entrare nel conteggio.
            player_count = len(self._seeding._active_inscriptions(gara))
            if player_count == 0:
                return {"errors": errors, "warnings": warnings}

            if player_count < self.min_players:
                errors.append(
                    f"{self.display_name} richiede almeno {self.min_players} "
                    f"iscritti, ne ha {player_count}"
                )
                return {"errors": errors, "warnings": warnings}

            group_rounds = group_rounds_of(gara)
            if group_rounds is not None:
                errors.extend(self._group_format_errors(player_count, group_rounds))
                if errors:
                    return {"errors": errors, "warnings": warnings}

            required_rounds = self.total_rounds_for(gara, player_count)
            rounds_count = getattr(gara, "rounds_count", None)
            if rounds_count and rounds_count < required_rounds:
                errors.append(
                    f"{self.display_name} richiede {required_rounds} turni "
                    f"(winners, losers, finale e bella), la gara ne ha "
                    f"{rounds_count}"
                )

            if getattr(gara, "third_place_match", False) and group_rounds is None:
                # Non e' un errore bloccante: il flag e' semplicemente senza
                # effetto qui, perche' il terzo posto lo assegna gia' il
                # tabellone (chi perde la finale del losers bracket). In UI
                # l'opzione non viene proprio mostrata sul doppio KO (US-7).
                warnings.append(
                    "La finale 3°/4° non si applica al doppio KO: il terzo "
                    "posto è già deciso dal losers bracket"
                )
        except ValueError as e:
            # Solo gli errori di dominio dell'aritmetica del tabellone (taglie
            # non valide, turni fuori range). Sono configurazioni **invalide**,
            # quindi diventano errori bloccanti e non warning.
            #
            # Tutto il resto propaga di proposito: un `except Exception` qui
            # trasformava un AttributeError — cioe' un bug — in un warning, e
            # la validazione proseguiva come se fosse andata a buon fine,
            # saltando in silenzio ogni controllo successivo.
            errors.append(f"Configurazione a tabellone non valida: {e}")

        return {"errors": errors, "warnings": warnings}

    def _group_format_errors(self, player_count: int, group_rounds: int) -> List[str]:
        """Vincoli propri della fase a gironi.

        Due soli, ma entrambi bloccanti: sotto i due turni il girone non
        troncherebbe nulla (tutti si qualificherebbero), e una ripartizione
        che lascia un girone mezzo vuoto produrrebbe nodi senza giocatori.
        """
        if group_rounds < MIN_GROUP_DOUBLE_KO_ROUNDS:
            return [
                f"Un girone a doppio KO troncato richiede almeno "
                f"{MIN_GROUP_DOUBLE_KO_ROUNDS} turni, la gara ne dichiara "
                f"{group_rounds}"
            ]

        size = group_size_for(group_rounds)
        if not group_phase_is_feasible(player_count, size):
            return [
                f"{player_count} iscritti non si dividono in gironi da {size}: "
                f"uno dei gironi resterebbe mezzo vuoto"
            ]
        return []

    # ── Ingresso ──────────────────────────────────────────────────────────

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        gara = processed_data["gara"]
        return self._generate_round_pairings(gara, round_number)

    def _generate_round_pairings(
        self, gara: object, round_number: int
    ) -> List[Pairing]:
        gara_typed = cast("Gara", gara)
        if round_number == 1:
            return self._generate_first_round_pairings(gara_typed)
        return self._generate_subsequent_round_pairings(gara_typed, round_number)

    def _generate_first_round_pairings(self, gara: "Gara") -> List[Pairing]:
        """Turno 1: winners bracket, identico all'eliminazione diretta."""
        return self._seeding._generate_first_round_pairings(gara)

    def _apply_side_effects(
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> None:
        """Fissa `rounds_count` a `2k + 1` sugli iscritti effettivi."""
        self._seeding._apply_side_effects(pairings, gara, round_number)

    # ── Turni successivi: lettura del tabellone ───────────────────────────

    def _generate_subsequent_round_pairings(
        self, gara: "Gara", round_number: int
    ) -> List[Pairing]:
        """Accoppiamenti del turno, letti dallo schedule e dalle coordinate.

        Ogni round di bracket sa da dove pesca: il winners bracket dai propri
        vincitori, il losers bracket dai perdenti del winners e dai propri
        sopravvissuti, la finale dai due campioni. Nessuna ricostruzione
        dallo storico, nessun `set()` di mezzo.
        """
        from ...match.models import Match
        from models.status_enum import MatchStatus

        played = (
            Match.query.filter(
                Match.gara_id == gara.id, Match.round_number < round_number
            )
            .order_by(Match.id)
            .all()
        )
        if not played:
            return []

        # Nel doppio KO gli alimentatori non stanno tutti nel turno
        # precedente — il round maggiore di losers pesca i perdenti di un
        # winners bracket di due turni prima — quindi il gate guarda tutto
        # cio' che e' stato giocato, non solo l'ultimo turno.
        if any(not MatchStatus.is_finished(m.status) for m in played):
            return []

        nodes = self._nodes_by_coordinate(gara, played)
        size = 2 * sum(1 for key in nodes if key[0] == BRACKET_WINNERS and key[1] == 1)

        pairings: List[Pairing] = []
        for bracket_round in bracket_schedule(size, double_elimination=True).get(
            round_number, []
        ):
            if bracket_round.bracket_type == BRACKET_WINNERS:
                pairings.extend(
                    self._winners_pairings(nodes, bracket_round, round_number)
                )
            elif bracket_round.bracket_type == BRACKET_LOSERS:
                pairings.extend(
                    self._losers_pairings(nodes, bracket_round, round_number)
                )
            elif bracket_round.bracket_type == BRACKET_GRAND_FINAL:
                pairings.extend(self._grand_final_pairings(nodes, size, round_number))
            elif bracket_round.bracket_type == BRACKET_GRAND_FINAL_RESET:
                pairings.extend(self._bracket_reset_pairings(nodes, round_number))

        return pairings

    def _nodes_by_coordinate(self, gara: "Gara", played: Sequence[Any]) -> Dict:
        """Match giocati indicizzati per coordinata di tabellone."""
        nodes: Dict[NodeKey, Any] = {}
        for match in played:
            if match.bracket_slot is None or match.bracket_type is None:
                # Il doppio KO non ha ramo legacy: a differenza
                # dell'eliminazione diretta, il vecchio codice accoppiava il
                # losers bracket in ordine non deterministico, quindi non c'e'
                # un "comportamento precedente" da preservare. Meglio un
                # errore esplicito che un tabellone inventato a meta' gara.
                raise ValueError(
                    f"Gara {getattr(gara, 'id', None)}: il match {match.id} non "
                    f"ha coordinate di tabellone. Una gara a doppio KO "
                    f"iniziata prima della persistenza del tabellone non e' "
                    f"ricostruibile: va annullata e risorteggiata."
                )
            key = (match.bracket_type, match.bracket_round, match.bracket_slot)
            if key in nodes:
                raise ValueError(
                    f"Coordinata {key} duplicata nella gara "
                    f"{getattr(gara, 'id', None)} (match {match.id})"
                )
            nodes[key] = match
        return nodes

    # ── I tre alimentatori ────────────────────────────────────────────────

    def _winners_pairings(
        self, nodes: Dict, bracket_round: BracketRound, round_number: int
    ) -> List[Pairing]:
        """`W_w` ← vincitori di `(W, w-1, 2s)` e `(W, w-1, 2s+1)`."""
        previous = bracket_round.bracket_round - 1
        pairings: List[Pairing] = []
        for slot in range(bracket_round.n_matches):
            first = self._required(nodes, (BRACKET_WINNERS, previous, 2 * slot))
            second = self._required(nodes, (BRACKET_WINNERS, previous, 2 * slot + 1))
            pairings.append(
                Pairing(
                    players=(self._winner(first), self._winner(second)),
                    round_number=round_number,
                    bracket_type=BRACKET_WINNERS,
                    bracket_round=bracket_round.bracket_round,
                    bracket_slot=slot,
                )
            )
        return pairings

    def _losers_pairings(
        self, nodes: Dict, bracket_round: BracketRound, round_number: int
    ) -> List[Pairing]:
        """Round minore e maggiore del losers bracket.

        Il losers bracket alterna due tipi di round: quelli **minori**
        `L_{2j-1}`, che accoppiano fra loro i ripescati appena arrivati, e
        quelli **maggiori** `L_{2j}`, dove i sopravvissuti incontrano i
        perdenti freschi del winners bracket.

        E' qui che i buchi del primo turno si propagano: un bye di `W1` non
        produce alcun perdente, quindi lo slot corrispondente resta vuoto. Un
        nodo con due alimentatori e' un match, con uno solo e' un bye, con
        nessuno **non viene materializzato** — e a valle si comporta a sua
        volta da alimentatore assente.
        """
        lb_round = bracket_round.bracket_round
        pairings: List[Pairing] = []

        for slot in range(bracket_round.n_matches):
            if lb_round % 2 == 1:
                feeders = self._minor_round_feeders(nodes, lb_round, slot)
            else:
                feeders = self._major_round_feeders(
                    nodes, lb_round, slot, bracket_round.n_matches
                )

            present = [player for player in feeders if player is not None]
            if not present:
                continue

            pairings.append(
                Pairing(
                    players=cast(Tuple[int, ...], tuple(present)),
                    is_bye=len(present) == 1,
                    round_number=round_number,
                    bracket_type=BRACKET_LOSERS,
                    bracket_round=lb_round,
                    bracket_slot=slot,
                )
            )
        return pairings

    def _minor_round_feeders(
        self, nodes: Dict, lb_round: int, slot: int
    ) -> List[Optional[int]]:
        """`L_{2j-1}` ← perdenti di `W1` (j=1) o vincitori di `L_{2j-2}`."""
        j = (lb_round + 1) // 2
        if j == 1:
            return [
                self._loser(self._required(nodes, (BRACKET_WINNERS, 1, 2 * slot))),
                self._loser(self._required(nodes, (BRACKET_WINNERS, 1, 2 * slot + 1))),
            ]
        return [
            self._winner_or_none(nodes.get((BRACKET_LOSERS, lb_round - 1, 2 * slot))),
            self._winner_or_none(
                nodes.get((BRACKET_LOSERS, lb_round - 1, 2 * slot + 1))
            ),
        ]

    def _major_round_feeders(
        self, nodes: Dict, lb_round: int, slot: int, n_matches: int
    ) -> List[Optional[int]]:
        """`L_{2j}` ← vincitore di `(L, 2j-1, s)` + perdente di `(W, j+1, σ(s))`.

        La permutazione `σ` allontana il ripescato dai sopravvissuti che
        vengono dal suo stesso ramo, cosi' che una rivincita immediata sia
        l'eccezione e non la regola. I nodi di `W_{j+1}` esistono sempre e
        non sono mai bye — i buchi stanno solo al primo turno — quindi il
        perdente c'e' comunque, e un round maggiore non resta mai vuoto.
        """
        j = lb_round // 2
        sigma = losers_feed_permutation(j + 1, n_matches)
        dropdown = self._required(nodes, (BRACKET_WINNERS, j + 1, sigma[slot]))
        return [
            self._winner_or_none(nodes.get((BRACKET_LOSERS, lb_round - 1, slot))),
            self._loser(dropdown),
        ]

    def _grand_final_pairings(
        self, nodes: Dict, size: int, round_number: int
    ) -> List[Pairing]:
        """Finale fra i due campioni.

        **Convenzione di seat**: `player1` e' il campione del winners bracket,
        `player2` quello del losers. Non e' cosmesi — e' cosi' che lo Step 8
        riconosce il bracket reset (`winner_id == player2_id` significa che a
        vincere e' stato chi aveva gia' una sconfitta, quindi si gioca la
        bella). Va quindi mantenuta, e c'e' un test che la sorveglia.
        """
        levels = size.bit_length() - 1
        winners_champion = self._required(nodes, (BRACKET_WINNERS, levels, 0))
        losers_champion = self._required(nodes, (BRACKET_LOSERS, 2 * levels - 2, 0))
        return [
            Pairing(
                players=(
                    self._winner(winners_champion),
                    self._winner(losers_champion),
                ),
                round_number=round_number,
                bracket_type=BRACKET_GRAND_FINAL,
                bracket_round=1,
                bracket_slot=0,
            )
        ]

    def _bracket_reset_pairings(self, nodes: Dict, round_number: int) -> List[Pairing]:
        """La bella, se la finale l'ha vinta chi arrivava dal losers (US-15).

        Il doppio KO promette due sconfitte prima dell'eliminazione. Chi arriva
        alla finale imbattuto non puo' quindi essere eliminato da una sola
        partita: se perde, si rigioca da pari — entrambi con una sconfitta.
        Se invece vince, la gara e' finita e questo turno **resta vuoto**, che
        e' uno stato legittimo e non un errore.

        Il rilevamento e' banale grazie alla convenzione di seat della finale
        (`player1` = campione winners): `winner_id == player2_id` significa
        "ha vinto quello che era gia' stato eliminato una volta".
        """
        final = nodes.get((BRACKET_GRAND_FINAL, 1, 0))
        if final is None:
            # La finale non e' stata giocata: puo' capitare se il turno viene
            # avviato fuori sequenza. Non c'e' niente da decidere.
            return []

        if final.winner_id != final.player2_id:
            logger.debug(
                "Gara %s: la finale l'ha vinta il campione del winners "
                "bracket, nessuna bella",
                final.gara_id,
            )
            return []

        return [
            Pairing(
                players=(final.player1_id, final.player2_id),
                round_number=round_number,
                bracket_type=BRACKET_GRAND_FINAL_RESET,
                bracket_round=1,
                bracket_slot=0,
            )
        ]

    # ── Lettura dei nodi ──────────────────────────────────────────────────

    @staticmethod
    def _required(nodes: Dict, key: NodeKey) -> Any:
        """Alimentatore che deve esistere per costruzione."""
        match = nodes.get(key)
        if match is None:
            raise ValueError(
                f"Alimentatore {key} assente: il tabellone del doppio KO e' "
                f"incoerente (i nodi del winners bracket esistono sempre)"
            )
        return match

    @staticmethod
    def _winner(match: Any) -> int:
        return DirectEliminationStrategy._winner_of(match)

    @staticmethod
    def _winner_or_none(match: Optional[Any]) -> Optional[int]:
        """Vincitore di un nodo che **puo' non essere stato materializzato**."""
        if match is None:
            return None
        return DirectEliminationStrategy._winner_of(match)

    @staticmethod
    def _loser(match: Any) -> Optional[int]:
        """Chi scende nel losers bracket, o None se il nodo era un bye.

        E' l'unica sorgente di buchi del losers bracket: chi passa il turno
        senza giocare non produce alcun perdente da ripescare.
        """
        return DirectEliminationStrategy._loser_of(match)

    # ── Aritmetica ────────────────────────────────────────────────────────

    def total_rounds_for(self, gara: object, player_count: int) -> int:
        """Turni necessari alla gara, nel formato che la gara dichiara.

        Due formati distinti, e la differenza non e' un dettaglio: il doppio KO
        classico e' un tabellone solo che arriva a un vincitore, la formula
        FISBB sono `g` gironi in parallelo piu' un tabellone finale, e i turni
        si contano di conseguenza.
        """
        group_rounds = group_rounds_of(gara)
        if group_rounds is None:
            return self.get_total_rounds_needed(player_count)
        return group_format_total_rounds(player_count, group_rounds)

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Turni necessari al doppio KO classico: `2k + 1`, con `k = log2(S)`.

        Il `+1` e' la bella, che puo' restare vuota: un turno con zero pairing
        significa "torneo concluso", non errore. Il vecchio `2k + 2` era
        un'approssimazione dichiarata tale nel codice.
        """
        return self._seeding.get_total_rounds_needed(player_count)

    def get_bracket_size(self, player_count: int) -> int:
        return self._seeding.get_bracket_size(player_count)

    def get_byes_needed(self, player_count: int) -> int:
        return self._seeding.get_byes_needed(player_count)
