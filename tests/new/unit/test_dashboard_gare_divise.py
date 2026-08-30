"""Le gare della dashboard divise fra «le tue» e «aperte».

Presidia `models/dashboard/gara_cards.py`. Tre dei casi qui sotto sono
regressioni di difetti trovati disegnando le dashboard (canvas del 2026-08-30):

* la sezione «Gare» conteneva **tutte** le gare vive del sistema, iscritto o
  no — il titolo diceva una cosa e l'elenco un'altra;
* «Lista d'attesa #1» non diceva mai *perché*, e su una gara mezza vuota si
  legge come un errore del sito: il motivo è in colonna da sempre;
* una gara con le iscrizioni **programmate** nel futuro spariva da ogni
  dashboard, compresa quella del direttore che l'aveva appena creata.

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
from models.dashboard.gara_cards import CONCLUSE_IN_CODA, build_gara_cards
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


# --------------------------------------------------------------------------
# La divisione
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_la_gara_a_cui_sono_iscritto_e_mia():
    gara = _gara(1)
    mie, aperte, _ = build_gara_cards([_item(gara)], [_iscrizione(gara)], [])

    assert [c.id for c in mie] == [1]
    assert aperte == []
    assert mie[0].is_inscribed


@pytest.mark.unit
def test_la_gara_aperta_a_cui_non_sono_iscritto_e_fra_le_aperte():
    gara = _gara(1)
    mie, aperte, _ = build_gara_cards([_item(gara)], [], [])

    assert mie == []
    assert [c.id for c in aperte] == [1]


@pytest.mark.unit
def test_la_gara_in_corso_di_altri_non_compare_da_nessuna_parte():
    """Il difetto vero: «Gare» conteneva tutto il sistema.

    Una gara che sta giocando qualcun altro non è né mia né aperta: non ho
    niente da farci. Sta nell'elenco pubblico, dietro il «Vedi tutte».
    """
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    mie, aperte, _ = build_gara_cards([_item(gara)], [], [])

    assert mie == []
    assert aperte == []


@pytest.mark.unit
def test_la_gara_che_dirigo_e_mia_anche_senza_iscrizione():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    mie, _aperte, _ = build_gara_cards([_item(gara, can_manage=True)], [], [])

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
    mie, _aperte, _ = build_gara_cards(
        [_item(gara, can_manage=True)], [_iscrizione(gara)], []
    )

    assert len(mie) == 1
    assert mie[0].can_manage and mie[0].is_inscribed


@pytest.mark.unit
def test_una_iscrizione_ritirata_non_rende_la_gara_mia():
    gara = _gara(1)
    mie, aperte, _ = build_gara_cards(
        [_item(gara)], [_iscrizione(gara, ritirata=True)], []
    )

    assert mie == []
    # E torna disponibile: ritirarsi vuol dire poter rientrare.
    assert [c.id for c in aperte] == [1]


@pytest.mark.unit
def test_l_amministratore_non_vede_le_gare_aperte():
    """L'admin non è un giocatore: «puoi iscriverti» non è vero per lui."""
    gara = _gara(1)
    _mie, aperte, _ = build_gara_cards([_item(gara)], [], [], can_inscribe=False)

    assert aperte == []


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

    mie, _aperte, _ = build_gara_cards(
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
    mie, aperte, _ = build_gara_cards([_item(gara)], [ins], [])

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

    mie, aperte, _ = build_gara_cards([_item(gara, can_manage=True)], [], [])

    assert [c.id for c in mie] == [1]
    # Non è ancora aperta a nessuno: nessuno può iscriversi.
    assert aperte == []


# --------------------------------------------------------------------------
# L'ordine e la coda delle concluse
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_prima_quelle_in_corso_poi_le_future_poi_le_concluse():
    in_corso = _gara(1, status=GaraStatus.PLAYING.value, giorno=OGGI)
    futura = _gara(2, giorno=OGGI + timedelta(days=30))
    conclusa = _gara(3, status=GaraStatus.COMPLETED.value, giorno=OGGI - timedelta(1))

    mie, _aperte, _ = build_gara_cards(
        [_item(g) for g in (conclusa, futura, in_corso)],
        [_iscrizione(g) for g in (conclusa, futura, in_corso)],
        [],
    )

    assert [c.id for c in mie] == [1, 2, 3]


@pytest.mark.unit
def test_le_concluse_sono_limitate_ma_il_totale_torna_intero():
    """La coda si taglia, il conteggio no: serve alla riga «mostrate N di M»."""
    concluse = [
        _gara(
            i,
            status=GaraStatus.COMPLETED.value,
            giorno=OGGI - timedelta(days=i),
        )
        for i in range(1, CONCLUSE_IN_CODA + 4)
    ]
    mie, _aperte, totale = build_gara_cards(
        [_item(g) for g in concluse], [_iscrizione(g) for g in concluse], []
    )

    assert len(mie) == CONCLUSE_IN_CODA
    assert totale == len(concluse)
    # La più recente per prima: di una gara finita interessa l'ultima.
    assert [c.id for c in mie] == [1, 2, 3]


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

    mie, _aperte, _ = build_gara_cards([_item(gara)], [_iscrizione(gara)], [match])

    assert mie[0].prossima_partita is match


@pytest.mark.unit
def test_con_due_partite_aperte_la_prossima_e_quella_del_turno_piu_basso():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    tardi = Match(gara_id=1, round_number=4, status=MatchStatus.PENDING.value)
    presto = Match(gara_id=1, round_number=2, status=MatchStatus.PLAYING.value)

    mie, _aperte, _ = build_gara_cards(
        [_item(gara)], [_iscrizione(gara)], [tardi, presto]
    )

    assert mie[0].prossima_partita is presto
    assert [m.round_number for m in mie[0].matches] == [2, 4]


@pytest.mark.unit
def test_una_gara_senza_mie_partite_non_ne_inventa():
    gara = _gara(1, status=GaraStatus.PLAYING.value)
    altrove = Match(gara_id=99, round_number=1, status=MatchStatus.PLAYING.value)

    mie, _aperte, _ = build_gara_cards([_item(gara)], [_iscrizione(gara)], [altrove])

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

    mie, aperte, _ = build_gara_cards([item], [_iscrizione(prima)], [])

    assert [c.id for c in mie] == [1]
    assert mie[0].campionato_name == "Sociale 2026"
    assert [c.id for c in aperte] == [2]
    assert aperte[0].campionato_name == "Sociale 2026"
