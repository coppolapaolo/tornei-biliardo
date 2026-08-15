"""
Module: models/matchmaking/bracket_view.py
Purpose: Struttura di presentazione del tabellone (US-13, Step 10)
Requirements: piano "Eliminazione diretta e doppio KO", Step 10
Decisione: docs/adr/ADR-038-bracket-persistence.md

Il tabellone e' persistito su `Match` come tripla `(bracket_type,
bracket_round, bracket_slot)` piu' il girone `bracket_group` (Step 2 e
Step 12). Quella forma e' ottima per generare e per interrogare, pessima da
disegnare: il template dovrebbe raggruppare, ordinare e decidere quali
colonne appartengono al ramo dei vincenti e quali a quello dei ripescati.

Questo modulo fa quella traduzione una volta sola, **senza toccare il DB e
senza i18n**: prende i match gia' caricati e restituisce lavagne, sezioni e
colonne. Le etichette ("Finale", "Semifinali", "Recupero 2") sono lasciate al
template, che e' il solo posto dove `_()` e' al suo posto — qui restano i
dati grezzi da cui l'etichetta si deriva (tipo, numero di round, quanti nodi).

Convenzioni di ordinamento
--------------------------
- le **lavagne** vanno in ordine di girone, con il tabellone finale
  (`bracket_group IS NULL`) per ultimo: e' l'ordine in cui si gioca;
- dentro una lavagna il ramo dei **vincenti** viene prima di quello dei
  **ripescati**, come nel modo in cui il doppio KO si legge;
- le **colonne** seguono il turno, e i **nodi** lo slot: e' l'ordine che
  rende il vicino di sopra e quello di sotto gli alimentatori del nodo
  successivo, quindi l'unico che disegna un albero e non un elenco.

I rami vuoti non compaiono (US-13): un nodo che non e' stato materializzato
— tipico del losers bracket quando un X a tavolino del primo turno non
produce alcun perdente — semplicemente non e' nella lista.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_THIRD_PLACE,
    BRACKET_WINNERS,
)

SECTION_WINNERS = "winners"
SECTION_LOSERS = "losers"

# Posizione della colonna dentro la sezione dei vincenti. La finalina 3o/4o
# si gioca nello stesso turno della finale (Step 8) ma le sta accanto, non
# dentro: e' un nodo suo, con un esito suo.
_WINNERS_COLUMN_ORDER: Dict[str, int] = {
    BRACKET_WINNERS: 0,
    BRACKET_THIRD_PLACE: 1,
    BRACKET_GRAND_FINAL: 2,
    BRACKET_GRAND_FINAL_RESET: 3,
}


@dataclass(frozen=True)
class BracketColumn:
    """Una colonna del tabellone: i nodi di un round, in ordine di slot."""

    bracket_type: str
    bracket_round: int
    matches: List[Any]

    @property
    def is_losers(self) -> bool:
        return self.bracket_type == BRACKET_LOSERS

    @property
    def size(self) -> int:
        """Quanti nodi ha davvero la colonna (i rami vuoti non ci sono)."""
        return len(self.matches)


@dataclass(frozen=True)
class BracketSection:
    """Un ramo del tabellone: vincenti oppure ripescati."""

    key: str
    columns: List[BracketColumn]


@dataclass(frozen=True)
class BracketBoard:
    """Una lavagna: un girone della formula FISBB, o il tabellone finale."""

    group: Optional[int]
    sections: List[BracketSection]

    @property
    def is_group(self) -> bool:
        """Vero se e' un girone, falso se e' il tabellone (finale o unico)."""
        return self.group is not None

    @property
    def has_losers(self) -> bool:
        return any(section.key == SECTION_LOSERS for section in self.sections)


def _sort_key(match: Any) -> Tuple[int, int]:
    """Chiave di ordinamento dei nodi dentro una colonna.

    `bracket_slot` puo' essere NULL su un match arrivato qui per sbaglio
    (gara mista, ramo legacy): non e' un motivo per far esplodere la pagina,
    quindi finisce in coda invece che in mezzo agli altri.
    """
    slot = match.bracket_slot
    return (1, match.id or 0) if slot is None else (0, slot)


def _column_order(column: BracketColumn) -> Tuple[int, int]:
    return (
        _WINNERS_COLUMN_ORDER.get(column.bracket_type, 0),
        column.bracket_round or 0,
    )


def has_bracket_coordinates(matches: Iterable[Any]) -> bool:
    """C'e' almeno un match con le coordinate del tabellone?

    E' la domanda che decide se la vista tabellone ha qualcosa da mostrare:
    una gara a tabellone antecedente allo Step 2 (o non ancora sorteggiata)
    ha `bracket_type` NULL ovunque e va mandata sullo stato vuoto, non su una
    pagina di colonne senza nodi.
    """
    return any(getattr(match, "bracket_type", None) for match in matches)


def build_bracket_boards(matches: Iterable[Any]) -> List[BracketBoard]:
    """Raggruppa i match in lavagne / sezioni / colonne pronte da disegnare.

    I match senza coordinate vengono ignorati: in una gara a tabellone non
    dovrebbero esistere, ma se esistono (ramo legacy dello Step 5) l'unica
    cosa onesta e' non disegnarli, perche' la loro posizione nell'albero non
    e' nota.
    """
    grouped: Dict[Optional[int], Dict[Tuple[str, int], List[Any]]] = {}

    for match in matches:
        bracket_type = getattr(match, "bracket_type", None)
        if not bracket_type:
            continue
        board_key = getattr(match, "bracket_group", None)
        column_key = (bracket_type, match.bracket_round or 1)
        grouped.setdefault(board_key, {}).setdefault(column_key, []).append(match)

    boards: List[BracketBoard] = []
    # `None` (tabellone finale) per ultimo: si gioca dopo i gironi.
    for board_key in sorted(grouped, key=lambda key: (key is None, key or 0)):
        winners: List[BracketColumn] = []
        losers: List[BracketColumn] = []

        for (bracket_type, bracket_round), nodes in grouped[board_key].items():
            column = BracketColumn(
                bracket_type=bracket_type,
                bracket_round=bracket_round,
                matches=sorted(nodes, key=_sort_key),
            )
            (losers if column.is_losers else winners).append(column)

        sections: List[BracketSection] = []
        if winners:
            sections.append(
                BracketSection(SECTION_WINNERS, sorted(winners, key=_column_order))
            )
        if losers:
            sections.append(
                BracketSection(SECTION_LOSERS, sorted(losers, key=_column_order))
            )

        boards.append(BracketBoard(group=board_key, sections=sections))

    return boards
