"""Le regole del girone all'italiana a più gironi, senza database (ADR-076).

Modulo puro `models/matchmaking/gironi.py`: quanti gironi, chi va dove,
quanti turni. Le regole numeriche hanno anche il loro presidio contro la
specifica in `test_specifiche_conformita.py::TestIGironi`.
"""

from __future__ import annotations

from collections import Counter

import pytest

from models.matchmaking.group_phase import distribute_into_groups
from models.matchmaking.gironi import (
    ComposizioneGironi,
    Iscritto,
    componi_gironi,
    gironi_possibili,
    nome_del_girone,
    ordine_di_composizione,
    proposta_di_gironi,
    taglie_dei_gironi,
    turni_dei_gironi,
    verifica_numero_di_gironi,
)


class TestQuantiGironi:
    @pytest.mark.parametrize(
        "iscritti,tetto,atteso",
        [
            (11, 2, 2),  # la serata della locandina
            (11, 4, 2),  # uno ogni sei, per eccesso
            (12, 4, 2),
            (13, 4, 3),
            (5, 2, 1),  # due gironi da 3 non ci stanno
            (6, 2, 1),  # sei iscritti: un girone solo, non due da tre
            (7, 2, 2),
            (30, 3, 3),  # oltre il tetto no
            (8, None, 1),  # senza tetto, girone unico
        ],
    )
    def test_la_proposta(self, iscritti, tetto, atteso):
        assert proposta_di_gironi(iscritti, tetto) == atteso

    def test_il_massimo_scende_con_pochi_iscritti(self):
        assert gironi_possibili(11, 4) == 3
        assert gironi_possibili(5, 2) == 1
        assert gironi_possibili(6, 2) == 2
        assert gironi_possibili(2, 2) == 1

    def test_almeno_tre_per_girone(self):
        assert verifica_numero_di_gironi(8, 3, 4) == "giocatori"
        assert verifica_numero_di_gironi(9, 3, 4) is None

    def test_mai_oltre_il_tetto(self):
        assert verifica_numero_di_gironi(30, 3, 2) == "tetto"
        assert verifica_numero_di_gironi(30, 0, 2) == "minimo"

    def test_un_girone_va_sempre_bene(self):
        assert verifica_numero_di_gironi(2, 1, None) is None


class TestTaglieETurni:
    def test_undici_in_due_gironi_sei_e_cinque(self):
        assert taglie_dei_gironi(11, 2) == [6, 5]

    def test_i_turni_sono_quelli_del_girone_piu_numeroso(self):
        assert turni_dei_gironi([6, 5]) == 5
        assert turni_dei_gironi([4, 3]) == 3
        assert turni_dei_gironi([7, 6]) == 7
        assert turni_dei_gironi([4, 4]) == 3


class TestNomi:
    def test_a_b_c(self):
        assert [nome_del_girone(i) for i in range(4)] == ["A", "B", "C", "D"]
        assert nome_del_girone(26) == "AA"


class TestDistribuzione:
    def test_andata_e_ritorno(self):
        """1 al girone A, 2 al B, 3 al B, 4 all'A, 5 all'A, 6 al B."""
        assert distribute_into_groups([1, 2, 3, 4, 5, 6], 2) == [[1, 4, 5], [2, 3, 6]]

    def test_taglie_qualsiasi(self):
        gironi = distribute_into_groups(list(range(1, 12)), 2)
        assert [len(g) for g in gironi] == [6, 5]
        gironi = distribute_into_groups(list(range(1, 11)), 3)
        assert [len(g) for g in gironi] == [4, 3, 3]

    def test_i_compagni_si_separano(self):
        # 1 e 2 sono compagni: nella stessa riga vanno in gironi diversi
        # comunque; 3 e 4 anche. 1 e 4 compagni, nella serpentina pura
        # finirebbero insieme nel girone A.
        squadre = {1: "Nord", 4: "Nord"}
        gironi = distribute_into_groups([1, 2, 3, 4], 2, squadre)
        assert not any({1, 4} <= set(g) for g in gironi)


def _iscritti():
    return [
        Iscritto(1, elo=1500, categoria=1),
        Iscritto(2, elo=1700, categoria=0),
        Iscritto(3, elo=None, categoria=0),
        Iscritto(4, elo=1600, categoria=None),
        Iscritto(5, elo=1400, categoria=1),
    ]


class TestComposizione:
    def test_per_elo_dal_piu_alto_chi_non_ce_l_ha_in_fondo(self):
        ordine = ordine_di_composizione(_iscritti(), ComposizioneGironi.ELO, 7)
        assert ordine == [2, 4, 1, 5, 3]

    def test_per_categoria_poi_elo(self):
        ordine = ordine_di_composizione(_iscritti(), ComposizioneGironi.CATEGORIA, 7)
        assert ordine == [2, 3, 1, 5, 4]

    def test_il_sorteggio_dipende_solo_dal_seme(self):
        a = ordine_di_composizione(_iscritti(), ComposizioneGironi.SORTEGGIO, 42)
        b = ordine_di_composizione(
            list(reversed(_iscritti())), ComposizioneGironi.SORTEGGIO, 42
        )
        assert a == b
        assert sorted(a) == [1, 2, 3, 4, 5]
        semi = {
            tuple(ordine_di_composizione(_iscritti(), ComposizioneGironi.SORTEGGIO, s))
            for s in range(20)
        }
        assert len(semi) > 1

    def test_per_elo_i_migliori_in_gironi_diversi(self):
        iscritti = [Iscritto(i, elo=2000 - i) for i in range(1, 12)]
        gironi = componi_gironi(iscritti, 2, ComposizioneGironi.ELO, 1)
        assert gironi[0][0] == 1 and gironi[1][0] == 2
        assert Counter(len(g) for g in gironi) == Counter([6, 5])

    def test_separa_i_compagni_solo_se_richiesto(self):
        iscritti = [
            Iscritto(1, elo=1900, squadra="Nord"),
            Iscritto(2, elo=1800),
            Iscritto(3, elo=1700),
            Iscritto(4, elo=1600, squadra="Nord"),
        ]
        insieme = componi_gironi(iscritti, 2, ComposizioneGironi.ELO, 1)
        assert any({1, 4} <= set(g) for g in insieme)
        separati = componi_gironi(
            iscritti, 2, ComposizioneGironi.ELO, 1, separa_compagni=True
        )
        assert not any({1, 4} <= set(g) for g in separati)

    def test_valore_sconosciuto_vale_sorteggio(self):
        assert ComposizioneGironi.resolve(None) is ComposizioneGironi.SORTEGGIO
        assert ComposizioneGironi.resolve("boh") is ComposizioneGironi.SORTEGGIO
        assert ComposizioneGironi.resolve("elo") is ComposizioneGironi.ELO
