"""La fase finale dopo i gironi: le regole pure (piano gironi, PR 5).

Senza database: quanti passano, quanto è grande il tabellone, con che ordine
si entra, e come si compone la classifica finale.
"""

from __future__ import annotations

import pytest

from models.classification.fase_finale import classifica_con_tabellone
from models.matchmaking.fase_finale import (
    FaseFinale,
    qualificati_dei_gironi,
    qualificati_per_girone,
    semina_del_tabellone,
    taglia_del_tabellone,
    turni_del_tabellone,
    verifica_qualificati,
)
from models.matchmaking.group_phase import qualifier_seeding, seed_per_colonne

pytestmark = pytest.mark.unit


class TestValori:
    def test_fase_finale_si_legge_con_tolleranza(self):
        assert FaseFinale.resolve("tabellone") is FaseFinale.TABELLONE
        assert FaseFinale.resolve(None) is FaseFinale.NESSUNA
        assert FaseFinale.resolve("boh") is FaseFinale.NESSUNA

    def test_qualificati_per_girone_di_norma_due(self):
        assert qualificati_per_girone(None) == 2
        assert qualificati_per_girone("3") == 3
        assert qualificati_per_girone(0) == 1


class TestQuantoEGrande:
    @pytest.mark.parametrize(
        "qualificati, taglia, turni",
        [(2, 2, 1), (3, 4, 2), (4, 4, 2), (6, 8, 3), (8, 8, 3), (9, 16, 4)],
    )
    def test_potenza_di_due_subito_sopra(self, qualificati, taglia, turni):
        assert taglia_del_tabellone(qualificati) == taglia
        assert turni_del_tabellone(qualificati) == turni

    def test_si_fa_con_almeno_due_e_non_oltre_il_girone_piu_piccolo(self):
        assert verifica_qualificati([6, 5], 2) is None
        assert verifica_qualificati([6, 5], 5) is None
        assert verifica_qualificati([6, 5], 6) == "girone"
        assert verifica_qualificati([5], 1) == "pochi"
        assert verifica_qualificati([5], 4) is None
        assert verifica_qualificati([6, 5], 0) == "minimo"


class TestChiPassa:
    def test_i_primi_k_di_ogni_girone(self):
        q = qualificati_dei_gironi({0: [1, 2, 3], 1: [4, 5, 6]}, 2, {1, 2, 3, 4, 5, 6})
        assert q == {0: [1, 2], 1: [4, 5]}

    def test_chi_si_e_ritirato_lascia_il_posto_al_successivo(self):
        q = qualificati_dei_gironi({0: [1, 2, 3], 1: [4, 5, 6]}, 2, {1, 3, 4, 5, 6})
        assert q[0] == [1, 3]


class TestSemina:
    def test_per_colonne_prima_i_primi(self):
        # Girone A: 1, 2; girone B: 4, 5. Classifica a gironi: 4 meglio di 1,
        # e 2 meglio di 5.
        seed = semina_del_tabellone({0: [1, 2], 1: [4, 5]}, [4, 1, 2, 5])
        assert seed == [4, 1, 2, 5]

    def test_con_tre_gironi_i_migliori_primi_in_testa(self):
        seed = semina_del_tabellone(
            {0: [1, 2], 1: [3, 4], 2: [5, 6]}, [5, 1, 3, 2, 6, 4]
        )
        assert seed[:3] == [5, 1, 3]
        assert seed[3:] == [2, 6, 4]

    def test_qualifier_seeding_della_formula_fisbb_non_cambia(self):
        gironi = [[1, 2, 3, 4], [5, 6, 7, 8]]
        assert qualifier_seeding(gironi) == [1, 5, 2, 6, 3, 7, 4, 8]
        with pytest.raises(ValueError):
            qualifier_seeding([[1, 2], [3, 4]])

    def test_seed_per_colonne_accetta_gironi_di_lunghezza_diversa(self):
        assert seed_per_colonne([[1, 2], [3]]) == [1, 3, 2]


class TestClassificaFinale:
    #: Classifica a gironi di 2 gironi da 4: A1, B1, A2, B2, A3, B3, A4, B4.
    GIRONI = [(1, [11]), (2, [21]), (3, [12]), (4, [22]), (5, [13]), (6, [23])]

    def test_finale_e_finalina(self):
        # Finale 21-11, vince 21; finalina 22-12, vince 12.
        bande = [[21], [11], [12], [22]]
        fasce = classifica_con_tabellone(bande, self.GIRONI)
        assert fasce == [
            (1, [21]),
            (2, [11]),
            (3, [12]),
            (4, [22]),
            (5, [13]),
            (6, [23]),
        ]

    def test_senza_finalina_due_terzi(self):
        bande = [[21], [11], [12, 22]]
        fasce = classifica_con_tabellone(bande, self.GIRONI, pari_merito={12, 22})
        assert fasce[2] == (3, [12, 22])
        assert fasce[3] == (5, [13])

    def test_chi_esce_ai_quarti_si_ordina_per_piazzamento_nel_girone(self):
        # Tabellone da 8: i quattro usciti ai quarti sono 13, 23 (terzi del
        # girone) e 12, 22 (secondi): prima i secondi, nell'ordine della
        # classifica a gironi.
        gironi = [
            (1, [11]),
            (2, [21]),
            (3, [12]),
            (4, [22]),
            (5, [13]),
            (6, [23]),
            (7, [14]),
            (8, [24]),
        ]
        bande = [[11], [21], [14, 24], [12, 13, 22, 23]]
        fasce = classifica_con_tabellone(bande, gironi, pari_merito={14, 24})
        assert fasce[2] == (3, [14, 24])
        assert fasce[3:] == [(5, [12]), (6, [22]), (7, [13]), (8, [23])]

    def test_a_pari_piazzamento_resta_il_pari_merito(self):
        gironi = [(1, [11, 21]), (3, [12]), (4, [22])]
        bande = [[12], [22], [11, 21]]
        fasce = classifica_con_tabellone(bande, gironi)
        assert fasce[2] == (3, [11, 21])

    def test_i_non_qualificati_vengono_dopo_nell_ordine_dei_gironi(self):
        bande = [[11, 21, 12, 22]]
        fasce = classifica_con_tabellone(bande, self.GIRONI)
        # Tabellone in corso: i quattro ancora in corsa, nell'ordine dei
        # gironi, poi gli altri.
        assert [f[1][0] for f in fasce] == [11, 21, 12, 22, 13, 23]
