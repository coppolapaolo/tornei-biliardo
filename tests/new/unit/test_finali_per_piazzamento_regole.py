"""Le finali per piazzamento dopo i gironi: le regole pure (piano gironi, PR 6).

Dopo l'ultimo turno dei gironi il p-esimo del girone A gioca contro il
p-esimo del girone B: 1ºA–1ºB per il 1°/2° posto, 2ºA–2ºB per il 3°/4°, e
così via. Prima versione con **due gironi**. Con gironi di taglia diversa
l'ultimo del girone più numeroso si classifica direttamente, dietro alla
coppia della finale precedente (SPECIFICHE.md, «Fase finale dopo i gironi»).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.classification.fase_finale import (
    bande_delle_finali,
    classifica_con_tabellone,
)
from models.matchmaking.bracket import BRACKET_PLACEMENT, BRACKET_WINNERS
from models.matchmaking.fase_finale import (
    MASSIMO_GIRONI_PER_PIAZZAMENTO,
    incroci_per_piazzamento,
    la_finale_del_turno,
    verifica_piazzamento,
)

pytestmark = pytest.mark.unit


class TestIncroci:
    def test_due_gironi_da_quattro(self):
        coppie, resto = incroci_per_piazzamento({0: [1, 2, 3, 4], 1: [5, 6, 7, 8]})
        assert coppie == [(1, 5), (2, 6), (3, 7), (4, 8)]
        assert resto == []

    def test_cinque_e_quattro_l_ultimo_del_piu_numeroso_va_diretto(self):
        coppie, resto = incroci_per_piazzamento({0: [1, 2, 3, 4, 9], 1: [5, 6, 7, 8]})
        assert coppie == [(1, 5), (2, 6), (3, 7), (4, 8)]
        assert resto == [9]

    def test_il_girone_piu_numeroso_puo_essere_il_secondo(self):
        coppie, resto = incroci_per_piazzamento({0: [1, 2, 3], 1: [5, 6, 7, 8]})
        assert coppie == [(1, 5), (2, 6), (3, 7)]
        assert resto == [8]

    def test_con_tre_gironi_non_si_fa(self):
        with pytest.raises(ValueError):
            incroci_per_piazzamento({0: [1, 2, 3], 1: [4, 5, 6], 2: [7, 8, 9]})

    def test_quanti_gironi(self):
        assert MASSIMO_GIRONI_PER_PIAZZAMENTO == 2
        assert verifica_piazzamento(2) is None
        assert verifica_piazzamento(3) == "gironi"
        assert verifica_piazzamento(1) == "gironi"


class TestBande:
    def test_ogni_finale_assegna_due_posti(self):
        coppie = [(1, 5), (2, 6), (3, 7), (4, 8)]
        # Vince sempre il girone B, tranne la finale per il 5°/6° posto.
        vincitori = {0: 5, 1: 6, 2: 3, 3: 8}
        bande, pari = bande_delle_finali(coppie, vincitori, [])
        assert bande == [[5], [1], [6], [2], [3], [7], [8], [4]]
        assert pari == frozenset()

    def test_l_ultimo_diretto_sta_in_fondo(self):
        bande, _pari = bande_delle_finali([(1, 5), (2, 6)], {0: 1, 1: 2}, [9])
        assert bande == [[1], [5], [2], [6], [9]]

    def test_una_finale_da_giocare_tiene_insieme_i_due(self):
        bande, pari = bande_delle_finali([(1, 5), (2, 6)], {0: 1, 1: None}, [])
        assert bande == [[1], [5], [2, 6]]
        assert pari == frozenset()

    def test_senza_partita_perche_ritirati_entrambi_restano_pari(self):
        bande, pari = bande_delle_finali(
            [(1, 5), (2, 6)], {0: 1}, [], senza_partita={1}
        )
        assert bande == [[1], [5], [2, 6]]
        assert pari == frozenset({2, 6})

    def test_la_classifica_della_serata(self):
        """Le bande sopra la classifica a gironi: nessun pari merito."""
        coppie = [(1, 5), (2, 6), (3, 7), (4, 8)]
        bande, pari = bande_delle_finali(coppie, {0: 5, 1: 2, 2: 7, 3: 4}, [9])
        # La classifica a gironi: prima i primi, poi i secondi… (pari per
        # partita giocata a coppie).
        gironi = [(1, [1, 5]), (3, [2, 6]), (5, [3, 7]), (7, [4, 8]), (9, [9])]
        fasce = classifica_con_tabellone(bande, gironi, pari_merito=pari)
        assert fasce == [
            (1, [5]),
            (2, [1]),
            (3, [2]),
            (4, [6]),
            (5, [7]),
            (6, [3]),
            (7, [4]),
            (8, [8]),
            (9, [9]),
        ]


class TestLaFinale:
    def test_la_finale_e_la_partita_per_il_primo_posto(self):
        nodi = [
            SimpleNamespace(bracket_type=BRACKET_PLACEMENT, bracket_slot=s)
            for s in (2, 0, 1)
        ]
        assert la_finale_del_turno(nodi) is nodi[1]

    def test_senza_la_coppia_del_primo_posto_nessuna_finale(self):
        nodi = [
            SimpleNamespace(bracket_type=BRACKET_PLACEMENT, bracket_slot=s)
            for s in (1, 2)
        ]
        assert la_finale_del_turno(nodi) is None

    def test_il_tabellone_resta_com_era(self):
        nodo = SimpleNamespace(bracket_type=BRACKET_WINNERS, bracket_group=None)
        assert la_finale_del_turno([nodo]) is nodo
