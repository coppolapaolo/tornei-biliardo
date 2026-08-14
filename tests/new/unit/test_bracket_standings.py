"""Classifica per bande ricavata dal tabellone (Step 9, US-16).

Nel tabellone la posizione non si conta, si legge: chi esce allo stesso turno ha
fatto lo stesso percorso, quindi condivide la posizione. I quattro
quartifinalisti sono tutti 5° e la banda successiva riparte da 9, non da 6.

Due eccezioni: la finalina scioglie la banda dei semifinalisti, e nel doppio KO
il terzo posto lo assegna già il tabellone.
"""

from __future__ import annotations

import pytest

from models.classification.bracket_standings import (
    BracketMatch,
    elimination_bands,
    positions_from_bands,
)

pytestmark = pytest.mark.unit


def _match(bracket_type, round_number, winner, loser, order=0):
    return BracketMatch(
        bracket_type=bracket_type,
        round_number=round_number,
        players=(winner, loser) if loser else (winner,),
        winner_id=winner,
        loser_id=loser,
        order=order,
    )


def _positions(matches, **kwargs):
    return positions_from_bands(elimination_bands(matches, **kwargs))


class TestEliminazioneDiretta:
    def _tabellone_da_otto(self):
        """1 vince tutto; 5 perde la finale; 3 e 7 le semifinali."""
        return [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 1, 5, 6, 2),
            _match("W", 1, 7, 8, 3),
            _match("W", 2, 1, 3, 4),
            _match("W", 2, 5, 7, 5),
            _match("W", 3, 1, 5, 6),
        ]

    def test_bande_a_pari_merito(self):
        positions = _positions(self._tabellone_da_otto())

        assert positions[1] == 1, "il vincitore"
        assert positions[5] == 2, "il finalista sconfitto"
        assert positions[3] == positions[7] == 3, "i semifinalisti, a pari merito"
        # La banda successiva riparte da 5, non da 4: i pari merito occupano
        # comunque il loro posto.
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_la_finalina_scioglie_la_banda(self):
        """Con il 3°/4° i due semifinalisti smettono di essere pari merito."""
        matches = self._tabellone_da_otto() + [_match("3P", 3, 7, 3, 7)]

        positions = _positions(matches)

        assert positions[1] == 1
        assert positions[5] == 2
        assert positions[7] == 3, "vincitore della finalina"
        assert positions[3] == 4, "perdente della finalina"
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_gara_in_corso_chi_e_dentro_e_primo(self):
        """Finché non esci il tabellone non ti ha ancora ordinato."""
        matches = self._tabellone_da_otto()[:4]  # solo il primo turno

        positions = _positions(matches)

        assert {positions[p] for p in (1, 3, 5, 7)} == {1}
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_bye_non_producono_eliminati(self):
        """Chi passa senza giocare non fa uscire nessuno."""
        matches = [
            BracketMatch("W", 1, (1,), winner_id=1, loser_id=None, order=0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),
        ]

        positions = _positions(matches)

        assert positions == {1: 1, 3: 2, 4: 3}


class TestDoppioKO:
    def test_serve_la_seconda_sconfitta_per_uscire(self):
        """Tabellone da 4: chi perde una volta è ancora in gioco."""
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),  # 3 scende nel losers, non esce
            _match("L", 2, 2, 4, 3),  # 4 esce (seconda sconfitta)
            _match("L", 3, 3, 2, 4),  # 2 esce
            _match("GF", 4, 1, 3, 5),  # 3 esce
        ]

        positions = _positions(matches, double_elimination=True)

        assert positions == {1: 1, 3: 2, 2: 3, 4: 4}

    def test_a_meta_gara_chi_ha_una_sconfitta_e_ancora_dentro(self):
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
        ]

        positions = _positions(matches, double_elimination=True)

        # Nessuno è ancora eliminato: tutti primi a pari merito.
        assert set(positions.values()) == {1}

    def test_la_bella_decide_il_primo_posto(self):
        """Se il ripescato vince la finale, conta l'esito della bella."""
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),
            _match("L", 2, 2, 4, 3),
            _match("L", 3, 3, 2, 4),
            _match("GF", 4, 3, 1, 5),  # vince il campione del losers
            _match("GFR", 5, 3, 1, 6),  # e vince anche la bella
        ]

        positions = _positions(matches, double_elimination=True)

        assert positions[3] == 1
        assert positions[1] == 2, "eliminato alla seconda sconfitta, nella bella"


class TestPosizioniDalleBande:
    def test_la_banda_vale_la_sua_posizione_piu_alta(self):
        bande = [[1], [2], [3, 4], [5, 6, 7, 8]]

        assert positions_from_bands(bande) == {
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            5: 5,
            6: 5,
            7: 5,
            8: 5,
        }

    def test_nessuna_banda_nessuna_posizione(self):
        assert positions_from_bands([]) == {}
