"""Lo schermo in sala, senza database (canvas 3.10).

`models/competition/schermo_sala.py` decide cosa si proietta a partire da
partite, righe di classifica e tavoli: qui si fissano le caselle dei tavoli,
le colonne della classifica, il turno prima e la fase per ogni stato; per le
gare a tabellone (issue #352) quali nodi vanno nella colonna laterale, i
vincenti e i ripescati del doppio KO, il podio e le bande a gara conclusa.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import pytest

from models.competition.schermo_sala import (
    FaseSchermo,
    StatoNodo,
    fase_schermo,
    schermo_sala,
)
from models.competition.tabellone_view import NomeRound
from models.matchmaking.bracket import (
    BRACKET_LOSERS,
    BRACKET_WINNERS,
    standard_bracket_order,
)
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
        (GaraStatus.PLAYING.value, "double_knockout", FaseSchermo.TABELLONE),
        (GaraStatus.AWAITING_SSR.value, "amalfi", FaseSchermo.SPAREGGIO),
        (GaraStatus.COMPLETED.value, "amalfi", FaseSchermo.CONCLUSA),
        # Un tabellone concluso ha podio e bande, non piu' il turno in corso.
        (GaraStatus.COMPLETED.value, "direct_elimination", FaseSchermo.CONCLUSA),
        (GaraStatus.COMPLETED.value, "double_knockout", FaseSchermo.CONCLUSA),
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


# ── Le gare a tabellone (issue #352) ──────────────────────────────────────


@dataclass
class U:
    id: int
    username: str


@dataclass
class B:
    """Un match con le coordinate del tabellone."""

    id: int
    bracket_type: str
    bracket_round: int
    bracket_slot: int
    round_number: int
    player1: Optional[U]
    player2: Optional[U] = None
    status: str = PENDING
    winner_id: Optional[int] = None
    is_bye: bool = False
    bracket_group: Optional[int] = None
    table_assignment: Optional[str] = None
    player1_score: int = 0
    player2_score: int = 0
    is_at_distance: bool = False
    is_player_validated: bool = False
    is_trio: bool = False
    trio_match: None = None

    @property
    def player1_id(self):
        return self.player1.id if self.player1 else None

    @property
    def player2_id(self):
        return self.player2.id if self.player2 else None


def _primo_turno(n, taglia):
    """Il turno 1 come lo sorteggia la strategia: seed sugli slot canonici."""
    utenti = {i: U(i, f"g{i}") for i in range(1, n + 1)}
    ordine = standard_bracket_order(taglia)
    return [
        B(
            j + 1,
            BRACKET_WINNERS,
            1,
            j,
            1,
            utenti[ordine[2 * j]],
            utenti[ordine[2 * j + 1]],
        )
        for j in range(taglia // 2)
    ]


def _chiudi(m):
    """Vince `player1`, 2-0."""
    m.status = CHIUSA
    m.player1_score, m.player2_score = 2, 0
    m.winner_id = m.player1_id


def _gara_tab(strategy="direct_elimination", *, finalina=False, **kw):
    gara = _gara(strategy=strategy, **kw)
    gara.third_place_match = finalina
    return gara


def _colonne(schermo):
    return [
        [
            (
                ramo.key,
                [
                    (c.nome.chiave, c.nome.numero, len(c.nodi), c.attuale)
                    for c in ramo.colonne
                ],
            )
            for ramo in lavagna.rami
        ]
        for lavagna in schermo.tabellone.lavagne
    ]


def test_eliminazione_da_8_il_turno_e_quello_dopo_senza_la_finale():
    partite = _primo_turno(8, 8)
    partite[0].table_assignment = "1"
    partite[0].status = PLAYING
    partite[0].player1_score = 1
    s = schermo_sala(_gara_tab(turno=1), partite, [], ["1", "2"], 8)

    assert s.fase == FaseSchermo.TABELLONE
    assert _colonne(s) == [
        [("winners", [("quarti", None, 4, True), ("semifinali", None, 2, False)])]
    ]
    assert s.tabellone.nomi_turno == (NomeRound("quarti"),)
    # Le semifinali non sono nate: nodi vuoti che dicono da dove arriva chi.
    quarti, semi = s.tabellone.lavagne[0].rami[0].colonne
    assert all(n.stato == StatoNodo.VUOTO for n in semi.nodi)
    # Chi arriva esce da un quarto gia' nato: «chi vince» e i due nomi, e il
    # tavolo solo per il quarto che si sta giocando.
    primo, secondo = semi.nodi[0].lati
    assert (primo.esito, primo.da, primo.tavolo) == (
        "vincitore",
        (partite[0].player1.username, partite[0].player2.username),
        "1",
    )
    assert (secondo.esito, secondo.da, secondo.tavolo) == (
        "vincitore",
        (partite[1].player1.username, partite[1].player2.username),
        None,
    )
    assert primo.nome is None and primo.posto is None
    # Quattro righe, un ramo solo: c'e' spazio per i due nomi.
    assert not s.tabellone.stretto
    # Il quarto al tavolo 1 e' in corso col punteggio; lo 0-0 degli altri no.
    assert quarti.nodi[0].stato == StatoNodo.IN_CORSO
    assert quarti.nodi[0].lati[0].punti == 1
    assert quarti.nodi[1].stato == StatoNodo.DA_GIOCARE
    assert quarti.nodi[1].lati[0].punti is None
    # Le caselle dei tavoli portano il nome del round, anche la prossima.
    uno, due = s.tavoli
    assert uno.round == NomeRound("quarti") and not uno.libero
    assert due.libero and due.prossima and due.round == NomeRound("quarti")
    # Nel tabellone non c'e' il turno prima delle gare a turni.
    assert s.turno_prima == [] and s.numero_turno_prima is None


def test_eliminazione_da_16_ottavi_e_quarti():
    s = schermo_sala(_gara_tab(turno=1, turni=4), _primo_turno(16, 16), [], ["1"], 16)

    assert _colonne(s) == [
        [("winners", [("ottavi", None, 8, True), ("quarti", None, 4, False)])]
    ]
    assert s.tabellone.righe == 8


def test_fra_un_turno_e_l_altro_il_turno_dopo_ha_i_vincitori():
    partite = _primo_turno(8, 8)
    for m in partite:
        _chiudi(m)
    s = schermo_sala(_gara_tab(turno=1), partite, [], ["1"], 8)

    assert s.turno_concluso
    semi = s.tabellone.lavagne[0].rami[0].colonne[1].nodi
    assert [lato.nome for lato in semi[0].lati] == [
        partite[0].player1.username,
        partite[1].player1.username,
    ]
    assert all(t.libero and t.prossima is None for t in s.tavoli)


def test_con_la_finalina_finale_e_finalina_stanno_nel_turno_dopo():
    s = schermo_sala(
        _gara_tab(turno=1, turni=2, finalina=True), _primo_turno(4, 4), [], ["1"], 4
    )

    (ramo,) = s.tabellone.lavagne[0].rami
    assert [(c.nome.chiave, c.attuale) for c in ramo.colonne] == [
        ("semifinali", True),
        ("finale", False),
        ("finalina", False),
    ]


def test_doppio_ko_vincenti_sopra_e_ripescati_sotto():
    w1 = _primo_turno(8, 8)
    for m in w1:
        _chiudi(m)
    vin = [m.player1 for m in w1]
    per = [m.player2 for m in w1]
    w2 = [
        B(11, BRACKET_WINNERS, 2, 0, 2, vin[0], vin[1], PLAYING, table_assignment="1"),
        B(12, BRACKET_WINNERS, 2, 1, 2, vin[2], vin[3]),
    ]
    l1 = [
        B(21, BRACKET_LOSERS, 1, 0, 2, per[0], per[1], PLAYING, table_assignment="2"),
        B(22, BRACKET_LOSERS, 1, 1, 2, per[2], per[3]),
    ]
    s = schermo_sala(
        _gara_tab("double_knockout", turno=2, turni=7),
        w1 + w2 + l1,
        [],
        ["1", "2"],
        8,
    )

    assert _colonne(s) == [
        [
            ("winners", [("turno", 2, 2, True), ("turno", 3, 1, False)]),
            ("losers", [("recupero", 1, 2, True), ("recupero", 2, 2, False)]),
        ]
    ]
    assert s.tabellone.lavagne[0].con_ripescati
    # Due rami: poco spazio, un posto che esce da una partita al tavolo si
    # dice col tavolo. Il recupero 2, slot 0, riceve chi vince il recupero 1
    # al tavolo 2 e chi perde la seconda partita dei vincenti, senza tavolo.
    assert s.tabellone.stretto
    recupero2 = s.tabellone.lavagne[0].rami[1].colonne[1].nodi[0]
    assert [(lato.esito, lato.da, lato.tavolo) for lato in recupero2.lati] == [
        ("vincitore", (per[0].username, per[1].username), "2"),
        ("perdente", (vin[2].username, vin[3].username), None),
    ]
    assert s.tabellone.nomi_turno == (
        NomeRound("vincenti", 2),
        NomeRound("recupero", 1),
    )
    # Sul tavolo non c'e' la colonna intorno: il ramo si dice per esteso.
    uno, due = s.tavoli
    assert uno.round == NomeRound("vincenti", 2)
    assert due.round == NomeRound("recupero", 1)


def test_a_gara_conclusa_podio_e_bande_dalle_posizioni():
    semi = _primo_turno(4, 4)
    for m in semi:
        _chiudi(m)
    finale = B(9, BRACKET_WINNERS, 2, 0, 2, semi[0].player1, semi[1].player1)
    _chiudi(finale)
    campione, secondo = finale.player1, finale.player2
    terzi = [semi[0].player2, semi[1].player2]
    posizioni = {campione.id: 1, secondo.id: 2, terzi[0].id: 3, terzi[1].id: 3}

    s = schermo_sala(
        _gara_tab(status=GaraStatus.COMPLETED.value, turno=2, turni=2),
        semi + [finale],
        [],
        ["1"],
        4,
        posizioni=posizioni,
    )

    assert s.fase == FaseSchermo.CONCLUSA
    assert s.tabellone is None and s.tavoli == []
    podio = [[r.user.username for r in gradino] for gradino in s.podio]
    assert podio[:2] == [[campione.username], [secondo.username]]
    # Senza finalina i due semifinalisti sconfitti stanno sullo stesso gradino.
    assert sorted(podio[2]) == sorted(u.username for u in terzi)
    assert [(b.posizione, b.ultima) for b in s.bande] == [(1, 1), (2, 2), (3, 4)]


def test_a_gara_conclusa_senza_posizioni_resta_la_classifica():
    s = schermo_sala(
        _gara_tab(status=GaraStatus.COMPLETED.value, turno=1, turni=2),
        _primo_turno(4, 4),
        [_riga(1, "rossi")],
        ["1"],
        4,
    )
    assert s.bande == [] and s.podio == [] and len(s.classifica) == 1
