"""Le forme della card del direttore: trio, partita a set, X con esercizio.

`direttore_view` risponde senza database: qui le partite sono oggetti finti
con gli attributi che la vista legge.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.competition.direttore_view import (
    FormaPartita,
    StatoPartita,
    StatoProvaX,
    forma_partita,
    scheda_prova_x,
    scheda_set,
    scheda_trio,
    stato_partita,
)
from models.match.trio_config import TrioConfig
from models.status_enum import MatchStatus

pytestmark = pytest.mark.unit


def _partita(**kw):
    base = dict(
        id=1,
        is_bye=False,
        is_trio=False,
        trio_match=None,
        is_multi_set=False,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
        player1_score=0,
        player2_score=0,
        is_at_distance=False,
        is_player_validated=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _trio(punti=(0, 0, 0), distanza=4, attesa=False, vincitore=None):
    config = TrioConfig(distance=distanza)
    giocatori = [SimpleNamespace(username=n) for n in ("Anna", "Bruno", "Carla")]
    return SimpleNamespace(
        id=7,
        trio_config=config,
        player_racks_list=list(punti),
        player_ids=[11, 12, 13],
        player1=giocatori[0],
        player2=giocatori[1],
        player3=giocatori[2],
        player3_id=13,
        awaiting_confirmation=attesa,
        winner_id=vincitore,
    )


# ── Stati ─────────────────────────────────────────────────────────────────────


def test_il_trio_giocato_fino_in_fondo_senza_firme_e_da_validare():
    trio = _trio((2, 1, 0), distanza=2, attesa=True, vincitore=11)
    partita = _partita(is_trio=True, trio_match=trio, is_at_distance=True)
    assert forma_partita(partita) == FormaPartita.TRIO
    assert stato_partita(partita) == StatoPartita.DA_VALIDARE


def test_il_trio_a_meta_e_in_corso():
    trio = _trio((1, 0, 0))
    partita = _partita(is_trio=True, trio_match=trio)
    assert stato_partita(partita) == StatoPartita.IN_CORSO


def test_la_partita_a_set_non_e_mai_da_validare():
    """Ogni set si chiude alla sua distanza e la partita ai set: non ci sono
    firme da raccogliere, anche se `is_at_distance` dicesse il contrario."""
    partita = _partita(is_multi_set=True, is_at_distance=True, player1_score=1)
    assert forma_partita(partita) == FormaPartita.SET
    assert stato_partita(partita) == StatoPartita.IN_CORSO


def test_la_x_con_esercizio_resta_una_x():
    partita = _partita(is_bye=True, is_x_with_challenge=True)
    assert forma_partita(partita) == FormaPartita.X_ESERCIZIO
    assert stato_partita(partita) == StatoPartita.X


# ── Trio ──────────────────────────────────────────────────────────────────────


def test_la_scheda_del_trio_dice_limiti_e_piu_ammessi():
    partita = _partita(is_trio=True, trio_match=_trio((0, 0, 0), distanza=5))
    scheda = scheda_trio(partita)
    assert scheda is not None
    assert scheda.nomi == ("Anna", "Bruno", "Carla")
    assert (scheda.gironi, scheda.massimo, scheda.totale) == (2, 4, 6)
    # Il primo triangolo e' fra il primo e il secondo: il terzo aspetta.
    assert scheda.piu == (True, True, False)


def test_a_trio_finito_nessun_piu_resta_acceso():
    partita = _partita(is_trio=True, trio_match=_trio((2, 1, 0), distanza=3))
    scheda = scheda_trio(partita)
    assert scheda is not None
    assert scheda.piu == (False, False, False)


# ── Set ───────────────────────────────────────────────────────────────────────


def _set(numero, p1, p2, status, distanza=4):
    return SimpleNamespace(
        set_number=numero,
        player1_racks=p1,
        player2_racks=p2,
        status=status,
        distance=distanza,
        is_race_to=True,
    )


def _distanza_set(sets=2):
    return SimpleNamespace(
        get_winning_sets=lambda: sets,
        is_race_to_sets=True,
        racks=4,
        is_race_to_racks=True,
    )


def test_la_scheda_del_set_mostra_il_set_in_corso():
    chiuso = _set(1, 4, 2, MatchStatus.CLOSED_UNILATERALLY.value)
    corrente = _set(2, 1, 3, MatchStatus.PLAYING.value)
    partita = _partita(
        is_multi_set=True,
        sets=[corrente, chiuso],
        player1_score=1,
        distance_config=_distanza_set(),
    )
    scheda = scheda_set(partita)
    assert scheda is not None
    assert scheda.set_vinti == (1, 0)
    assert (scheda.numero, scheda.punti, scheda.distanza) == (2, (1, 3), 4)
    assert scheda.prossimo is None
    assert scheda.chiusi == ((1, 4, 2),)


def test_a_set_chiuso_si_propone_il_prossimo():
    chiuso = _set(1, 4, 2, MatchStatus.CLOSED_UNILATERALLY.value)
    partita = _partita(
        is_multi_set=True,
        sets=[chiuso],
        player1_score=1,
        distance_config=_distanza_set(),
    )
    scheda = scheda_set(partita)
    assert scheda is not None
    assert not scheda.in_corso
    assert scheda.prossimo == 2


def test_senza_set_si_comincia_dal_primo():
    partita = _partita(is_multi_set=True, sets=[], distance_config=_distanza_set())
    scheda = scheda_set(partita)
    assert scheda is not None
    assert scheda.prossimo == 1


# ── X con esercizio ───────────────────────────────────────────────────────────


def _x(ponte, distanza=3, punti=0):
    return _partita(
        is_bye=True,
        is_x_with_challenge=True,
        bye_challenge=ponte,
        effective_distance=distanza,
        player1_score=punti,
        gara=SimpleNamespace(x_challenge=None),
    )


def test_la_prova_non_registrata_parte_da_zero_col_massimo_del_turno():
    scheda = scheda_prova_x(_x(None, distanza=3))
    assert scheda is not None
    assert (scheda.stato, scheda.punteggio, scheda.massimo) == (
        StatoProvaX.DA_REGISTRARE,
        0,
        3,
    )


def test_la_prova_dichiarata_parte_dal_punteggio_del_giocatore():
    tentativo = SimpleNamespace(score=2, challenge=None)
    ponte = SimpleNamespace(
        is_validated=False, is_completed=True, challenge_attempt=tentativo
    )
    scheda = scheda_prova_x(_x(ponte))
    assert scheda is not None
    assert (scheda.stato, scheda.punteggio) == (StatoProvaX.DICHIARATA, 2)


def test_la_prova_convalidata_e_in_sola_lettura():
    tentativo = SimpleNamespace(score=3, challenge=None)
    ponte = SimpleNamespace(
        is_validated=True, is_completed=True, challenge_attempt=tentativo
    )
    scheda = scheda_prova_x(_x(ponte, punti=3))
    assert scheda is not None
    assert (scheda.stato, scheda.punteggio) == (StatoProvaX.CONVALIDATA, 3)
