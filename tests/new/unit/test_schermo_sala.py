"""Lo schermo in sala, senza database (canvas 3.10).

`models/competition/schermo_sala.py` decide cosa si proietta a partire da
partite, righe di classifica e tavoli: qui si fissano le caselle dei tavoli,
le colonne della classifica, il turno prima e la fase per ogni stato.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.competition.schermo_sala import FaseSchermo, fase_schermo, schermo_sala
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


def _g(nome):
    return SimpleNamespace(username=nome)


def _m(
    id_,
    turno,
    status,
    *,
    tavolo=None,
    s1=0,
    s2=0,
    distanza=False,
    bye=False,
    p1="a",
    p2="b",
):
    return SimpleNamespace(
        id=id_,
        round_number=turno,
        status=status,
        table_assignment=tavolo,
        player1_score=s1,
        player2_score=s2,
        is_at_distance=distanza,
        is_player_validated=False,
        is_bye=bye,
        is_trio=False,
        trio_match=None,
        player1=_g(p1),
        player2=_g(p2) if not bye else None,
    )


def _gara(status=GaraStatus.PLAYING.value, strategy="amalfi", turno=2, turni=3):
    return SimpleNamespace(
        status=status,
        matchmaking_strategy=strategy,
        display_round=turno,
        rounds_count=turni,
    )


def _riga(pos, nome, vinte=0, diff=0, racks=None, turno=1, rack=False):
    return SimpleNamespace(
        position=pos,
        user=_g(nome),
        matches_won=vinte,
        rack_difference=diff,
        racks_won=racks,
        round_number=turno,
        is_rack_ranking=rack,
        ranking_rack_value=(racks if rack else diff),
        total_racks_value=racks or 0,
    )


PLAYING = MatchStatus.PLAYING.value
PENDING = MatchStatus.PENDING.value
CHIUSA = MatchStatus.CLOSED_UNILATERALLY.value


@pytest.mark.parametrize(
    "status, strategy, fase",
    [
        (GaraStatus.SETUP.value, "amalfi", FaseSchermo.ATTESA),
        (GaraStatus.INSCRIPTION.value, "direct_elimination", FaseSchermo.ATTESA),
        (GaraStatus.PLAYING.value, "amalfi", FaseSchermo.GIOCO),
        (GaraStatus.PLAYING.value, "direct_elimination", FaseSchermo.TABELLONE),
        (GaraStatus.AWAITING_SSR.value, "amalfi", FaseSchermo.SPAREGGIO),
        (GaraStatus.COMPLETED.value, "amalfi", FaseSchermo.CONCLUSA),
    ],
)
def test_la_fase_segue_lo_stato_e_il_formato(status, strategy, fase):
    assert fase_schermo(_gara(status=status, strategy=strategy)) == fase


def test_le_caselle_dei_tavoli_dicono_chi_gioca_e_la_prossima():
    partite = [
        _m(1, 2, PLAYING, tavolo="1", s1=4, s2=2, p1="rossi", p2="verdi"),
        _m(2, 2, PLAYING, tavolo="3", s1=5, s2=1, distanza=True, p1="galli", p2="neri"),
        _m(4, 2, PENDING, p1="conti", p2="marini"),
        _m(3, 2, PENDING, p1="sala", p2="costa"),
        _m(9, 1, CHIUSA, s1=5, s2=3, p1="x", p2="y"),
    ]
    s = schermo_sala(_gara(), partite, [], ["1", "2", "3", "4"], 8)
    uno, due, tre, quattro = s.tavoli
    assert [(lato.nome, lato.punti, lato.avanti) for lato in uno.lati] == [
        ("rossi", 4, True),
        ("verdi", 2, False),
    ]
    assert not uno.alla_distanza and tre.alla_distanza
    # Le partite in attesa vanno ai tavoli liberi nell'ordine in cui sono nate.
    assert due.libero and due.prossima == "sala – costa"
    assert quattro.libero and quattro.prossima == "conti – marini"


def test_la_classifica_a_vittorie_scrive_la_differenza_col_segno():
    righe = [_riga(1, "rossi", 2, 4), _riga(2, "verdi", 1, 0), _riga(3, "neri", 0, -4)]
    s = schermo_sala(_gara(), [], righe, [], 8)
    assert [(r.posizione, r.nome, r.valore, r.secondo) for r in s.classifica] == [
        (1, "rossi", 2, "+4"),
        (2, "verdi", 1, "0"),
        (3, "neri", 0, "-4"),
    ]
    assert not s.rack and s.turno_classifica == 1


def test_la_classifica_a_rack_scrive_vinti_e_persi():
    s = schermo_sala(
        _gara(), [], [_riga(1, "rossi", diff=4, racks=9, rack=True)], [], 8
    )
    assert s.rack
    assert (s.classifica[0].valore, s.classifica[0].secondo) == (9, "5")


def test_con_la_formula_casuale_la_classifica_e_complessiva():
    s = schermo_sala(_gara(strategy="random"), [], [_riga(1, "rossi", turno=3)], [], 8)
    assert s.turno_classifica == 0


def test_il_turno_prima_e_l_ultimo_chiuso_e_senza_x():
    partite = [
        _m(1, 1, CHIUSA, s1=5, s2=3, p1="rossi", p2="verdi"),
        _m(2, 1, CHIUSA, bye=True, p1="neri"),
        _m(3, 2, PLAYING, tavolo="1", s1=1, s2=0),
    ]
    s = schermo_sala(_gara(turno=2), partite, [], ["1"], 3)
    assert s.numero_turno_prima == 1
    assert [(p.p1, p.s1, p.p2, p.s2, p.vince1) for p in s.turno_prima] == [
        ("rossi", 5, "verdi", 3, True)
    ]


def test_a_turno_concluso_il_turno_prima_e_quello_stesso():
    partite = [
        _m(1, 1, CHIUSA, s1=5, s2=3),
        _m(2, 2, CHIUSA, s1=2, s2=5, p1="galli", p2="sala"),
    ]
    s = schermo_sala(_gara(turno=2), partite, [], ["1"], 2)
    assert s.numero_turno_prima == 2
    assert s.turno_prima[0].vince2
    assert all(t.libero and t.prossima is None for t in s.tavoli)


def test_fuori_dal_gioco_non_ci_sono_tavoli():
    partite = [_m(1, 1, PLAYING, tavolo="1", s1=1)]
    for status in (GaraStatus.INSCRIPTION.value, GaraStatus.COMPLETED.value):
        s = schermo_sala(_gara(status=status), partite, [], ["1"], 4)
        assert s.tavoli == [] and s.turno_prima == []
