"""La striscia di fase della pagina gara del direttore (canvas, decisione 2).

`models/competition/direttore_view.py` risponde senza database: la fase da
`Gara.status`, le tacche della striscia — con lo spareggio solo nelle gare
che ce l'hanno — e i conteggi del turno per la card scura del gioco.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.competition.direttore_view import (
    FaseGara,
    StatoPartita,
    StatoTacca,
    conteggi_turno,
    fase_della_gara,
    partite_del_turno,
    prima_in_attesa,
    spareggio_nella_striscia,
    stato_partita,
    striscia,
    tavoli_del_turno,
)
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "status, fase",
    [
        (GaraStatus.SETUP.value, FaseGara.PREPARAZIONE),
        (GaraStatus.INSCRIPTION.value, FaseGara.ISCRIZIONI),
        (GaraStatus.PLAYING.value, FaseGara.GIOCO),
        (GaraStatus.AWAITING_SSR.value, FaseGara.SPAREGGIO),
        (GaraStatus.COMPLETED.value, FaseGara.CONCLUSA),
        (GaraStatus.CANCELLED.value, FaseGara.CONCLUSA),
    ],
)
def test_ogni_stato_persistito_ha_la_sua_fase(status, fase):
    assert fase_della_gara(status) == fase


def test_uno_stato_ignoto_vale_preparazione():
    assert fase_della_gara("boh") == FaseGara.PREPARAZIONE


def test_la_striscia_senza_spareggio_ha_quattro_tacche_e_segna_le_fatte():
    tacche = striscia(FaseGara.GIOCO, con_spareggio=False)
    assert [t.fase for t in tacche] == [
        FaseGara.PREPARAZIONE,
        FaseGara.ISCRIZIONI,
        FaseGara.GIOCO,
        FaseGara.CONCLUSA,
    ]
    assert [t.stato for t in tacche] == [
        StatoTacca.FATTA,
        StatoTacca.FATTA,
        StatoTacca.ATTIVA,
        StatoTacca.DA_FARE,
    ]


def test_la_tacca_dello_spareggio_sta_fra_il_gioco_e_la_chiusura():
    tacche = striscia(FaseGara.SPAREGGIO, con_spareggio=True)
    assert [t.fase for t in tacche][2:] == [
        FaseGara.GIOCO,
        FaseGara.SPAREGGIO,
        FaseGara.CONCLUSA,
    ]
    assert tacche[3].stato == StatoTacca.ATTIVA
    assert tacche[2].stato == StatoTacca.FATTA


def test_lo_spareggio_compare_solo_nelle_gare_che_ce_l_hanno():
    # In gioco, a turni ancora aperti: non si sa, niente tacca.
    assert not spareggio_nella_striscia(FaseGara.GIOCO)
    # In gioco, turni finiti e un pari merito da sciogliere: la fascia dice
    # «serve uno spareggio» e la striscia deve dirlo con lei.
    assert spareggio_nella_striscia(
        FaseGara.GIOCO, parimerito_aperti=True, turni_conclusi=True
    )
    # Un pari merito a turni aperti non conta: puo' sparire al turno dopo.
    assert not spareggio_nella_striscia(
        FaseGara.GIOCO, parimerito_aperti=True, turni_conclusi=False
    )
    # Nello spareggio adesso, e dopo averlo giocato.
    assert spareggio_nella_striscia(FaseGara.SPAREGGIO)
    assert spareggio_nella_striscia(FaseGara.CONCLUSA, ha_dati_ssr=True)
    assert not spareggio_nella_striscia(FaseGara.CONCLUSA)


def _partita(turno, status, *, tavolo=None, bye=False, distanza=False, doppia=False):
    return SimpleNamespace(
        round_number=turno,
        status=status,
        table_assignment=tavolo,
        is_bye=bye,
        is_at_distance=distanza,
        is_player_validated=doppia,
    )


def test_i_conteggi_del_turno_ignorano_la_x_e_gli_altri_turni():
    partite = [
        _partita(2, MatchStatus.PLAYING.value, tavolo="1"),
        _partita(2, MatchStatus.PLAYING.value, tavolo="2"),
        _partita(2, MatchStatus.PLAYING.value, tavolo="3", distanza=True),
        _partita(2, MatchStatus.CLOSED_UNILATERALLY.value),
        _partita(2, MatchStatus.PENDING.value),
        _partita(2, MatchStatus.CLOSED_UNILATERALLY.value, bye=True),
        _partita(1, MatchStatus.CLOSED_UNILATERALLY.value),
    ]
    c = conteggi_turno(partite, 2, 4, ["1", "2", "3", "4"])
    assert (c.turno, c.turni_totali) == (2, 4)
    assert (c.chiuse, c.totali, c.aperte) == (1, 5, 4)
    assert (c.tavoli_occupati, c.tavoli_totali) == (3, 4)
    assert c.da_validare == 1
    assert c.senza_tavolo == 1
    assert c.percentuale == 20


def test_una_partita_gia_confermata_dai_due_non_e_da_validare():
    partite = [
        _partita(1, MatchStatus.PLAYING.value, tavolo="1", distanza=True, doppia=True)
    ]
    assert conteggi_turno(partite, 1, 1, ["1"]).da_validare == 0


def test_gli_occupati_vengono_dalla_mappa_dei_tavoli_quando_c_e():
    partite = [_partita(1, MatchStatus.PLAYING.value, tavolo="1")]
    c = conteggi_turno(partite, 1, 1, ["1", "2"], occupati={"1": 10, "2": 11})
    assert c.tavoli_occupati == 2


def test_senza_partite_la_percentuale_e_zero():
    c = conteggi_turno([], 1, 3, [])
    assert c.totali == 0 and c.percentuale == 0


# ── Le partite del turno (canvas 3.1–3.9) ─────────────────────────────────────


def _giocatore(nome):
    return SimpleNamespace(username=nome)


def _card(
    id_,
    turno,
    status,
    *,
    tavolo=None,
    bye=False,
    distanza=False,
    doppia=False,
    p1=1,
    p2=2,
):
    return SimpleNamespace(
        id=id_,
        round_number=turno,
        status=status,
        table_assignment=tavolo,
        is_bye=bye,
        is_trio=False,
        trio_match=None,
        is_at_distance=distanza,
        is_player_validated=doppia,
        player1_id=p1,
        player2_id=p2,
        player1=_giocatore(f"u{p1}"),
        player2=_giocatore(f"u{p2}"),
    )


@pytest.mark.parametrize(
    "partita, stato",
    [
        (_card(1, 1, MatchStatus.CLOSED_UNILATERALLY.value, bye=True), StatoPartita.X),
        (_card(1, 1, MatchStatus.CONFIRMED_BY_BOTH.value), StatoPartita.CONCLUSA),
        (
            _card(1, 1, MatchStatus.PLAYING.value, tavolo="1", distanza=True),
            StatoPartita.DA_VALIDARE,
        ),
        (
            _card(
                1, 1, MatchStatus.PLAYING.value, tavolo="1", distanza=True, doppia=True
            ),
            StatoPartita.IN_CORSO,
        ),
        (_card(1, 1, MatchStatus.PLAYING.value, tavolo="1"), StatoPartita.IN_CORSO),
        (_card(1, 1, MatchStatus.PENDING.value), StatoPartita.DA_GIOCARE),
    ],
)
def test_lo_stato_della_card_segue_la_regola_del_canvas(partita, stato):
    assert stato_partita(partita) == stato


def test_le_partite_del_turno_prima_quelle_che_chiedono_qualcosa():
    partite = [
        _card(10, 2, MatchStatus.CLOSED_UNILATERALLY.value, p1=1, p2=2),
        _card(11, 2, MatchStatus.PENDING.value, p1=3, p2=4),
        _card(12, 2, MatchStatus.PLAYING.value, tavolo="1", p1=5, p2=6),
        _card(13, 2, MatchStatus.PLAYING.value, tavolo="2", distanza=True, p1=7, p2=8),
        _card(14, 2, MatchStatus.CLOSED_UNILATERALLY.value, bye=True, p1=9, p2=None),
        _card(15, 1, MatchStatus.CLOSED_UNILATERALLY.value, p1=1, p2=2),
    ]
    assert [m.id for m in partite_del_turno(partite, 2)] == [13, 12, 11, 10, 14]


def test_la_partita_di_chi_dirige_e_gioca_sta_in_cima_finche_e_aperta():
    partite = [
        _card(10, 1, MatchStatus.PLAYING.value, tavolo="1", distanza=True, p1=1, p2=2),
        _card(11, 1, MatchStatus.PENDING.value, p1=3, p2=99),
        _card(12, 1, MatchStatus.CLOSED_UNILATERALLY.value, p1=99, p2=4),
    ]
    assert [m.id for m in partite_del_turno(partite, 1, user_id=99)] == [11, 10, 12]


def test_la_prima_in_attesa_e_la_partita_senza_tavolo_creata_prima():
    partite = [
        _card(21, 1, MatchStatus.PENDING.value),
        _card(20, 1, MatchStatus.PENDING.value),
        _card(19, 1, MatchStatus.PLAYING.value, tavolo="1"),
        _card(18, 2, MatchStatus.PENDING.value),
    ]
    assert prima_in_attesa(partite, 1).id == 20
    assert prima_in_attesa(partite, 3) is None


def test_le_tessere_dei_tavoli_dicono_chi_c_e_sopra():
    partite = [
        _card(1, 1, MatchStatus.PLAYING.value, tavolo="1", p1=1, p2=2),
        _card(2, 1, MatchStatus.CLOSED_UNILATERALLY.value, tavolo="2", p1=3, p2=4),
        _card(3, 2, MatchStatus.PLAYING.value, tavolo="3", p1=5, p2=6),
    ]
    tessere = tavoli_del_turno(partite, ["1", "2", "3", "4"])
    assert [(t.nome, t.libero) for t in tessere] == [
        ("1", False),
        ("2", True),
        ("3", False),
        ("4", True),
    ]
    assert tessere[0].giocatori == ("u1", "u2")
    assert tessere[0].match_id == 1
