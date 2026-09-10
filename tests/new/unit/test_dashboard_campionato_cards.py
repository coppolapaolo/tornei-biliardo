"""La tessera del campionato: i fatti di chi guarda sopra quella dell'ospite.

Presidia `models/dashboard/campionato_cards.py` (regola 1 del 2026-09-10):
la testa della classifica c'è per tutti, la **mia riga** si aggiunge sotto
solo se non è già fra le prime, «Hai giocato» / «Hai diretto» sui conclusi,
e la finestra dei conclusi è quella delle gare — l'ultimo più l'ultimo mese —
misurata sulla data dell'ultima gara.

Le entità sono costruite in memoria; la classifica arriva da un doppione di
`TournamentService`, perché qui si prova la regola e non il calcolo.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.dashboard import campionato_cards as cc
from models.dashboard.view_models import UnifiedDashboardItem
from models.status_enum import ClassificationSystem, GaraStatus

OGGI = date.today()


def _campionato(cid: int, *, gare_date, concluso: bool = False, rack=False):
    c = Campionato(name=f"Campionato {cid}")
    c.id = cid
    # `classification_system` è una property che risolve la colonna.
    c.default_classification_system = (
        ClassificationSystem.RACK.value if rack else ClassificationSystem.WINS.value
    )
    c.gare = []
    for i, giorno in enumerate(gare_date, start=1):
        g = Gara(
            name=f"Gara {i}",
            number=i,
            date=giorno,
            status=(
                GaraStatus.COMPLETED.value if concluso else GaraStatus.INSCRIPTION.value
            ),
        )
        g.id = cid * 100 + i
        g.campionato_id = cid
        c.gare.append(g)
    return c


def _item(c: Campionato, *, can_manage=False) -> UnifiedDashboardItem:
    return UnifiedDashboardItem(
        type="campionato", id=c.id, name=c.name, entity=c, can_manage=can_manage
    )


def _iscrizione(gara: Gara) -> Inscription:
    ins = Inscription(user_id=7, gara_id=gara.id)
    ins.gara = gara
    return ins


@pytest.fixture(autouse=True)
def _stato_calcolato(monkeypatch):
    """`get_status` legge le gare dal DB: qui lo stato lo dice la gara."""

    def stato(self):
        from models.status_enum import TournamentStatus

        finite = all(g.status == GaraStatus.COMPLETED.value for g in self.gare)
        return (
            TournamentStatus.COMPLETED.value
            if finite
            else TournamentStatus.IN_PROGRESS.value
        )

    monkeypatch.setattr(Campionato, "get_status", stato)


@pytest.mark.unit
def test_iscritto_a_una_gara_rende_il_campionato_mio():
    c = _campionato(1, gare_date=[OGGI + timedelta(days=5)])
    e = cc.build_campionato_cards([_item(c)], [_iscrizione(c.gare[0])])
    assert e.attivi[0].is_inscribed
    assert e.conclusi == []


@pytest.mark.unit
def test_il_concluso_dice_se_hai_giocato_o_diretto():
    giocato = _campionato(1, gare_date=[OGGI - timedelta(days=3)], concluso=True)
    diretto = _campionato(2, gare_date=[OGGI - timedelta(days=4)], concluso=True)
    e = cc.build_campionato_cards(
        [_item(giocato), _item(diretto, can_manage=True)],
        [_iscrizione(giocato.gare[0])],
        oggi=OGGI,
    )
    per_id = {c.id: c for c in e.conclusi}
    assert per_id[1].hai_giocato and not per_id[1].hai_diretto
    assert per_id[2].hai_diretto and not per_id[2].hai_giocato
    assert e.attivi == []


@pytest.mark.unit
def test_la_finestra_dei_conclusi_e_l_ultimo_piu_un_mese_sull_ultima_gara():
    giorni = cc.FINESTRA_CONCLUSE.days
    recente = _campionato(
        1,
        gare_date=[OGGI - timedelta(days=90), OGGI - timedelta(days=2)],
        concluso=True,
    )
    fuori = _campionato(2, gare_date=[OGGI - timedelta(days=giorni + 1)], concluso=True)
    antico = _campionato(3, gare_date=[OGGI - timedelta(days=300)], concluso=True)
    e = cc.build_campionato_cards(
        [_item(antico), _item(fuori), _item(recente)], [], oggi=OGGI
    )
    assert [c.id for c in e.conclusi] == [1]
    assert e.conclusi_totali == 3
    # L'ultimo compare sempre, anche da solo e vecchio.
    solo = cc.build_campionato_cards([_item(antico)], [], oggi=OGGI)
    assert [c.id for c in solo.conclusi] == [3]


@pytest.mark.unit
def test_le_prossime_gare_sono_poche_e_in_ordine():
    c = _campionato(
        1,
        gare_date=[
            OGGI - timedelta(days=1),
            OGGI + timedelta(days=9),
            OGGI + timedelta(days=2),
            OGGI + timedelta(days=30),
        ],
    )
    e = cc.build_campionato_cards([_item(c)], [], oggi=OGGI)
    assert [g.date for g in e.attivi[0].prossime] == [
        OGGI + timedelta(days=2),
        OGGI + timedelta(days=9),
    ]


def _classifica_finta(monkeypatch, righe):
    from models.campionato.tournament_service import TournamentService

    monkeypatch.setattr(
        TournamentService,
        "calculate_general_classification",
        lambda self, campionato_id: righe,
    )


def _riga(pos, uid, vittorie=0, triangoli=0):
    return (
        pos,
        {
            "user_id": uid,
            "username": f"u{uid}",
            "total_matches_won": vittorie,
            "total_racks_won": triangoli,
        },
    )


@pytest.mark.unit
def test_la_mia_riga_si_aggiunge_sotto_la_testa_se_non_ci_sono_gia(monkeypatch):
    _classifica_finta(
        monkeypatch, [_riga(1, 11, 7), _riga(2, 12, 6), _riga(3, 13, 6), _riga(4, 7, 5)]
    )
    c = _campionato(1, gare_date=[OGGI + timedelta(days=5)])
    card = cc.build_campionato_cards([_item(c)], [_iscrizione(c.gare[0])]).attivi[0]
    cc.enrich_with_classifica([card], user_id=7)
    assert [r.posizione for r in card.testa] == [1, 2, 3]
    assert card.mia_riga is not None and card.mia_riga.posizione == 4
    assert card.mia_riga.is_me and card.mia_riga.valore == 5
    assert not any(r.is_me for r in card.testa)


@pytest.mark.unit
def test_se_sono_gia_in_testa_la_riga_non_si_ripete(monkeypatch):
    _classifica_finta(monkeypatch, [_riga(1, 11, 7), _riga(2, 7, 6), _riga(3, 13, 6)])
    c = _campionato(1, gare_date=[OGGI + timedelta(days=5)])
    card = cc.build_campionato_cards([_item(c)], [_iscrizione(c.gare[0])]).attivi[0]
    cc.enrich_with_classifica([card], user_id=7)
    assert card.mia_riga is None
    assert [r.is_me for r in card.testa] == [False, True, False]


@pytest.mark.unit
def test_il_valore_segue_il_sistema_di_classifica_non_il_tipo(monkeypatch):
    """Issue #89: con il sistema a triangoli si mostrano i triangoli."""
    _classifica_finta(monkeypatch, [_riga(1, 11, vittorie=3, triangoli=40)])
    c = _campionato(1, gare_date=[OGGI + timedelta(days=5)], rack=True)
    card = cc.build_campionato_cards([_item(c)], []).attivi[0]
    cc.enrich_with_classifica([card], user_id=7)
    assert card.is_rack and card.testa[0].valore == 40
