"""Una domanda sola: questa gara ha un tabellone da mostrare? (ADR-081)

`models/competition/tabellone_della_gara.py` risponde per le pagine — del
direttore, pubblica, del tabellone, lo schermo in sala — al posto dei
controlli sulla strategia sparsi fra route e template. Test puri: la gara e
le partite sono oggetti finti.

* Eliminazione diretta e doppio KO: il tabellone c'è sempre, come prima.
* Girone all'italiana col tabellone dopo i gironi: mentre si giocano i
  gironi no, dal sorteggio del tabellone sì; con il girone unico mai.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import pytest

from models.competition.tabellone_della_gara import (
    NESSUN_TABELLONE,
    FaseDellaGara,
    albero_della_gara,
    tabellone_della_gara,
)
from models.competition.tabellone_view import NomeRound, costruisci_tabellone
from models.matchmaking.bracket import BRACKET_THIRD_PLACE, BRACKET_WINNERS
from models.status_enum import MatchStatus

pytestmark = pytest.mark.unit

IN_CORSO = MatchStatus.PLAYING.value


@dataclass
class U:
    id: int
    username: str


@dataclass
class M:
    id: int
    round_number: int
    player1: Optional[U]
    player2: Optional[U] = None
    bracket_type: Optional[str] = None
    bracket_round: Optional[int] = None
    bracket_slot: Optional[int] = None
    bracket_group: Optional[int] = None
    status: str = IN_CORSO
    winner_id: Optional[int] = None
    is_bye: bool = False

    @property
    def player1_id(self):
        return self.player1.id if self.player1 else None

    @property
    def player2_id(self):
        return self.player2.id if self.player2 else None


def _gara(strategia: str, *, tabellone: bool = False, finalina: bool = False):
    return SimpleNamespace(
        matchmaking_strategy=strategia,
        ha_tabellone_finale=tabellone,
        third_place_match=finalina,
    )


def _gironi(turni: int = 3, gironi: int = 2):
    """Le partite dei gironi: girone sì, coordinate del tabellone no."""
    utenti = [U(i, f"g{i}") for i in range(1, 9)]
    partite = []
    for r in range(1, turni + 1):
        for g in range(gironi):
            partite.append(
                M(
                    len(partite) + 1,
                    r,
                    utenti[2 * g],
                    utenti[2 * g + 1],
                    bracket_group=g,
                )
            )
    return partite


def _semifinali(turno: int = 4):
    a, b, c, d = (U(i, f"s{i}") for i in range(11, 15))
    return [
        M(101, turno, a, b, BRACKET_WINNERS, 1, 0),
        M(102, turno, c, d, BRACKET_WINNERS, 1, 1),
    ]


class TestTabelloneDiFormato:
    @pytest.mark.parametrize("strategia", ["direct_elimination", "double_knockout"])
    def test_c_e_sempre_anche_prima_del_sorteggio(self, strategia):
        t = tabellone_della_gara(_gara(strategia), [])
        assert t.di_formato and t.da_mostrare
        assert t.fase is FaseDellaGara.TABELLONE
        assert t.turni_prima == 0 and not t.dopo_i_gironi

    @pytest.mark.parametrize("strategia", ["amalfi", "random"])
    def test_le_gare_a_turni_non_ne_hanno(self, strategia):
        assert tabellone_della_gara(_gara(strategia), _gironi()) == NESSUN_TABELLONE


class TestTabelloneDopoIGironi:
    def test_mentre_si_giocano_i_gironi_non_si_mostra(self):
        t = tabellone_della_gara(_gara("round_robin", tabellone=True), _gironi())
        assert t.dopo_i_gironi and t.nei_gironi
        assert t.fase is FaseDellaGara.GIRONI
        assert not t.da_mostrare

    def test_dal_sorteggio_si_mostra_e_comincia_dopo_i_gironi(self):
        partite = _gironi(3) + _semifinali(4)
        t = tabellone_della_gara(_gara("round_robin", tabellone=True), partite)
        assert t.da_mostrare and t.dopo_i_gironi and not t.di_formato
        assert t.fase is FaseDellaGara.TABELLONE
        assert t.turni_prima == 3

    def test_col_girone_unico_non_c_e_niente(self):
        # Partito con un girone solo: le partite non hanno girone, e il
        # tabellone non si gioca (ADR-081, punto 2).
        partite = [M(i, 1, U(i, "a"), U(i + 10, "b")) for i in range(1, 4)]
        t = tabellone_della_gara(_gara("round_robin", tabellone=True), partite)
        assert t == NESSUN_TABELLONE

    def test_senza_fase_finale_i_gironi_restano_gironi(self):
        t = tabellone_della_gara(_gara("round_robin", tabellone=False), _gironi())
        assert t == NESSUN_TABELLONE

    def test_prima_dell_avvio_non_c_e_niente(self):
        t = tabellone_della_gara(_gara("round_robin", tabellone=True), [])
        assert t == NESSUN_TABELLONE


class TestAlbero:
    def test_i_turni_del_tabellone_hanno_il_loro_nome_dopo_i_gironi(self):
        partite = _gironi(3) + _semifinali(4)
        albero = albero_della_gara(
            _gara("round_robin", tabellone=True, finalina=True), partite
        )
        assert albero is not None
        nomi = albero.nomi_turni()
        assert nomi[4] == [NomeRound("semifinali")]
        assert nomi[5] == [NomeRound("finale")]
        # Le partite dei gironi non sono nodi del tabellone.
        assert set(nomi) == {4, 5}
        # La finalina sta nel turno della finale.
        finalina = [n for n in albero.nodi if n.bracket_type == BRACKET_THIRD_PLACE]
        assert len(finalina) == 1 and finalina[0].turno == 5

    def test_nei_gironi_non_c_e_albero(self):
        assert (
            albero_della_gara(_gara("round_robin", tabellone=True), _gironi()) is None
        )

    def test_un_tabellone_da_sorteggiare_dice_gia_i_nomi(self):
        albero = costruisci_tabellone(
            [], strategy="round_robin", turni_prima=3, taglia_da_sorteggiare=4
        )
        assert albero is not None
        assert albero.nomi_turni() == {
            4: [NomeRound("semifinali")],
            5: [NomeRound("finale")],
        }

    def test_due_qualificati_la_sola_finale(self):
        a, b = U(1, "a"), U(2, "b")
        albero = albero_della_gara(
            _gara("round_robin", tabellone=True),
            _gironi(3) + [M(50, 4, a, b, BRACKET_WINNERS, 1, 0)],
        )
        assert albero is not None
        assert albero.nomi_turni() == {4: [NomeRound("finale")]}

    def test_il_tabellone_di_formato_resta_quello_di_sempre(self):
        semi = _semifinali(1)
        gara = _gara("direct_elimination")
        prima = costruisci_tabellone(semi, strategy="direct_elimination")
        dopo = albero_della_gara(gara, semi)
        assert prima is not None and dopo is not None
        assert prima.nomi_turni() == dopo.nomi_turni()
        assert [(n.chiave, n.turno) for n in prima.nodi] == [
            (n.chiave, n.turno) for n in dopo.nodi
        ]
