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


def test_nessuno_stato_della_gara_resta_senza_fase():
    """Uno stato nuovo in `GaraStatus` va messo esplicitamente in una fase.

    `fase_della_gara` ripiega in silenzio su «preparazione» per uno stato che
    non conosce (ADR-059): senza questo presidio uno stato aggiunto
    all'enum mostrerebbe la striscia sbagliata senza nessun test rosso,
    perche' l'elenco del test sopra e' scritto a mano.
    """
    from models.competition.direttore_view import _FASE_PER_STATO

    mancanti = [s.value for s in GaraStatus if s.value not in _FASE_PER_STATO]
    assert mancanti == []


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


# ---------------------------------------------------------------------------
# La gara dentro un campionato (peso, playoff, apertura ereditata, date)
# ---------------------------------------------------------------------------


def _campionato(**kw):
    base = dict(
        id=9,
        name="Campionato Sociale",
        planned_gare_count=6,
        default_break_rule=None,
        gare=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _gara_di(campionato, numero, *, weight=1, peso_effettivo=None, config=None, **kw):
    from datetime import date as _date, time as _time

    base = dict(
        id=100 + numero,
        number=numero,
        campionato=campionato,
        campionato_id=campionato.id if campionato else None,
        weight=weight,
        classification_weight=weight if peso_effettivo is None else peso_effettivo,
        playoff_config=config,
        is_playoff=config is not None,
        break_rule=None,
        date=_date(2026, 10, numero),
        time=_time(20, 0),
    )
    base.update(kw)
    gara = SimpleNamespace(**base)
    if campionato is not None:
        campionato.gare.append(gara)
    return gara


def _con_regola(gara):
    from models.match.break_rules import BreakRule

    campionato = gara.campionato
    scelta = BreakRule.normalize(gara.break_rule)
    ereditata = (
        BreakRule.normalize(campionato.default_break_rule) if campionato else None
    )
    gara.effective_break_rule = scelta or ereditata or BreakRule.ALTERNATE
    return gara


def test_una_gara_singola_non_ha_contesto_di_campionato():
    from models.competition.direttore_view import contesto_campionato

    gara = _con_regola(_gara_di(None, 1))
    assert contesto_campionato(gara) is None


def test_il_contesto_dice_numero_gare_previste_e_peso():
    from models.competition.direttore_view import contesto_campionato

    camp = _campionato()
    _gara_di(camp, 3)
    gara = _con_regola(_gara_di(camp, 4, weight=3))
    _gara_di(camp, 5)
    cc = contesto_campionato(gara)
    assert cc is not None
    assert (cc.nome, cc.numero, cc.gare_previste) == ("Campionato Sociale", 4, 6)
    assert cc.peso == 3 and cc.peso_effettivo == 3
    assert not cc.is_playoff and not cc.decide_il_playoff
    assert cc.modalita is None


def test_il_playoff_che_decide_la_classifica_pesa_zero():
    from models.competition.direttore_view import contesto_campionato
    from models.playoff.models import PlayoffRankingMode

    camp = _campionato()
    config = SimpleNamespace(
        ranking_mode=PlayoffRankingMode.PLAYOFF_ONLY, decides_final_ranking=True
    )
    gara = _con_regola(_gara_di(camp, 7, weight=2, peso_effettivo=0, config=config))
    cc = contesto_campionato(gara)
    assert cc.is_playoff and cc.decide_il_playoff
    assert cc.peso == 2 and cc.peso_effettivo == 0
    assert cc.modalita == PlayoffRankingMode.PLAYOFF_ONLY.value
    # Il playoff viene dopo le gare previste: il numero non sfora il totale.
    assert cc.gare_previste >= cc.numero


def test_la_regola_di_apertura_ereditata_dal_campionato():
    from models.competition.direttore_view import contesto_campionato
    from models.match.break_rules import BreakRule

    camp = _campionato(default_break_rule=BreakRule.WINNER_BREAKS.value)
    ereditata = contesto_campionato(_con_regola(_gara_di(camp, 1)))
    assert ereditata.regola_apertura is BreakRule.WINNER_BREAKS
    assert ereditata.apertura_ereditata

    propria = contesto_campionato(
        _con_regola(_gara_di(camp, 2, break_rule=BreakRule.LOSER_BREAKS.value))
    )
    assert propria.regola_apertura is BreakRule.LOSER_BREAKS
    assert not propria.apertura_ereditata


def test_la_finestra_delle_date_viene_dalle_gare_vicine():
    """ADR-016: la gara N sta fra la gara con numero piu' alto < N e quella
    con numero piu' basso > N, non fra N-1 e N+1."""
    from models.competition.direttore_view import contesto_campionato

    camp = _campionato()
    _gara_di(camp, 1)
    _gara_di(camp, 2)
    gara = _con_regola(_gara_di(camp, 4))
    _gara_di(camp, 6)
    cc = contesto_campionato(gara)
    assert cc.precedente.numero == 2
    assert cc.successiva.numero == 6

    prima = contesto_campionato(_con_regola(camp.gare[0]))
    assert prima.precedente is None and prima.successiva.numero == 2
