"""Il campionato concluso in vetrina e nella pagina del direttore.

Canvas «campionato-concluso», forma A (2026-09-14): il campione in cima —
sulla targa della vetrina, nella fascia della pagina del direttore — con
secondo e terzo sotto. La classifica diventa «Classifica finale», senza zona
playoff né frecce; la finale sta fra le gare con chi l'ha vinta, e il
pulsante «Risultati della finale» sparisce.

Durante la fase playoff non si sa ancora chi vince: lì non cambia niente.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.competition.models import Gara
from models.playoff.models import PlayoffRankingMode
from models.status_enum import GaraStatus
from models.user.models import DirectorAssignment
from tests.new.unit.test_playoff_classifica_finale_e_peso import (
    _campionato_con_playoff,
    _make_user,
    _righe_di_turno,
)

pytestmark = pytest.mark.integration


def _concluso(db_session, mode=PlayoffRankingMode.PLAYOFF_ONLY):
    dati = _campionato_con_playoff(db_session, mode)
    _righe_di_turno(db_session, dati["campionato"])
    camp = dati["campionato"]
    camp.terminated_at = utc_now()
    direttore = _make_user(db_session, "dir", role="director")
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=camp.id,
            user_id=direttore.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.commit()
    dati["direttore"] = direttore
    return dati


def _finale_in_corso(db_session, dati):
    dati["playoff"].status = GaraStatus.PLAYING.value
    db_session.commit()


def _senza_debug(html: str) -> str:
    """Il pannello di debug in fondo elenca ogni utente: si taglia sul tag."""
    return html.split('<footer class="debug-footer"')[0]


def _pagina_direttore(client, dati) -> str:
    client.post(
        "/auth/login",
        data={"username": dati["direttore"].username, "password": "test1234"},
        follow_redirects=True,
    )
    risposta = client.get(f"/admin/campionato/{dati['campionato'].id}")
    assert risposta.status_code == 200
    return _senza_debug(risposta.get_data(as_text=True))


def _vetrina(client, dati) -> str:
    risposta = client.get(f"/c/{dati['campionato'].public_token}")
    assert risposta.status_code == 200
    return _senza_debug(risposta.get_data(as_text=True))


def _fascia(html: str) -> str:
    inizio = html.index("c7-fascia")
    return html[inizio : html.index("</section>", inizio)]


class TestPaginaDelDirettore:
    def test_la_fascia_dice_chi_ha_vinto_il_campionato(self, client, db_session):
        dati = _concluso(db_session)

        fascia = _fascia(_pagina_direttore(client, dati))

        assert "Campionato concluso" in fascia
        assert "c7-campione" in fascia and "Campione" in fascia
        assert dati["d"].username in fascia.split("c7-campione__nome")[1]
        # Secondo e terzo con i chip delle medaglie.
        assert "c7-pos--2" in fascia and dati["c"].username in fascia
        assert "c7-pos--3" in fascia and dati["a"].username in fascia
        assert "Classifica definitiva" not in fascia

    def test_con_la_somma_il_campione_e_il_primo_della_classifica(
        self, client, db_session
    ):
        dati = _concluso(db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF)

        fascia = _fascia(_pagina_direttore(client, dati))

        nome = fascia.split("c7-campione__nome")[1].split("</div>")[0]
        assert dati["a"].username in nome
        assert dati["d"].username not in nome

    def test_via_il_pulsante_risultati_della_finale(self, client, db_session):
        dati = _concluso(db_session)

        html = _pagina_direttore(client, dati)

        assert "Risultati della finale" not in html
        # La finale resta raggiungibile dalla sua riga fra le gare.
        assert f"/admin/gara/{dati['playoff'].id}" in html

    def test_la_classifica_e_quella_finale(self, client, db_session):
        dati = _concluso(db_session)

        html = _pagina_direttore(client, dati)

        assert "Classifica finale" in html and "definitiva" in html
        assert "Classifica generale" not in html
        assert "Zona playoff" not in html and "c7-cg__riga--zona" not in html
        assert "c7-classifica__trend" not in html

    def test_ogni_gara_conclusa_dice_chi_l_ha_vinta(self, client, db_session):
        dati = _concluso(db_session)

        html = _pagina_direttore(client, dati)

        finale = html.split(f"/admin/gara/{dati['playoff'].id}")[1].split(
            "c7-cgara__link"
        )[0]
        assert f"ha vinto {dati['d'].username}" in finale
        gare = Gara.query.filter_by(campionato_id=dati["campionato"].id).count()
        assert html.count("ha vinto ") == gare

    def test_durante_la_finale_non_c_e_campione(self, client, db_session):
        dati = _concluso(db_session)
        _finale_in_corso(db_session, dati)

        html = _pagina_direttore(client, dati)

        assert "Fase playoff" in html
        assert "c7-campione" not in html
        assert "Classifica generale" in html


class TestVetrina:
    def test_il_campione_sta_sulla_targa(self, client, db_session):
        dati = _concluso(db_session)

        html = _vetrina(client, dati)
        targa = html.split("c7-vt__plate")[1].split("c7-vt__facts")[0]

        assert "Campionato concluso" in targa
        assert "c7-campione" in targa and "Campione" in targa
        assert dati["d"].username in targa.split("c7-campione__nome")[1]
        assert "c7-pos--2" in targa and "c7-pos--3" in targa
        # Il kicker prende il posto del badge.
        assert "c7-vt__badge" not in targa

    def test_classifica_finale_prima_delle_gare_e_niente_iscrizioni(
        self, client, db_session
    ):
        dati = _concluso(db_session)

        html = _vetrina(client, dati)

        assert "Classifica finale" in html and "definitiva" in html
        assert html.index("Classifica finale") < html.index("Le gare")
        assert "Nessuna gara ha le iscrizioni aperte" not in html
        assert "Condividi il campionato" in html
        # La finale sta nel calendario con il suo vincitore.
        assert f"Vince {dati['d'].username}" in html

    def test_durante_la_finale_la_vetrina_resta_com_era(self, client, db_session):
        dati = _concluso(db_session)
        _finale_in_corso(db_session, dati)

        html = _vetrina(client, dati)

        assert "c7-campione" not in html
        assert "Classifica finale" not in html
        assert "Nessuna gara ha le iscrizioni aperte" in html


def test_la_pagina_pubblica_del_campionato_resta_quella_di_prima(client, db_session):
    """Il componente della classifica è incluso anche lì, senza la variante."""
    dati = _concluso(db_session)

    risposta = client.get(f"/campionato/{dati['campionato'].id}/public")

    assert risposta.status_code == 200
    html = risposta.get_data(as_text=True)
    assert "Classifica generale" in html
