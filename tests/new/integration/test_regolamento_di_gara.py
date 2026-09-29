"""La pagina pubblica «Regolamento di gara» (ADR-075).

Chiunque — anche senza account — vede con che regole si gioca, da quale turno
vale un cambio, la storia delle modifiche e il documento del regolamento.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.round_configuration import RoundConfiguration
from models.competition.services import GaraService
from models.storia.regolamento import regolamento

pytestmark = pytest.mark.integration


@pytest.fixture
def gara(db_session):
    camp = Campionato(
        name=f"C {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        rules_url="https://esempio.it/regolamento.pdf",
    )
    db_session.add(camp)
    db_session.commit()
    g = GaraService.create_gara(
        number=1,
        name="Gara 1",
        date=date.today() + timedelta(days=10),
        time=time(20, 0),
        discipline="9_ball",
        distance=5,
        rounds_count=4,
        campionato_id=camp.id,
        location="Sala A",
    )
    db_session.commit()
    return g


class TestLaPagina:
    def test_pubblica_con_impostazioni_storia_e_documento(self, client, gara):
        GaraService.update_gara(gara.id, location="Sala B", motivo="Sala chiusa")
        pagina = client.get(f"/gara/{gara.id}/regolamento")
        assert pagina.status_code == 200
        testo = pagina.get_data(as_text=True)
        assert "In vigore" in testo
        assert "Sala B" in testo
        assert "Sala chiusa" in testo
        assert "Regolamento completo" in testo
        assert "https://esempio.it/regolamento.pdf" in testo

    def test_il_documento_della_gara_vince_su_quello_del_campionato(self, gara):
        assert gara.effective_rules_url == "https://esempio.it/regolamento.pdf"
        gara.rules_url = "https://esempio.it/gara1.pdf"
        db.session.commit()
        assert gara.effective_rules_url == "https://esempio.it/gara1.pdf"

    def test_la_pagina_della_gara_ci_porta(self, client, gara):
        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert f"/gara/{gara.id}/regolamento" in pagina


class TestTurnoPerTurno:
    def test_uguali_niente_sezione(self, gara):
        assert regolamento(gara).per_turno == []

    def test_un_turno_diverso_si_vede(self, db_session, gara):
        db_session.add(RoundConfiguration(gara_id=gara.id, round_number=4, distance=7))
        db_session.commit()
        gruppi = regolamento(gara).per_turno
        assert [(g.dal, g.al) for g in gruppi] == [(1, 3), (4, 4)]
        assert gruppi[0].regole[1] == "5" and gruppi[1].regole[1] == "7"
