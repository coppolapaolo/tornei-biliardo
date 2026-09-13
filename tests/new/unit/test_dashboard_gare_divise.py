"""Le gare della dashboard divise fra «le tue» e «aperte».

Presidia `models/dashboard/gara_cards.py`. Tre dei casi qui sotto sono
regressioni di difetti trovati disegnando le dashboard (canvas del 2026-08-30):

* la sezione «Gare» conteneva **tutte** le gare vive del sistema, iscritto o
  no — il titolo diceva una cosa e l'elenco un'altra;
* «Lista d'attesa #1» non diceva mai *perché*, e su una gara mezza vuota si
  legge come un errore del sito: il motivo è in colonna da sempre;
* una gara con le iscrizioni **programmate** nel futuro spariva da ogni
  dashboard, compresa quella del direttore che l'aveva appena creata.

Dal 2026-09-10 gli elenchi sono cinque (`ElenchiGare`): la regola 1 dice che
senza un fatto mio la gara non sparisce, sta nell'elenco del suo stato con la
tessera dell'ospite; la regola 2 che le concluse sono di tutti, l'ultima più
l'ultimo mese.

Le entità sono costruite in memoria e non salvate: `build_gara_cards` legge
attributi e chiama `get_real_status()`, che è puro. È lo stesso stile di
`test_issue_65_scheduled_inscriptions_badge.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription, WaitlistReason
from models.dashboard.gara_cards import (
    _ordine_delle_altre,
    FINESTRA_CONCLUSE,
    build_gara_cards,
    finestra_concluse,
)
from models.dashboard.view_models import UnifiedDashboardItem
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus

OGGI = date.today()


def _gara(
    gara_id: int,
    *,
    status: str = GaraStatus.INSCRIPTION.value,
    nome: str = "Gara",
    giorno: date | None = None,
    inscription_start=None,
    inscription_end=None,
) -> Gara:
    """Una gara in memoria, con l'id assegnato a mano.

    L'id serve perché tutte le mappe di `build_gara_cards` sono per `gara.id`;
    su un oggetto mai salvato resterebbe `None` e due gare diverse
    collasserebbero sulla stessa chiave.
    """
    gara = Gara(
        name=nome,
        status=status,
        date=giorno or OGGI,
        inscription_start=inscription_start,
        inscription_end=inscription_end,
    )
    gara.id = gara_id
    return gara


def _item(gara: Gara, *, can_manage: bool = False) -> UnifiedDashboardItem:
    return UnifiedDashboardItem(
        type="gara",
        id=gara.id,
        name=gara.name or "",
        entity=gara,
        next_prova_date=gara.date,
        can_manage=can_manage,
    )


def _iscrizione(
    gara: Gara,
    *,
    waitlist: bool = False,
    reason: str | None = None,
    posizione: int | None = None,
    ritirata: bool = False,
) -> Inscription:
    ins = Inscription(
        user_id=7,
        gara_id=gara.id,
        is_waitlist=waitlist,
        waitlist_position=posizione,
        waitlist_reason=reason,
        is_withdrawn=ritirata,
    )
    ins.gara = gara
    return ins


def _dividi(items, iscrizioni, partite, **kw):
    """(mie, aperte, concluse_totali): la forma con cui sono nati questi test."""
    e = build_gara_cards(items, iscrizioni, partite, **kw)
    return e.mie, e.aperte, e.concluse_totali


# --------------------------------------------------------------------------
# La divisione
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_la_gara_a_cui_sono_iscritto_e_mia():
    gara = _gara(1)
    mie, aperte, _ = _dividi([_item(gara)], [_iscrizione(gara)], [])

    assert [c.id for c in mie] == [1]
    assert aperte == []
    assert mie[0].is_inscribed


@pytest.mark.unit
def test_la_gara_aperta_a_cui_non_sono_iscritto_e_fra_le_aperte():
    gara = _gara(1)
    mie, aperte, _ = _dividi([_item(gara)], [], [])

    assert mie == []
    assert [c.id for c in aperte] == [1]


@pytest.mark.unit
def test_la_gara_in_corso_di_altri_sta_in_diretta_con_la_tessera_dell_ospite():
    """Regola 1 del 2026-09-10: senza un fatto mio la gara non sparisce.

    Non è mia e non è aperta, ma sta succedendo: l'ospite la vede in «In
    diretta ora», e chi è loggato non deve vedere meno dell'ospite.
    """
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    e = build_gara_cards([_item(gara)], [], [])
    assert e.mie == [] and e.aperte == []
    assert [c.id for c in e.in_diretta] == [1]
    assert not e.in_diretta[0].ha_un_fatto_mio


@pytest.mark.unit
def test_una_gara_che_deve_ancora_cominciare_e_in_arrivo():
    """Creata, o con le iscrizioni programmate: contesto, niente da fare."""
    creata = _gara(1, status=GaraStatus.SETUP.value, giorno=OGGI + timedelta(days=20))
    programmata = _gara(
        2,
        inscription_start=utc_now() + timedelta(days=3),
        inscription_end=utc_now() + timedelta(days=10),
    )
    e = build_gara_cards([_item(creata), _item(programmata)], [], [])
    # Per data: la programmata è oggi, la creata fra venti giorni.
    assert [c.id for c in e.in_arrivo] == [2, 1]
    assert e.aperte == [] and e.mie == []


@pytest.mark.unit
def test_la_gara_che_dirigo_e_mia_anche_senza_iscrizione():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    mie, _aperte, _ = _dividi([_item(gara, can_manage=True)], [], [])

    assert [c.id for c in mie] == [1]
    assert mie[0].can_manage
    assert not mie[0].is_inscribed


@pytest.mark.unit
def test_la_gara_che_dirigo_e_in_cui_gioco_compare_una_volta_sola():
    """Una card, due nature.

    Niente vieta al direttore di iscriversi alla propria gara, ed è il motivo
    per cui l'elenco è uno solo: due elenchi la mostrerebbero due volte.
    """
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    mie, _aperte, _ = _dividi([_item(gara, can_manage=True)], [_iscrizione(gara)], [])

    assert len(mie) == 1
    assert mie[0].can_manage and mie[0].is_inscribed


@pytest.mark.unit
def test_una_iscrizione_ritirata_non_rende_la_gara_mia():
    gara = _gara(1)
    mie, aperte, _ = _dividi([_item(gara)], [_iscrizione(gara, ritirata=True)], [])

    assert mie == []
    # E torna disponibile: ritirarsi vuol dire poter rientrare.
    assert [c.id for c in aperte] == [1]


@pytest.mark.unit
def test_le_aperte_ci_sono_anche_per_chi_non_puo_iscriversi():
    """L'amministratore non gioca, ma vede le gare aperte come un ospite: è
    il template a non dargli il pulsante, non l'elenco a nasconderle."""
    gara = _gara(1)
    e = build_gara_cards([_item(gara)], [], [])
    assert [c.id for c in e.aperte] == [1]


# --------------------------------------------------------------------------
# La lista d'attesa dice perché
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_la_lista_d_attesa_per_parita_si_distingue_da_quella_per_capienza():
    piena = _gara(1)
    dispari = _gara(2)

    per_capienza = _iscrizione(
        piena, waitlist=True, reason=WaitlistReason.CAPACITY.value, posizione=3
    )
    per_parita = _iscrizione(
        dispari, waitlist=True, reason=WaitlistReason.PARITY.value, posizione=1
    )

    mie, _aperte, _ = _dividi(
        [_item(piena), _item(dispari)], [per_capienza, per_parita], []
    )
    per_id = {c.id: c for c in mie}

    assert per_id[1].is_waitlist and not per_id[1].waitlist_is_parity
    assert per_id[2].is_waitlist and per_id[2].waitlist_is_parity
    assert per_id[1].waitlist_position == 3
    assert per_id[2].waitlist_position == 1


@pytest.mark.unit
def test_chi_e_in_lista_d_attesa_ha_comunque_la_gara_fra_le_sue():
    """La lista d'attesa è un'iscrizione, non un'assenza."""
    gara = _gara(1)
    ins = _iscrizione(
        gara, waitlist=True, reason=WaitlistReason.CAPACITY.value, posizione=1
    )
    mie, aperte, _ = _dividi([_item(gara)], [ins], [])

    assert [c.id for c in mie] == [1]
    assert aperte == []


# --------------------------------------------------------------------------
# Le iscrizioni programmate
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_una_gara_con_iscrizioni_programmate_resta_visibile_a_chi_la_dirige():
    """Regressione: spariva dalla dashboard di tutti.

    `get_real_status()` risponde `inscription_not_yet_open` per una gara in
    INSCRIPTION la cui apertura è nel futuro, e quello stato non era fra
    quelli «vivi»: il direttore che l'aveva appena programmata non aveva più
    da nessuna parte il pulsante per gestirla.
    """
    gara = _gara(
        1,
        inscription_start=utc_now() + timedelta(days=3),
        inscription_end=utc_now() + timedelta(days=10),
    )
    assert gara.get_real_status() == ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value

    mie, aperte, _ = _dividi([_item(gara, can_manage=True)], [], [])

    assert [c.id for c in mie] == [1]
    # Non è ancora aperta a nessuno: nessuno può iscriversi.
    assert aperte == []


# --------------------------------------------------------------------------
# L'ordine delle mie, e le concluse di tutti
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_prima_quelle_in_corso_poi_le_future_e_le_concluse_stanno_a_parte():
    in_corso = _gara(1, status=GaraStatus.PLAYING.value, giorno=OGGI)
    futura = _gara(2, giorno=OGGI + timedelta(days=30))
    conclusa = _gara(3, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(1))
    e = build_gara_cards(
        [_item(g) for g in (conclusa, futura, in_corso)],
        [_iscrizione(g) for g in (conclusa, futura, in_corso)],
        [],
    )
    assert [c.id for c in e.mie] == [1, 2]
    # Una gara finita non è una cosa da fare: sta fra le concluse, con la
    # pastiglia che dice che c'ero.
    assert [c.id for c in e.concluse] == [3]
    assert e.concluse[0].hai_giocato and not e.concluse[0].hai_diretto


@pytest.mark.unit
def test_le_concluse_sono_di_tutti_e_si_riconoscono_le_mie():
    """Regola 2: le concluse in dashboard sono di tutti, riconoscibili."""
    mia = _gara(1, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(2))
    diretta = _gara(2, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(3))
    altrui = _gara(3, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(4))
    e = build_gara_cards(
        [_item(mia), _item(diretta, can_manage=True), _item(altrui)],
        [_iscrizione(mia)],
        [],
    )
    per_id = {c.id: c for c in e.concluse}
    assert set(per_id) == {1, 2, 3}
    assert per_id[1].hai_giocato and not per_id[1].hai_diretto
    assert per_id[2].hai_diretto and not per_id[2].hai_giocato
    assert not per_id[3].hai_giocato and not per_id[3].hai_diretto
    assert e.concluse_totali == 3


@pytest.mark.unit
def test_la_finestra_delle_concluse_e_l_ultima_piu_un_mese():
    """L'ultima sempre — anche vecchia — più quelle dentro la finestra."""
    giorni = FINESTRA_CONCLUSE.days
    recente = _gara(1, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(5))
    al_limite = _gara(
        2, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(giorni)
    )
    fuori = _gara(
        3, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(giorni + 1)
    )
    e = build_gara_cards(
        [_item(g) for g in (fuori, al_limite, recente)], [], [], oggi=OGGI
    )
    assert [c.id for c in e.concluse] == [1, 2]
    assert e.concluse_totali == 3


@pytest.mark.unit
def test_l_ultima_conclusa_compare_anche_se_ha_sei_mesi():
    """Chi apre la dashboard dopo l'estate trova comunque un aggancio."""
    vecchia = _gara(1, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(180))
    piu_vecchia = _gara(
        2, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(200)
    )
    e = build_gara_cards([_item(piu_vecchia), _item(vecchia)], [], [], oggi=OGGI)
    assert [c.id for c in e.concluse] == [1]
    assert e.concluse_totali == 2


@pytest.mark.unit
def test_finestra_concluse_e_pura_e_ordina_dalla_piu_recente():
    cards = build_gara_cards(
        [
            _item(
                _gara(i, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(i))
            )
            for i in (3, 1, 2)
        ],
        [],
        [],
        oggi=OGGI,
    ).concluse
    assert [c.id for c in finestra_concluse(cards, OGGI)] == [1, 2, 3]
    assert finestra_concluse([], OGGI) == []


# --------------------------------------------------------------------------
# La partita dentro la sua gara
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_la_partita_aperta_finisce_dentro_la_card_della_sua_gara():
    """È il cuore della forma scelta: non più una sezione «I tuoi match»."""
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    match = Match(
        gara_id=1,
        round_number=3,
        player1_id=7,
        player2_id=8,
        status=MatchStatus.PLAYING.value,
    )
    match.id = 55

    mie, _aperte, _ = _dividi([_item(gara)], [_iscrizione(gara)], [match])

    assert mie[0].prossima_partita is match


@pytest.mark.unit
def test_con_due_partite_aperte_la_prossima_e_quella_del_turno_piu_basso():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    tardi = Match(gara_id=1, round_number=4, status=MatchStatus.PENDING.value)
    presto = Match(gara_id=1, round_number=2, status=MatchStatus.PLAYING.value)

    mie, _aperte, _ = _dividi([_item(gara)], [_iscrizione(gara)], [tardi, presto])

    assert mie[0].prossima_partita is presto
    assert [m.round_number for m in mie[0].matches] == [2, 4]


@pytest.mark.unit
def test_una_gara_senza_mie_partite_non_ne_inventa():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    altrove = Match(gara_id=99, round_number=1, status=MatchStatus.PLAYING.value)

    mie, _aperte, _ = _dividi([_item(gara)], [_iscrizione(gara)], [altrove])

    assert mie[0].matches == []
    assert mie[0].prossima_partita is None


# --------------------------------------------------------------------------
# Le gare dentro un campionato
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_le_gare_di_un_campionato_arrivano_srotolate_col_nome_del_campionato():
    prima = _gara(1, nome="Gara 1", status=GaraStatus.PLAYING.value)
    seconda = _gara(2, nome="Gara 2")
    campionato = Campionato(name="Sociale 2026")
    campionato.id = 9
    campionato.gare = [prima, seconda]

    item = UnifiedDashboardItem(
        type="campionato",
        id=9,
        name="Sociale 2026",
        entity=campionato,
        can_manage=False,
    )

    mie, aperte, _ = _dividi([item], [_iscrizione(prima)], [])

    assert [c.id for c in mie] == [1]
    assert mie[0].campionato_name == "Sociale 2026"
    assert [c.id for c in aperte] == [2]
    assert aperte[0].campionato_name == "Sociale 2026"


# --------------------------------------------------------------------------
# Le partite degli altri nella card in corso
# --------------------------------------------------------------------------


def _altra(id_, tavolo, p1=0, p2=0):
    m = Match(gara_id=1, round_number=1, status=MatchStatus.PLAYING.value)
    m.id = id_
    m.table_assignment = tavolo
    m.player1_score = p1
    m.player2_score = p2
    return m


@pytest.mark.unit
def test_un_tavolo_con_la_lettera_e_uno_mancante_non_fanno_cadere_la_dashboard():
    """Regressione: `table_assignment` è testo e può mancare; la chiave
    d'ordine confrontava «A» con un intero e la dashboard rispondeva 500
    (2026-09-13, dataset della guida)."""
    partite = [_altra(3, None), _altra(2, "A"), _altra(1, "2")]

    partite.sort(key=_ordine_delle_altre)

    assert [m.id for m in partite] == [1, 2, 3]


@pytest.mark.unit
def test_i_tavoli_numerici_si_ordinano_per_numero_non_per_lettera():
    partite = [_altra(1, "10"), _altra(2, "2")]

    partite.sort(key=_ordine_delle_altre)

    assert [m.table_assignment for m in partite] == ["2", "10"]


@pytest.mark.unit
def test_prima_le_partite_con_un_punteggio():
    partite = [_altra(1, "1"), _altra(2, "5", p1=2)]

    partite.sort(key=_ordine_delle_altre)

    assert [m.id for m in partite] == [2, 1]
