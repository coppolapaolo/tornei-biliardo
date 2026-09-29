"""La pagina pubblica «Regolamento del campionato» (ADR-075).

Chiunque vede i valori che il campionato propone alle gare, le gare con il
loro peso e il collegamento al regolamento di ciascuna, i playoff, e la storia
delle modifiche di campionato e playoff insieme.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.competition.services import GaraService
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.playoff.services import PlayoffService

pytestmark = pytest.mark.integration


@pytest.fixture
def campionato(db_session):
    camp = Campionato(
        name=f"C {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        default_entry_fee=10,
        rules_url="https://esempio.it/regolamento.pdf",
    )
    db_session.add(camp)
    db_session.commit()
    GaraService.create_gara(
        number=1,
        name="Gara 1",
        date=date.today() + timedelta(days=10),
        time=time(20, 0),
        discipline="9_ball",
        distance=5,
        campionato_id=camp.id,
        weight=2,
    )
    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
    )
    db_session.add(cfg)
    db_session.commit()
    return camp, cfg


def test_pubblica_con_valori_gare_playoff_storia_e_documento(client, campionato):
    camp, cfg = campionato
    TournamentService().update_campionato(
        camp.id, motivo="Costo dei tavoli", default_entry_fee=12
    )
    PlayoffService.update_configuration(cfg.id, motivo="Finale più lunga", distance=9)
    pagina = client.get(f"/campionato/{camp.id}/regolamento")
    assert pagina.status_code == 200
    testo = pagina.get_data(as_text=True)
    assert "Valori del campionato" in testo
    assert "12 €" in testo
    assert "Gara 1" in testo and "&times;2" in testo
    assert "Playoff · Finale" in testo
    assert "Costo dei tavoli" in testo and "Finale più lunga" in testo
    assert "https://esempio.it/regolamento.pdf" in testo


def test_le_pagine_del_campionato_ci_portano(client, campionato):
    camp, _cfg = campionato
    url = f"/campionato/{camp.id}/regolamento"
    assert url in client.get(f"/campionato/{camp.id}/public").get_data(as_text=True)
