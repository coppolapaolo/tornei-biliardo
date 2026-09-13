"""Gli esercizi fra i turni sulla pagina del direttore, senza database.

`direttore_view.esercizi_fra_i_turni` decide quali esercizi si registrano
adesso — quelli il cui turno e' **concluso**, perche' la regola e' «dopo il
turno N» — e, per ognuno, a che punto e' ogni giocatore: tentativi fatti sul
massimo, il migliore punteggio o l'esito.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.competition.direttore_view import (
    esercizi_fra_i_turni,
    turni_conclusi,
)
from models.status_enum import MatchStatus

pytestmark = pytest.mark.unit


def _partita(turno, status, *, is_bye=False):
    return SimpleNamespace(
        round_number=turno,
        status=status,
        is_bye=is_bye,
        table_assignment=None,
        trio_match=None,
        trio_matches=[],
        is_multi_set=False,
        player1_score=0,
        player2_score=0,
    )


def _esercizio(gc_id, turno, *, a_esito=False, massimo=None, tentativi=2):
    sfida = SimpleNamespace(
        pass_fail_only=a_esito,
        max_score=massimo,
        get_display_name=lambda: f"Esercizio {gc_id}",
    )
    return SimpleNamespace(
        id=gc_id, round_number=turno, max_attempts=tentativi, challenge=sfida
    )


GIOCATORI = [(1, "Anna"), (2, "Bruno"), (3, "Carla")]


def test_un_turno_e_concluso_quando_ogni_sua_partita_lo_e():
    chiusa = MatchStatus.CLOSED_UNILATERALLY.value
    partite = [
        _partita(1, chiusa),
        _partita(1, MatchStatus.CONFIRMED_BY_BOTH.value),
        _partita(1, MatchStatus.PLAYING.value, is_bye=True),
        _partita(2, chiusa),
        _partita(2, MatchStatus.PLAYING.value),
    ]
    assert turni_conclusi(partite) == {1}


def test_un_turno_senza_partite_non_e_concluso():
    assert turni_conclusi([]) == set()


def test_l_esercizio_si_registra_solo_dopo_il_suo_turno():
    esercizi = esercizi_fra_i_turni(
        [_esercizio(10, 1), _esercizio(11, 2)],
        turni_chiusi={1},
        giocatori=GIOCATORI,
        tentativi={},
    )
    dopo_uno, dopo_due = esercizi
    assert (dopo_uno.turno, dopo_uno.dovuto) == (1, True)
    assert [g.nome for g in dopo_uno.giocatori] == ["Anna", "Bruno", "Carla"]
    # Il turno 2 non e' ancora chiuso: l'esercizio c'e', ma non si registra.
    assert (dopo_due.turno, dopo_due.dovuto) == (2, False)
    assert dopo_due.giocatori == ()


def test_tentativi_fatti_migliore_e_chi_non_puo_piu_tentare():
    (esercizio,) = esercizi_fra_i_turni(
        [_esercizio(10, 1, massimo=15, tentativi=2)],
        turni_chiusi={1},
        giocatori=GIOCATORI,
        tentativi={(10, 1): [(4, None), (9, None)], (10, 2): [(6, None)]},
    )
    anna, bruno, carla = esercizio.giocatori
    assert (anna.fatti, anna.massimo, anna.migliore, anna.puo_tentare) == (
        2,
        2,
        9,
        False,
    )
    assert (bruno.fatti, bruno.migliore, bruno.puo_tentare) == (1, 6, True)
    assert (carla.fatti, carla.migliore, carla.puo_tentare) == (0, None, True)
    assert esercizio.punteggio_massimo == 15
    assert esercizio.da_registrare == 1


def test_a_esito_conta_se_almeno_un_tentativo_e_riuscito():
    (esercizio,) = esercizi_fra_i_turni(
        [_esercizio(10, 1, a_esito=True)],
        turni_chiusi={1},
        giocatori=GIOCATORI,
        tentativi={(10, 1): [(0, False), (1, True)], (10, 2): [(0, False)]},
    )
    anna, bruno, carla = esercizio.giocatori
    assert esercizio.a_esito is True
    assert (anna.riuscito, bruno.riuscito, carla.riuscito) == (True, False, None)
