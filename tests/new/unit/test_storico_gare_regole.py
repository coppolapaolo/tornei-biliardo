"""Le regole dello storico delle gare, senza database.

`models/storico/gare.py` tiene le regole in funzioni pure su `RigaStorico`:
qui si provano con gare finte. Cosa è concluso e cosa è «mio» lo decide il
database e sta nel test di integrazione.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from models.storico.gare import (
    CHI_DIRETTE,
    CHI_GIOCATE,
    PASSO,
    FiltriStorico,
    RigaStorico,
    componi,
    filtra,
    ordina,
    raggruppa_per_mese,
)


def _gara(id, nome, giorno, sala="Sala Test", campionato=None, disciplina="8_ball"):
    return SimpleNamespace(
        id=id,
        display_name=nome,
        date=giorno,
        location=sala,
        campionato=SimpleNamespace(name=campionato) if campionato else None,
        discipline=disciplina,
    )


def _riga(id, nome, giorno, **fatti):
    campionato = fatti.pop("campionato", None)
    sala = fatti.pop("sala", "Sala Test")
    return RigaStorico(gara=_gara(id, nome, giorno, sala, campionato), **fatti)


@pytest.fixture
def righe():
    return [
        _riga(
            1, "Coppa di Ferragosto", date(2026, 8, 15), hai_giocato=True, piazzamento=1
        ),
        _riga(2, "Notturna", date(2026, 7, 25), hai_diretto=True, sala="Sala Centrale"),
        _riga(3, "Gara 2", date(2026, 8, 16), campionato="Campionato Sociale"),
        _riga(4, "Vecchia", date(2025, 3, 3), hai_giocato=True, piazzamento=7),
        _riga(5, "Senza data", None),
    ]


@pytest.mark.unit
class TestFiltriDaParametri:
    def test_un_valore_fuori_dalle_scelte_vale_come_nessun_filtro(self):
        f = FiltriStorico.da_parametri(
            {"chi": "tutte-le-mie", "primi": "2", "anno": "abc", "mostra": "3"}
        )
        assert f.chi == "tutte"
        assert f.primi is None
        assert f.anno is None
        assert f.mostra == PASSO, "meno di un passo non ha senso"

    def test_i_valori_buoni_passano(self):
        f = FiltriStorico.da_parametri(
            {
                "q": "  ferragosto ",
                "chi": "giocate",
                "primi": "3",
                "anno": "2026",
                "mostra": "40",
            }
        )
        assert f == FiltriStorico("ferragosto", CHI_GIOCATE, 3, 2026, 40)

    def test_parametri_per_url_tengono_solo_cio_che_conta(self):
        f = FiltriStorico("x", CHI_DIRETTE, None, 2026)
        assert f.parametri() == {"q": "x", "chi": "dirette", "anno": 2026}
        # un cambio sostituisce; «tutte» e i vuoti spariscono dall'indirizzo
        assert f.parametri(chi="tutte") == {"q": "x", "anno": 2026}
        assert f.parametri(mostra=40)["mostra"] == 40


@pytest.mark.unit
class TestFiltra:
    def test_la_ricerca_guarda_nome_sala_e_campionato(self, righe):
        assert [r.id for r in filtra(righe, FiltriStorico(testo="FERRAGOSTO"))] == [1]
        assert [r.id for r in filtra(righe, FiltriStorico(testo="centrale"))] == [2]
        assert [r.id for r in filtra(righe, FiltriStorico(testo="sociale"))] == [3]

    def test_che_ho_giocato_e_che_ho_diretto(self, righe):
        assert {r.id for r in filtra(righe, FiltriStorico(chi=CHI_GIOCATE))} == {1, 4}
        assert {r.id for r in filtra(righe, FiltriStorico(chi=CHI_DIRETTE))} == {2}

    def test_nei_primi_n_guarda_il_piazzamento(self, righe):
        assert {r.id for r in filtra(righe, FiltriStorico(primi=3))} == {1}
        assert {r.id for r in filtra(righe, FiltriStorico(primi=10))} == {1, 4}

    def test_anno(self, righe):
        assert {r.id for r in filtra(righe, FiltriStorico(anno=2025))} == {4}
        # senza data non appartiene a nessun anno
        assert 5 not in {r.id for r in filtra(righe, FiltriStorico(anno=2026))}


@pytest.mark.unit
def test_ordina_dalla_piu_recente_e_senza_data_in_fondo(righe):
    assert [r.id for r in ordina(righe)] == [3, 1, 2, 4, 5]


@pytest.mark.unit
def test_raggruppa_per_mese_spezza_a_ogni_cambio(righe):
    gruppi = raggruppa_per_mese(ordina(righe))
    assert [(chiave, [r.id for r in rr]) for chiave, rr in gruppi] == [
        ((2026, 8), [3, 1]),
        ((2026, 7), [2]),
        ((2025, 3), [4]),
        ((0, 0), [5]),
    ]


@pytest.mark.unit
class TestComponi:
    def test_i_numeri_di_testa_non_seguono_chi_e_nei_primi(self, righe):
        """«34 gare concluse nel 2026 · 9 giocate, 4 dirette» descrive l'anno,
        non il chip appena premuto: altrimenti premendo «che ho giocato» il
        conteggio delle dirette andrebbe a zero e sembrerebbe un errore."""
        s = componi(righe, FiltriStorico(chi=CHI_GIOCATE, anno=2026))
        assert s.conteggio == 3
        assert (s.giocate, s.dirette) == (1, 1)
        assert s.totale == 1
        assert [r.id for r in s.righe] == [1]

    def test_mostra_taglia_e_conta_le_restanti(self):
        tante = [_riga(i, f"G{i}", date(2026, 1, 1)) for i in range(1, 46)]
        s = componi(tante, FiltriStorico())
        assert len(s.righe) == PASSO
        assert s.totale == 45
        assert (s.restanti, s.altre) == (25, PASSO)
        s2 = componi(tante, FiltriStorico(mostra=40))
        assert (len(s2.righe), s2.restanti, s2.altre) == (40, 5, 5)

    def test_gli_anni_sono_quelli_di_tutte_le_gare(self, righe):
        s = componi(righe, FiltriStorico(anno=2025))
        assert s.anni == [
            2026,
            2025,
        ], "la tendina deve offrire anche gli anni non scelti"
