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
from typing import Sequence, List, Dict, Any, Optional, Tuple, TYPE_CHECKING, cast

from ..bracket import (
    BRACKET_THIRD_PLACE,
    BRACKET_WINNERS,
    MIN_BRACKET_SIZE_DIRECT_ELIMINATION,
    bracket_levels,
    bracket_size,
    standard_bracket_order,
)
from ..team_separation import assign_slots
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
    primo turno, e azzerato dall'annullamento: riavviare significa
    risorteggiare, mentre due invocazioni della stessa generazione danno lo
    stesso tabellone. Serve anche a poter ricostruire a posteriori perche' il
    sorteggio e' uscito cosi', se qualcuno lo contesta.

    Se manca (gare precedenti all'introduzione del campo, o chiamate fuori dal
    flusso normale) si ricade sull'id della gara: arbitrario ma **stabile**,
    che e' l'unica proprieta' che serve qui.
    """
    seed = getattr(gara, "draw_seed", None)
    if seed is not None:
        return int(seed)
    return int(getattr(gara, "id", 0) or 0)


def rounds_count_check(
    gara: object, required_rounds: int, message: str
) -> Tuple[List[str], List[str]]:
    """Il numero di turni e' un problema solo **dopo** il sorteggio.

    Prima, e' una stima: il sorteggio la sostituisce col numero calcolato sugli
    iscritti che si sono presentati (ADR-038, `_apply_side_effects`). Trattarla
    come errore bloccante impediva l'unica azione che l'avrebbe corretta — il
    director si vedeva rifiutare l'avvio con "richiede N turni, la gara ne ha
    M" senza avere piu' un campo dove cambiare M, visto che il form non lo
    chiede piu'. Qui diventa una nota: il valore verra' riscritto fra un
    istante.

    A tabellone gia' estratto invece resta un errore vero: i nodi esistono, e
    un `rounds_count` troppo basso significa che gli ultimi turni non si
    potrebbero materializzare.
    """
    rounds_count = getattr(gara, "rounds_count", None)
    if not rounds_count or rounds_count >= required_rounds:
        return [], []

    if not getattr(gara, "current_round", 0):
        return [], [f"{message}: il sorteggio li fissera' a {required_rounds}"]

    return [f"{message}, la gara ne ha {rounds_count}"], []


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

    def _derived_rng(self, gara: object, key: str) -> random.Random:
        """Sorgente casuale dedicata a **uno** dei sorteggi della gara.

        Serve alla formula FISBB, dove nella stessa operazione si estraggono
        piu' tabelloni distinti (un girone per volta, poi il tabellone finale).
        Con una sorgente sola i gironi verrebbero sorteggiati dalla stessa
        sequenza di numeri: non identici — i giocatori sono altri — ma con le
        stesse scelte interne all'algoritmo di separazione (stessi restart,
        stessi scambi), che e' una correlazione che non ha ragione di esserci.

        La derivazione resta deterministica: dal seme persistito della gara
        piu' la chiave, oppure — quando un test o un replay ha iniettato un
        RNG — pescando da quello, che a parita' di seme e di ordine di
        chiamata da' sempre la stessa cosa.
        """
        if self._injected_rng is not None:
            return random.Random(self._injected_rng.random())
        return random.Random(f"{resolve_draw_seed(gara)}:{key}")

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
            problems, notes = rounds_count_check(
                gara,
                required_rounds,
                f"{self.display_name} richiede {required_rounds} turni",
            )
            errors.extend(problems)
            warnings.extend(notes)
        except ValueError as e:
            # Vedi la nota gemella in double_knockout: solo gli errori di
            # dominio dell'aritmetica diventano errori di configurazione; i bug
            # propagano invece di essere degradati a warning.
            errors.append(f"Configurazione a tabellone non valida: {e}")

        return {"errors": errors, "warnings": warnings}

    # ── Ingresso ──────────────────────────────────────────────────────────

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
        slots = self._assign_slots(gara, player_ids, size, inscriptions)
        return self._pairings_from_slots(slots, size)

    def _pairings_from_slots(
        self,
        slots: Sequence[Optional[int]],
        size: int,
        *,
        round_number: int = 1,
        bracket_group: Optional[int] = None,
    ) -> List[Pairing]:
        """Nodi del primo turno di **un** tabellone, dati i suoi slot.

        Isolata dal resto perche' i tabelloni da costruire non sono uno solo:
        la formula FISBB ne estrae uno per girone e poi quello finale, tutti
        con la stessa regola (il nodo `j` prende gli slot `2j` e `2j+1`) ma
        con turno di gara e `bracket_group` diversi.
        """
        pairings: List[Pairing] = []
        for slot_index in range(size // 2):
            first = slots[2 * slot_index]
            second = slots[2 * slot_index + 1]

            if first is not None and second is not None:
                pairings.append(
                    Pairing(
                        players=(first, second),
                        round_number=round_number,
                        bracket_type=BRACKET_WINNERS,
                        bracket_round=1,
                        bracket_slot=slot_index,
                        bracket_group=bracket_group,
                    )
                )
            elif first is not None or second is not None:
                pairings.append(
                    Pairing(
                        players=(cast(int, first if first is not None else second),),
                        is_bye=True,
                        round_number=round_number,
                        bracket_type=BRACKET_WINNERS,
                        bracket_round=1,
                        bracket_slot=slot_index,
                        bracket_group=bracket_group,
                    )
                )
            else:
                # Impossibile per costruzione: S e' la potenza di 2
                # immediatamente superiore a n, quindi i buchi sono meno della
                # meta' degli slot. Se accade, il tabellone e' incoerente e
                # tacere produrrebbe un turno con lacune silenziose.
                raise ValueError(
                    f"Slot {2 * slot_index} e {2 * slot_index + 1} entrambi "
                    f"vuoti su un tabellone da {size}"
                )

        return pairings

    def _assign_slots(
        self,
        gara: "Gara",
        player_ids: List[int],
        size: int,
        inscriptions: Optional[List] = None,
        rng: Optional[random.Random] = None,
        groups_of: Optional[Dict[int, Optional[int]]] = None,
    ) -> List[Optional[int]]:
        """Slot del primo turno: `slots[i]` = giocatore, oppure None (buco).

        Collocazione canonica: lo slot `i` ospita la testa di serie
        `standard_bracket_order(size)[i]`, e le teste di serie oltre il numero
        di iscritti sono i buchi — che finiscono cosi' davanti ai primi seed,
        dando loro il bye.

        Con `gara.separate_teammates` attivo la collocazione passa da
        `team_separation.assign_slots`, che sceglie **quale membro di ciascuna
        banda di seeding** occupa quale slot della banda: il seeding resta
        quello canonico, cambia solo il sorteggio interno alla banda — cioe'
        esattamente "le teste di serie 5-8 si sorteggiano fra i quattro
        quarti" (US-6, US-10).

        `rng` permette al chiamante di sorteggiare **piu' tabelloni** con
        sorgenti casuali distinte pur restando deterministico: serve alla
        formula FISBB, dove i gironi sono tabelloni separati estratti nella
        stessa operazione e condividere la stessa sequenza li renderebbe
        copie l'uno dell'altro nelle scelte interne all'algoritmo. Assente,
        vale l'RNG della gara.

        `groups_of` sostituisce le squadre con **un altro raggruppamento** da
        separare, e attiva la separazione anche a `separate_teammates` spento.
        Lo usa il tabellone finale della formula FISBB col girone di
        provenienza: la separazione e' la stessa operazione, cambia solo che
        cosa si tiene lontano da cosa.
        """
        n = len(player_ids)
        canonical = [
            player_ids[seed - 1] if seed <= n else None
            for seed in standard_bracket_order(size)
        ]

        if groups_of is not None:
            team_of: Dict[int, Optional[int]] = groups_of
        elif not getattr(gara, "separate_teammates", False):
            return canonical
        else:
            team_of = self._teams_by_player(gara, inscriptions)

        if not any(team is not None for team in team_of.values()):
            # Opzione attiva ma nessuno ha dichiarato una squadra: non c'e'
            # nulla da separare e il canonico e' gia' la risposta giusta.
            return canonical

        holes = size - n
        if 2 * holes >= size:
            # Puo' accadere solo quando il pavimento di formato alza `S` sopra
            # la potenza di 2 naturale (doppio KO con pochissimi iscritti):
            # li' meta' del tabellone e' vuota e la separazione non ha piu'
            # una base sensata su cui lavorare.
            logger.warning(
                "Gara %s: separazione squadre saltata, %s buchi su %s slot "
                "(il pavimento di formato ha allargato il tabellone)",
                getattr(gara, "id", None),
                holes,
                size,
            )
            return canonical

        return assign_slots(
            player_ids, team_of, size, rng or self._rng_for(gara), holes
        )

    def _teams_by_player(
        self, gara: "Gara", inscriptions: Optional[List] = None
    ) -> Dict[int, Optional[int]]:
        """Squadra di ciascun iscritto, letta **dall'iscrizione**.

        `Inscription.squadra_id` e' l'unica fonte autorevole: il testo libero
        sul profilo (`user.squadra`) e' servito solo a precompilare quel campo
        al momento dell'iscrizione e non viene piu' riletto. Cambiarlo dopo —
        anche a gara in corso — non deve spostare nessuno nel tabellone.

        `None` significa "gioca senza squadra qui", ed e' uno stato legittimo:
        chi non ha squadra non ha compagni da cui essere separato.
        """
        rows = self._active_inscriptions(gara) if inscriptions is None else inscriptions
        return {i.user_id: getattr(i, "squadra_id", None) for i in rows}

    # ── Turni successivi ──────────────────────────────────────────────────

    def _generate_subsequent_round_pairings(
        self, gara: "Gara", round_number: int
    ) -> List[Pairing]:
        """Accoppia i vincitori **leggendo il tabellone persistito**.

        E' il punto da cui e' partita tutta l'analisi. La versione precedente
        riaccoppiava i vincitori nell'ordine di ritorno della query
        (`pop(0), pop(0)`): non un ordine casuale, ma uno **sistematicamente
        sbagliato**, perche' i match del turno 1 vengono inseriti prima i bye e
        poi le coppie. Al turno 2 tutti i giocatori usciti dai bye — cioe' le
        teste di serie, quelle che il seeding vuole tenere separate il piu' a
        lungo possibile — finivano per incontrarsi fra loro.

        Il tabellone dice invece che il vincitore dello slot `2j` incontra
        quello dello slot `2j+1`: entrambi gli alimentatori esistono sempre,
        perche' il turno 1 e' completo (`S/2` nodi senza lacune, Step 4) e ogni
        nodo — bye compreso — produce un vincitore.
        """
        from ...match.models import Match
        from models.status_enum import MatchStatus

        previous_round = round_number - 1
        previous_matches = (
            Match.query.filter_by(gara_id=gara.id, round_number=previous_round)
            .order_by(Match.id)
            .all()
        )
        if not previous_matches:
            return []

        # Il turno successivo non parte finche' il precedente non e' chiuso.
        # `validated` e' finale quanto `completed` (conferma bilaterale): usare
        # solo `completed` bloccava il torneo (vedi
        # test_direct_elimination_validated_status.py).
        if any(not MatchStatus.is_finished(m.status) for m in previous_matches):
            return []

        coordinates = self._bracket_coordinates(previous_matches)
        if coordinates is None:
            logger.warning(
                "Gara %s, turno %s: il turno precedente non ha coordinate di "
                "tabellone, accoppiamento legacy (ordine di query). E' il "
                "comportamento che questa gara ha gia' avuto nei turni "
                "precedenti: cambiarlo a meta' gara sarebbe peggio.",
                getattr(gara, "id", None),
                round_number,
            )
            return self._legacy_subsequent_pairings(previous_matches, round_number)

        previous_bracket_round, by_slot = coordinates
        size = self._persisted_bracket_size(gara)
        expected_nodes = size >> previous_bracket_round

        if sorted(by_slot) != list(range(expected_nodes)):
            raise ValueError(
                f"Tabellone incoerente per la gara {getattr(gara, 'id', None)}: "
                f"il round W{previous_bracket_round} di un tabellone da {size} "
                f"dovrebbe avere gli slot 0..{expected_nodes - 1}, ha "
                f"{sorted(by_slot)}"
            )

        pairings: List[Pairing] = []
        for slot_index in range(expected_nodes // 2):
            pairings.append(
                Pairing(
                    players=(
                        self._winner_of(by_slot[2 * slot_index]),
                        self._winner_of(by_slot[2 * slot_index + 1]),
                    ),
                    round_number=round_number,
                    bracket_type=BRACKET_WINNERS,
                    bracket_round=previous_bracket_round + 1,
                    bracket_slot=slot_index,
                )
            )

        pairings.extend(
            self._third_place_pairings(
                gara, by_slot, expected_nodes, previous_bracket_round + 1, round_number
            )
        )
        return pairings

    def _third_place_pairings(
        self,
        gara: "Gara",
        by_slot: Dict[int, Any],
        expected_nodes: int,
        bracket_round: int,
        round_number: int,
    ) -> List[Pairing]:
        """Finalina 3°/4° posto, se il director l'ha chiesta (US-7).

        Occupa **lo stesso turno della finale**, non uno in piu': i due
        semifinalisti sconfitti sono gia' liberi, e allungare il tabellone di
        un turno per una sola partita costringerebbe tutti gli altri ad
        aspettare. Da qui `bracket_round` uguale a quello della finale, con
        `bracket_type='3P'` a distinguere i due nodi.

        Si genera solo quando il turno che si sta creando **e'** la finale,
        cioe' quando il turno precedente aveva esattamente due nodi: sono le
        semifinali, e i loro perdenti sono i due contendenti.
        """
        if expected_nodes != 2 or not getattr(gara, "third_place_match", False):
            return []

        contenders = [self._loser_of(by_slot[0]), self._loser_of(by_slot[1])]
        if any(player is None for player in contenders):
            # Una semifinale vinta senza giocare non produce uno sconfitto.
            # Non puo' accadere col dimensionamento sugli iscritti (i bye
            # stanno solo al turno 1, e con S=4 non ce ne sono), ma se accade
            # una "finalina" con un solo partecipante non avrebbe senso.
            logger.warning(
                "Gara %s: finalina 3°/4° saltata, una semifinale non ha "
                "prodotto uno sconfitto",
                getattr(gara, "id", None),
            )
            return []

        return [
            Pairing(
                players=(cast(int, contenders[0]), cast(int, contenders[1])),
                round_number=round_number,
                bracket_type=BRACKET_THIRD_PLACE,
                bracket_round=bracket_round,
                bracket_slot=0,
            )
        ]

    def _bracket_coordinates(
        self, matches: Sequence[Any]
    ) -> Optional[Tuple[int, Dict[int, Any]]]:
        """`(bracket_round, {slot: match})` del turno, o None se non ha tabellone.

        None significa "gara iniziata prima della persistenza del tabellone":
        basta un solo match senza `bracket_slot` perche' l'intero turno sia
        inaffidabile come alimentatore, quindi si ricade sul ramo legacy.
        """
        if any(getattr(m, "bracket_slot", None) is None for m in matches):
            return None

        # `bracket_group is None` = tabellone finale. Nell'eliminazione
        # diretta pura e' sempre vero (i gironi esistono solo nella formula
        # FISBB), ma il filtro serve quando e' la fase finale di una gara a
        # gironi a passare di qui: li' i nodi dei gironi non sono
        # alimentatori di questo tabellone.
        feeders = [
            m
            for m in matches
            if m.bracket_type == BRACKET_WINNERS
            and getattr(m, "bracket_group", None) is None
        ]
        if not feeders:
            raise ValueError(
                "Turno con coordinate di tabellone ma senza alcun nodo del "
                "winners bracket: nell'eliminazione diretta non puo' accadere"
            )

        bracket_rounds = {m.bracket_round for m in feeders}
        if len(bracket_rounds) != 1:
            raise ValueError(
                f"Un turno di gara contiene piu' round di winners bracket: "
                f"{sorted(bracket_rounds)}"
            )

        bracket_round = bracket_rounds.pop()
        by_slot: Dict[int, Any] = {}
        for match in feeders:
            if match.bracket_slot in by_slot:
                raise ValueError(
                    f"Slot {match.bracket_slot} duplicato nel round "
                    f"W{bracket_round} (match {match.id})"
                )
            by_slot[match.bracket_slot] = match
        return bracket_round, by_slot

    def _persisted_bracket_size(self, gara: "Gara") -> int:
        """Dimensione del tabellone **come e' stato estratto**.

        Si conta il turno 1 persistito, non gli iscritti: dopo il sorteggio il
        tabellone non si tocca piu' (un ritiro fa avanzare l'avversario a
        tavolino), quindi gli iscritti attivi possono benissimo essere di meno.
        """
        from ...match.models import Match

        nodes = Match.query.filter(
            Match.gara_id == gara.id,
            Match.bracket_type == BRACKET_WINNERS,
            Match.bracket_round == 1,
            # Vedi _bracket_coordinates: i gironi non fanno parte del
            # tabellone finale e non ne dichiarano la dimensione.
            Match.bracket_group.is_(None),
        ).count()
        if nodes == 0:
            raise ValueError(
                f"Gara {getattr(gara, 'id', None)}: turni successivi con "
                f"coordinate ma nessun nodo di primo turno da cui derivare la "
                f"dimensione del tabellone"
            )
        return 2 * nodes

    @staticmethod
    def _winner_of(match: Any) -> int:
        """Chi passa il turno. Un bye e' un nodo pieno, quindi ha un vincitore."""
        if match.winner_id:
            return match.winner_id
        if match.is_bye:
            player = match.player1_id or match.player2_id
            if player:
                return player
        raise ValueError(
            f"Match {match.id} concluso senza vincitore "
            f"(turno {match.round_number})"
        )

    @staticmethod
    def _loser_of(match: Any) -> Optional[int]:
        """Chi esce dal nodo, o None se il nodo era un bye.

        Serve alla finalina 3°/4° (qui) e al ripescaggio nel losers bracket
        del doppio KO: un bye non produce sconfitti, ed e' da li' che nascono
        i buchi del losers bracket.
        """
        if match.is_bye:
            return None
        winner_id = match.winner_id
        if winner_id is None:
            raise ValueError(
                f"Match {match.id} concluso senza vincitore "
                f"(turno {match.round_number})"
            )
        return match.player1_id if winner_id == match.player2_id else match.player2_id

    def _legacy_subsequent_pairings(
        self, previous_matches: Sequence[Any], round_number: int
    ) -> List[Pairing]:
        """Comportamento pre-tabellone, per le gare iniziate senza coordinate.

        I pairing prodotti qui restano **senza coordinate**: scriverle adesso
        significherebbe dichiarare un tabellone che i turni gia' giocati non
        hanno mai rispettato.
        """
        winners = [self._winner_of(m) for m in previous_matches]

        pairings: List[Pairing] = []
        while len(winners) >= 2:
            player1 = winners.pop(0)
            player2 = winners.pop(0)
            pairings.append(
                Pairing(players=(player1, player2), round_number=round_number)
            )

        if winners:
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

        Il rating e' l'Elo. La colonna `seeding_rating` della gara resta come
        appiglio per un eventuale secondo sistema, ma oggi ha un valore solo:
        un rating che nessuno alimenta non e' un'opzione, e' una promessa.
        """
        rank: Dict[int, float] = {}
        for inscription in inscriptions:
            user = getattr(inscription, "user", None)
            rating = getattr(user, "elo_rating", None) if user else None
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
