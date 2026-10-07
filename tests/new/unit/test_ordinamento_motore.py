"""Il motore unico della catena degli spareggi (ADR-078).

Test puri, senza database: il motore riceve i giocatori già aggregati e
restituisce le fasce della classifica. Qui si fissano le regole del motore in
sé — come lavora ogni criterio, l'ordine dei criteri, lo scontro diretto fra
due e fra tre, lo spareggio SSR «fino al N° posto», il sorteggio sempre ultimo.
Le catene di default per livello e sistema sono in fondo.
"""

from __future__ import annotations

import pytest

from models.classification.ordinamento import (
    Concorrente,
    Criterio,
    Livello,
    Scontro,
    Voce,
    catena_di_default,
    chiave_di_sorteggio,
    criteri_ammessi,
    descrivi_catena,
    normalizza_catena,
    ordina,
    parse_catena,
    serializza_catena,
)
from models.status_enum import ClassificationSystem

pytestmark = pytest.mark.unit


def _c(pid, **kw) -> Concorrente:
    kw.setdefault("sorteggio", pid)
    return Concorrente(player_id=pid, **kw)


def _posizioni(fasce) -> dict[int, int]:
    return {g.player_id: f.posizione for f in fasce for g in f.giocatori}


def _ordine(fasce) -> list[int]:
    return [g.player_id for f in fasce for g in f.giocatori]


V = Voce


class TestCriterioPrincipale:
    def test_ordina_per_il_principale_decrescente(self):
        fasce = ordina(
            [_c(1, vittorie=1), _c(2, vittorie=3), _c(3, vittorie=2)],
            Criterio.VITTORIE,
            (),
        )
        assert _ordine(fasce) == [2, 3, 1]
        assert _posizioni(fasce) == {2: 1, 3: 2, 1: 3}

    def test_senza_catena_i_pari_condividono_la_posizione(self):
        fasce = ordina(
            [_c(1, vittorie=2), _c(2, vittorie=2), _c(3, vittorie=1)],
            Criterio.VITTORIE,
            (),
        )
        assert _posizioni(fasce) == {1: 1, 2: 1, 3: 3}

    def test_completa_aggiunge_il_sorteggio_in_coda(self):
        fasce = ordina(
            [_c(1, vittorie=2, sorteggio=9), _c(2, vittorie=2, sorteggio=4)],
            Criterio.VITTORIE,
            (),
            completa=True,
        )
        assert _ordine(fasce) == [2, 1]
        assert _posizioni(fasce) == {2: 1, 1: 2}


class TestCriteriSemplici:
    def test_differenza_rack(self):
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=1),
                _c(2, vittorie=2, differenza_rack=4),
            ],
            Criterio.VITTORIE,
            (V(Criterio.DIFFERENZA_RACK),),
        )
        assert _ordine(fasce) == [2, 1]

    def test_rack_vinti(self):
        fasce = ordina(
            [_c(1, vittorie=2, rack_vinti=6), _c(2, vittorie=2, rack_vinti=8)],
            Criterio.VITTORIE,
            (V(Criterio.RACK_VINTI),),
        )
        assert _ordine(fasce) == [2, 1]

    def test_vittorie_come_spareggio_di_rack(self):
        fasce = ordina(
            [_c(1, rack_vinti=8, vittorie=1), _c(2, rack_vinti=8, vittorie=2)],
            Criterio.RACK_VINTI,
            (V(Criterio.VITTORIE),),
        )
        assert _ordine(fasce) == [2, 1]

    def test_posizione_precedente_crescente_e_chi_non_ce_l_ha_va_in_fondo(self):
        fasce = ordina(
            [
                _c(1, vittorie=1, posizione_precedente=None),
                _c(2, vittorie=1, posizione_precedente=5),
                _c(3, vittorie=1, posizione_precedente=2),
            ],
            Criterio.VITTORIE,
            (V(Criterio.POSIZIONE_PRECEDENTE),),
        )
        assert _ordine(fasce) == [3, 2, 1]

    def test_un_criterio_che_non_separa_passa_al_successivo(self):
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=3, posizione_precedente=2),
                _c(2, vittorie=2, differenza_rack=3, posizione_precedente=1),
            ],
            Criterio.VITTORIE,
            (V(Criterio.DIFFERENZA_RACK), V(Criterio.POSIZIONE_PRECEDENTE)),
        )
        assert _ordine(fasce) == [2, 1]

    def test_l_ordine_dei_criteri_conta(self):
        giocatori = [
            _c(1, vittorie=2, differenza_rack=5, rack_vinti=6),
            _c(2, vittorie=2, differenza_rack=3, rack_vinti=9),
        ]
        prima_diff = ordina(
            giocatori,
            Criterio.VITTORIE,
            (V(Criterio.DIFFERENZA_RACK), V(Criterio.RACK_VINTI)),
        )
        prima_rack = ordina(
            giocatori,
            Criterio.VITTORIE,
            (V(Criterio.RACK_VINTI), V(Criterio.DIFFERENZA_RACK)),
        )
        assert _ordine(prima_diff) == [1, 2]
        assert _ordine(prima_rack) == [2, 1]


class TestSpareggioSSR:
    def test_lo_ssr_separa_i_pari_entro_il_posto(self):
        fasce = ordina(
            [_c(1, vittorie=2, ssr=3), _c(2, vittorie=2, ssr=7), _c(3, vittorie=1)],
            Criterio.VITTORIE,
            (V(Criterio.SPAREGGIO_SSR, fino_al=3),),
        )
        assert _posizioni(fasce) == {2: 1, 1: 2, 3: 3}

    def test_oltre_il_posto_lo_ssr_non_decide(self):
        fasce = ordina(
            [
                _c(1, vittorie=5),
                _c(2, vittorie=4),
                _c(3, vittorie=3),
                _c(4, vittorie=2, ssr=9),
                _c(5, vittorie=2, ssr=1),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SPAREGGIO_SSR, fino_al=3),),
        )
        assert _posizioni(fasce)[4] == _posizioni(fasce)[5] == 4

    def test_chi_non_ha_tirato_viene_dopo_chi_ha_fatto_zero(self):
        fasce = ordina(
            [_c(1, vittorie=2, ssr=None), _c(2, vittorie=2, ssr=0)],
            Criterio.VITTORIE,
            (V(Criterio.SPAREGGIO_SSR, fino_al=3),),
        )
        assert _ordine(fasce) == [2, 1]

    def test_a_ssr_uguale_il_pari_resta(self):
        fasce = ordina(
            [
                _c(1, vittorie=2, ssr=4),
                _c(2, vittorie=2, ssr=4),
                _c(3, vittorie=2, ssr=6),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SPAREGGIO_SSR, fino_al=3),),
        )
        assert _posizioni(fasce) == {3: 1, 1: 2, 2: 2}

    def test_senza_limite_lo_ssr_vale_ovunque(self):
        """Nel campionato lo SSR è la somma, e vale a ogni posizione."""
        fasce = ordina(
            [_c(i, vittorie=10 - i) for i in range(1, 6)]
            + [_c(8, vittorie=1, ssr=2), _c(9, vittorie=1, ssr=5)],
            Criterio.VITTORIE,
            (V(Criterio.SPAREGGIO_SSR),),
        )
        assert _ordine(fasce)[-2:] == [9, 8]


class TestScontriDiretti:
    def test_fra_due_decide_chi_ha_vinto_lo_scontro(self):
        fasce = ordina(
            [_c(1, vittorie=2), _c(2, vittorie=2)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI),),
            scontri=[Scontro(1, 2, 1, 3, vincitore=2)],
        )
        assert _ordine(fasce) == [2, 1]

    def test_fra_due_che_non_si_sono_incontrati_non_decide(self):
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=1),
                _c(2, vittorie=2, differenza_rack=5),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK)),
            scontri=[Scontro(1, 3, 3, 0, vincitore=1)],
        )
        assert _ordine(fasce) == [2, 1]

    def test_un_pareggio_nello_scontro_non_decide(self):
        fasce = ordina(
            [_c(1, vittorie=2), _c(2, vittorie=2)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI),),
            scontri=[Scontro(1, 2, 1, 1, vincitore=None)],
        )
        assert _posizioni(fasce) == {1: 1, 2: 1}

    def test_fra_due_in_parita_di_scontri_non_decide(self):
        """Due incontri, una vittoria a testa (in gare diverse del campionato,
        o all'andata e al ritorno): nessun vincolo, decide il criterio dopo."""
        fasce = ordina(
            [
                _c(1, vittorie=2, differenza_rack=1),
                _c(2, vittorie=2, differenza_rack=4),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK)),
            scontri=[
                Scontro(1, 2, 3, 1, vincitore=1),
                Scontro(2, 1, 3, 0, vincitore=2),
            ],
        )
        assert _ordine(fasce) == [2, 1]

    def test_fra_due_conta_chi_ha_vinto_piu_scontri(self):
        fasce = ordina(
            [_c(1, vittorie=2, differenza_rack=9), _c(2, vittorie=2)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK)),
            scontri=[
                Scontro(1, 2, 3, 1, vincitore=1),
                Scontro(2, 1, 3, 0, vincitore=2),
                Scontro(2, 1, 3, 2, vincitore=2),
            ],
        )
        assert _ordine(fasce) == [2, 1]

    def test_tre_con_un_vincolo_solo(self):
        """1 ha battuto 2; 3 non ha incontrato nessuno. Il 3 lo colloca il
        criterio successivo, e l'1 resta sempre davanti al 2."""
        scontri = [Scontro(1, 2, 3, 1, vincitore=1)]
        catena = (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK))

        def ordine(d1, d2, d3):
            return _ordine(
                ordina(
                    [
                        _c(1, vittorie=2, differenza_rack=d1),
                        _c(2, vittorie=2, differenza_rack=d2),
                        _c(3, vittorie=2, differenza_rack=d3),
                    ],
                    Criterio.VITTORIE,
                    catena,
                    scontri=scontri,
                )
            )

        # Il 3 meglio di tutti per differenza: primo.
        assert ordine(1, 5, 9) == [3, 1, 2]
        # Il 3 in mezzo: il 2 ha la differenza migliore ma ha perso con l'1.
        assert ordine(1, 9, 5) == [3, 1, 2]
        assert ordine(6, 4, 5) == [1, 3, 2]
        # Passato l'1, fra il 2 e il 3 decide la differenza.
        assert ordine(6, 9, 5) == [1, 2, 3]
        # Il 3 peggio di tutti.
        assert ordine(6, 9, 0) == [1, 2, 3]

    def test_il_cerchio_resta_pari_e_il_battuto_da_tutti_e_ultimo(self):
        """1>2, 2>3, 3>1 e tutti hanno battuto il 4: chi si è battuto a
        vicenda in giro resta pari sullo scontro, e lo ordina il criterio
        dopo; il 4 è ultimo anche con la differenza migliore."""
        scontri = [
            Scontro(1, 2, 3, 1, vincitore=1),
            Scontro(2, 3, 3, 1, vincitore=2),
            Scontro(3, 1, 3, 1, vincitore=3),
            Scontro(1, 4, 3, 0, vincitore=1),
            Scontro(2, 4, 3, 0, vincitore=2),
            Scontro(3, 4, 3, 0, vincitore=3),
        ]
        fasce = ordina(
            [
                _c(1, vittorie=3, differenza_rack=1),
                _c(2, vittorie=3, differenza_rack=3),
                _c(3, vittorie=3, differenza_rack=2),
                _c(4, vittorie=3, differenza_rack=9),
            ],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK)),
            scontri=scontri,
        )
        assert _ordine(fasce) == [2, 3, 1, 4]

    def test_nel_cerchio_senza_altri_criteri_si_resta_pari(self):
        scontri = [
            Scontro(1, 2, 3, 1, vincitore=1),
            Scontro(2, 3, 3, 1, vincitore=2),
            Scontro(3, 1, 3, 1, vincitore=3),
            Scontro(1, 4, 3, 0, vincitore=1),
        ]
        fasce = ordina(
            [_c(p, vittorie=3) for p in (1, 2, 3, 4)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI),),
            scontri=scontri,
        )
        assert _posizioni(fasce) == {1: 1, 2: 1, 3: 1, 4: 4}

    def test_nessun_risultato_diretto_viene_contraddetto(self):
        """Una catena lunga di vincoli: 1>2>3>4, con le differenze al
        contrario. L'ordine è quello degli scontri."""
        scontri = [
            Scontro(1, 2, 3, 2, vincitore=1),
            Scontro(2, 3, 3, 2, vincitore=2),
            Scontro(3, 4, 3, 2, vincitore=3),
        ]
        fasce = ordina(
            [_c(p, vittorie=2, differenza_rack=p) for p in (1, 2, 3, 4)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI), V(Criterio.DIFFERENZA_RACK)),
            scontri=scontri,
        )
        assert _ordine(fasce) == [1, 2, 3, 4]

    def test_conta_chi_vince_non_i_triangoli(self):
        """A triangoli vale lo stesso: chi ha vinto lo scontro sta davanti."""
        fasce = ordina(
            [_c(1, rack_vinti=8), _c(2, rack_vinti=8)],
            Criterio.RACK_VINTI,
            (V(Criterio.SCONTRI_DIRETTI),),
            scontri=[Scontro(1, 2, 2, 3, vincitore=2)],
        )
        assert _ordine(fasce) == [2, 1]

    def test_nel_turno_chi_resta_indistinguibile_va_al_sorteggio(self):
        scontri = [
            Scontro(1, 2, 3, 1, vincitore=1),
            Scontro(2, 3, 3, 1, vincitore=2),
            Scontro(3, 1, 3, 1, vincitore=3),
        ]
        fasce = ordina(
            [_c(p, vittorie=2) for p in (1, 2, 3)],
            Criterio.VITTORIE,
            (V(Criterio.SCONTRI_DIRETTI),),
            scontri=scontri,
            completa=True,
        )
        assert [len(f.giocatori) for f in fasce] == [1, 1, 1]


class TestSorteggio:
    def test_il_sorteggio_e_deterministico(self):
        assert chiave_di_sorteggio("gara:7", 3) == chiave_di_sorteggio("gara:7", 3)

    def test_il_sorteggio_cambia_col_seme(self):
        chiavi_a = sorted(range(1, 30), key=lambda p: chiave_di_sorteggio("a", p))
        chiavi_b = sorted(range(1, 30), key=lambda p: chiave_di_sorteggio("b", p))
        assert chiavi_a != chiavi_b

    def test_il_sorteggio_non_e_l_ordine_degli_id(self):
        ordine = sorted(range(1, 30), key=lambda p: chiave_di_sorteggio("gara:1", p))
        assert ordine != list(range(1, 30))


class TestCatene:
    def test_andata_e_ritorno_della_serializzazione(self):
        catena = (
            V(Criterio.SCONTRI_DIRETTI),
            V(Criterio.SPAREGGIO_SSR, fino_al=2),
            V(Criterio.SORTEGGIO),
        )
        testo = serializza_catena(catena)
        assert testo == ["scontri_diretti", "ssr:2", "sorteggio"]
        assert parse_catena(testo) == catena

    def test_voci_ignote_si_scartano(self):
        assert parse_catena(["differenza_rack", "boh", "ssr:x"]) == (
            V(Criterio.DIFFERENZA_RACK),
        )

    def test_normalizza_toglie_doppioni_principale_e_mette_il_sorteggio_in_fondo(self):
        catena = (
            V(Criterio.SORTEGGIO),
            V(Criterio.VITTORIE),
            V(Criterio.DIFFERENZA_RACK),
            V(Criterio.DIFFERENZA_RACK),
            V(Criterio.SPAREGGIO_SSR, fino_al=3),
            V(Criterio.SPAREGGIO_SSR, fino_al=2),
        )
        assert normalizza_catena(catena, Livello.GARA, ClassificationSystem.WINS) == (
            V(Criterio.DIFFERENZA_RACK),
            V(Criterio.SPAREGGIO_SSR, fino_al=3),
            V(Criterio.SORTEGGIO),
        )

    def test_nel_turno_lo_ssr_non_e_ammesso_e_il_sorteggio_e_implicito(self):
        assert Criterio.SPAREGGIO_SSR not in criteri_ammessi(
            Livello.TURNO, ClassificationSystem.WINS
        )
        assert normalizza_catena(
            (V(Criterio.SPAREGGIO_SSR, fino_al=3), V(Criterio.DIFFERENZA_RACK)),
            Livello.TURNO,
            ClassificationSystem.WINS,
        ) == (V(Criterio.DIFFERENZA_RACK), V(Criterio.SORTEGGIO))

    def test_il_principale_non_e_ammesso_come_spareggio(self):
        assert Criterio.VITTORIE not in criteri_ammessi(
            Livello.GARA, ClassificationSystem.WINS
        )
        assert Criterio.RACK_VINTI not in criteri_ammessi(
            Livello.GARA, ClassificationSystem.RACK
        )

    def test_la_frase_del_regolamento(self):
        frase = descrivi_catena(
            (
                V(Criterio.SCONTRI_DIRETTI),
                V(Criterio.DIFFERENZA_RACK),
                V(Criterio.SORTEGGIO),
            ),
            ClassificationSystem.WINS,
        )
        assert frase == (
            "A pari vittorie conta lo scontro diretto, poi la differenza triangoli, "
            "poi il sorteggio."
        )


class TestCateneDiDefault:
    """Le catene di default decise il 2026-10-07 (ADR-078)."""

    @pytest.mark.parametrize(
        "livello, sistema, attesa",
        [
            (
                Livello.TURNO,
                ClassificationSystem.WINS,
                ["differenza_rack", "posizione_precedente", "sorteggio"],
            ),
            (
                Livello.TURNO,
                ClassificationSystem.RACK,
                ["posizione_precedente", "sorteggio"],
            ),
            (Livello.GARA, ClassificationSystem.WINS, ["differenza_rack", "ssr:3"]),
            (Livello.GARA, ClassificationSystem.RACK, ["ssr:3"]),
            (
                Livello.CAMPIONATO,
                ClassificationSystem.WINS,
                ["differenza_rack", "ssr", "posizione_precedente", "sorteggio"],
            ),
            (
                Livello.CAMPIONATO,
                ClassificationSystem.RACK,
                ["ssr", "posizione_precedente", "sorteggio"],
            ),
        ],
    )
    def test_default(self, livello, sistema, attesa):
        assert serializza_catena(catena_di_default(livello, sistema)) == attesa

    def test_la_gara_senza_spareggio_non_ha_lo_ssr(self):
        assert serializza_catena(
            catena_di_default(Livello.GARA, ClassificationSystem.WINS, ssr_fino_al=None)
        ) == ["differenza_rack"]

    def test_lo_ssr_della_gara_segue_il_posto(self):
        assert serializza_catena(
            catena_di_default(Livello.GARA, ClassificationSystem.RACK, ssr_fino_al=2)
        ) == ["ssr:2"]
