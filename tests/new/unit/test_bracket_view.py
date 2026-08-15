"""Unit test della struttura di presentazione del tabellone (Step 10, US-13).

Copre `models/matchmaking/bracket_view.py`: raggruppamento in lavagne
(gironi + tabellone finale), separazione dei rami vincenti/ripescati,
ordinamento delle colonne e dei nodi, e il fatto che i rami vuoti non
compaiano.

Test puri: i match sono oggetti finti con le sole coordinate: il modulo non
tocca il DB e non deve pretendere un `Match` vero.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from models.matchmaking.bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_THIRD_PLACE,
    BRACKET_WINNERS,
)
from models.matchmaking.bracket_view import (
    SECTION_LOSERS,
    SECTION_WINNERS,
    build_bracket_boards,
    has_bracket_coordinates,
)


@dataclass
class FakeMatch:
    """Il minimo che il costruttore di lavagne legge da un match."""

    id: int
    bracket_type: Optional[str] = None
    bracket_round: Optional[int] = None
    bracket_slot: Optional[int] = None
    bracket_group: Optional[int] = None


def node(id_, btype, bround, slot, group=None):
    return FakeMatch(
        id=id_,
        bracket_type=btype,
        bracket_round=bround,
        bracket_slot=slot,
        bracket_group=group,
    )


def direct_elimination_8():
    """Tabellone da 8: 4 + 2 + 1 nodi, tutti nel ramo dei vincenti."""
    matches = []
    next_id = 1
    for bracket_round, count in ((1, 4), (2, 2), (3, 1)):
        for slot in range(count):
            matches.append(node(next_id, BRACKET_WINNERS, bracket_round, slot))
            next_id += 1
    return matches


class TestHasBracketCoordinates:
    def test_gara_senza_coordinate(self):
        assert has_bracket_coordinates([FakeMatch(id=1), FakeMatch(id=2)]) is False

    def test_basta_un_match_con_coordinate(self):
        matches = [FakeMatch(id=1), node(2, BRACKET_WINNERS, 1, 0)]
        assert has_bracket_coordinates(matches) is True

    def test_elenco_vuoto(self):
        assert has_bracket_coordinates([]) is False


class TestEliminazioneDiretta:
    def test_una_lavagna_un_ramo_tre_colonne(self):
        boards = build_bracket_boards(direct_elimination_8())

        assert len(boards) == 1
        board = boards[0]
        assert board.group is None
        assert board.is_group is False
        assert board.has_losers is False
        assert [section.key for section in board.sections] == [SECTION_WINNERS]
        assert [column.size for column in board.sections[0].columns] == [4, 2, 1]

    def test_i_nodi_seguono_lo_slot_non_l_ordine_di_arrivo(self):
        """L'ordine dei nodi e' quel che disegna l'albero, non un dettaglio.

        I vicini di una colonna sono gli alimentatori del nodo successivo:
        se l'ordine e' quello di ritorno della query, il tabellone disegnato
        e' un elenco che *sembra* un albero.
        """
        shuffled = list(reversed(direct_elimination_8()))
        boards = build_bracket_boards(shuffled)

        first = boards[0].sections[0].columns[0]
        assert [match.bracket_slot for match in first.matches] == [0, 1, 2, 3]

    def test_finalina_e_una_colonna_accanto_alla_finale(self):
        matches = direct_elimination_8()
        matches.append(node(99, BRACKET_THIRD_PLACE, 3, 0))

        columns = build_bracket_boards(matches)[0].sections[0].columns
        assert [column.bracket_type for column in columns] == [
            BRACKET_WINNERS,
            BRACKET_WINNERS,
            BRACKET_WINNERS,
            BRACKET_THIRD_PLACE,
        ]

    def test_match_senza_coordinate_ignorati(self):
        """Ramo legacy (Step 5): posizione ignota, quindi non si disegna."""
        matches = direct_elimination_8() + [FakeMatch(id=500)]
        totale = sum(
            column.size
            for board in build_bracket_boards(matches)
            for section in board.sections
            for column in section.columns
        )
        assert totale == 7


class TestDoppioKo:
    def test_vincenti_prima_dei_ripescati(self):
        matches = direct_elimination_8()
        matches += [
            node(20, BRACKET_LOSERS, 1, 0),
            node(21, BRACKET_LOSERS, 1, 1),
            node(22, BRACKET_LOSERS, 2, 0),
            node(23, BRACKET_GRAND_FINAL, 1, 0),
            node(24, BRACKET_GRAND_FINAL_RESET, 1, 0),
        ]

        board = build_bracket_boards(matches)[0]
        assert [section.key for section in board.sections] == [
            SECTION_WINNERS,
            SECTION_LOSERS,
        ]
        assert board.has_losers is True

        winners = board.sections[0].columns
        assert [column.bracket_type for column in winners[-2:]] == [
            BRACKET_GRAND_FINAL,
            BRACKET_GRAND_FINAL_RESET,
        ]
        assert all(column.is_losers for column in board.sections[1].columns)

    def test_rami_vuoti_non_compaiono(self):
        """Un X a tavolino al turno 1 non produce perdenti (Step 7).

        Lo slot corrispondente del recupero resta non materializzato: la
        colonna deve avere un nodo solo, non due di cui uno vuoto.
        """
        matches = direct_elimination_8() + [node(20, BRACKET_LOSERS, 1, 1)]

        losers = build_bracket_boards(matches)[0].sections[1].columns[0]
        assert losers.size == 1
        assert losers.matches[0].bracket_slot == 1


class TestFormulaFisbb:
    def test_gironi_in_ordine_col_tabellone_finale_in_coda(self):
        matches = [
            node(1, BRACKET_WINNERS, 1, 0, group=1),
            node(2, BRACKET_WINNERS, 1, 0, group=0),
            node(3, BRACKET_WINNERS, 1, 0),
            node(4, BRACKET_WINNERS, 1, 0, group=2),
        ]

        boards = build_bracket_boards(matches)
        assert [board.group for board in boards] == [0, 1, 2, None]
        assert [board.is_group for board in boards] == [True, True, True, False]

    def test_i_gironi_non_si_mescolano(self):
        """Stessa tripla in gironi diversi: due colonne, non una da due nodi."""
        matches = [
            node(1, BRACKET_WINNERS, 1, 0, group=0),
            node(2, BRACKET_WINNERS, 1, 0, group=1),
        ]

        boards = build_bracket_boards(matches)
        assert len(boards) == 2
        for board in boards:
            assert board.sections[0].columns[0].size == 1


class TestPurezza:
    def test_niente_import_di_flask_o_sqlalchemy(self):
        import ast
        from pathlib import Path

        source = Path("models/matchmaking/bracket_view.py").read_text()
        moduli = set()
        for nodo in ast.walk(ast.parse(source)):
            if isinstance(nodo, ast.Import):
                moduli.update(alias.name.split(".")[0] for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                moduli.add(nodo.module.split(".")[0])

        assert not moduli & {"flask", "flask_babel", "sqlalchemy", "models"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
