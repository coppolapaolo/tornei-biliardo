"""Competizione di prova (ADR-058), tappa 3: il campionato di prova dal client.

La spunta nel wizard, il banner sulla pagina del campionato, la data proposta
per le gare, i pulsanti sugli inviti al playoff per ciascun fittizio più
«Accetta tutti i rimanenti», l'eliminazione dal banner. Il servizio è provato
in `tests/new/unit/test_prova_campionato.py`; qui si percorre il giunto
interfaccia↔server.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from flask import url_for

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.prova.service import LIMITE_PROVE_ATTIVE, ProvaService
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole
from utils.feature_flags import ENDPOINT_ROLES

pytestmark = pytest.mark.integration


def _pulisci_stato_fra_richieste() -> None:
    """Vedi `test_prova_visibilita.py`: `g` e l'identity map sopravvivono."""
    from flask import g

    g.pop("_login_user", None)
    db.session.expunge_all()


def _campionato_di_prova(direttore: User) -> int:
    with prova_visibili():
        campionato = TournamentService().create_campionato_with_director(
            name=f"Campionato di prova {uuid.uuid4().hex[:4]}",
            creator_user_id=direttore.id,
            **ProvaService.campi_di_creazione(),
        )
        db.session.commit()
        return campionato.id


def _passo1(nome: str, prova: bool = True) -> dict:
    dati = {
        "name": nome,
        "planned_gare_count": "3",
        "campionato_type": "amalfi",
        "default_classification_system": "WINS",
        "playoff_elite_enabled": "on",
        "playoff_elite_participants": "2",
    }
    if prova:
        dati["is_prova"] = "on"
    return dati


def _playoff_con_inviti(direttore: User) -> dict:
    """Campionato di prova terminato, quattro fittizi in classifica, un playoff
    da due posti con i primi due invitati. Tutto sul DB, come in
    `test_playoff_invito_dashboard_e_direttore.py`."""
    campionato_id = _campionato_di_prova(direttore)
    with prova_visibili():
        gara = GaraService.create_gara(
            campionato_id=campionato_id,
            number=1,
            name="Gara 1",
            date=date.today() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            status=GaraStatus.COMPLETED.value,
        )
        db.session.commit()
        fittizi = ProvaService.crea_fittizi(gara, 4)
        for posizione, fittizio in enumerate(fittizi, start=1):
            db.session.add(Inscription(user_id=fittizio.id, gara_id=gara.id))
            db.session.add(
                Classification(
                    campionato_id=campionato_id,
                    user_id=fittizio.id,
                    position=posizione,
                    total_matches_won=10 - posizione,
                    total_point_difference=20 - posizione,
                    gare_played=1,
                )
            )
        config = PlayoffConfiguration(
            campionato_id=campionato_id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=2,
            positions_from=1,
            positions_to=2,
            is_active=True,
        )
        db.session.add(config)
        db.session.flush()
        inviti = []
        for posizione, fittizio in enumerate(fittizi[:2], start=1):
            invito = PlayoffQualification(
                configuration_id=config.id,
                user_id=fittizio.id,
                qualifying_position=posizione,
                qualification_reason=f"Posizione {posizione}",
                status=QualificationStatus.PENDING,
                invited_at=utc_now(),
            )
            db.session.add(invito)
            inviti.append(invito)
        campionato = db.session.get(Campionato, campionato_id)
        assert campionato is not None
        campionato.terminated_at = utc_now()
        db.session.commit()
        return {
            "campionato_id": campionato_id,
            "config_id": config.id,
            "fittizi_ids": [f.id for f in fittizi],
            "inviti_ids": [q.id for q in inviti],
        }


@pytest.fixture
def direttore_loggato(logged_in_client):
    client, direttore = logged_in_client(role=UserRole.DIRECTOR, username_prefix="dir")
    return client, direttore


class TestIlWizard:
    def test_la_spunta_crea_un_campionato_di_prova(self, direttore_loggato):
        client, direttore = direttore_loggato
        passo2 = client.post(
            url_for("admin.campionato.wizard_step2"), data=_passo1("Prova dal wizard")
        )
        assert passo2.status_code == 200
        assert "Competizione di prova" in passo2.get_data(as_text=True)

        creazione = client.post(
            url_for("admin.campionato.wizard_create"),
            data={"default_rounds_count": "3", "default_odd_policy": "bye"},
            follow_redirects=True,
        )
        html = creazione.get_data(as_text=True)
        assert creazione.status_code == 200
        assert "solo tu la vedi" in html
        # Il banner della prova, sulla pagina del campionato.
        assert "Sparisce da sola il" in html
        assert "Elimina la prova" in html

        prove = ProvaService.prove_attive(direttore.id)
        assert [p.name for p in prove] == ["Prova dal wizard"]
        assert prove[0].prova_expires_at is not None

    def test_senza_spunta_e_un_campionato_vero(self, direttore_loggato):
        client, direttore = direttore_loggato
        client.post(
            url_for("admin.campionato.wizard_step2"),
            data=_passo1("Campionato vero", prova=False),
        )
        html = client.post(
            url_for("admin.campionato.wizard_create"),
            data={"default_rounds_count": "3"},
            follow_redirects=True,
        ).get_data(as_text=True)
        assert "solo tu la vedi" not in html
        assert "Elimina la prova" not in html
        assert ProvaService.prove_attive(direttore.id) == []

    def test_al_limite_la_spunta_e_spenta_e_il_server_rifiuta(self, direttore_loggato):
        client, direttore = direttore_loggato
        direttore_id = direttore.id
        for _ in range(LIMITE_PROVE_ATTIVE):
            _campionato_di_prova(direttore)
        _pulisci_stato_fra_richieste()

        modulo = client.get(url_for("admin.campionato.wizard_start")).get_data(
            as_text=True
        )
        assert "eliminane una" in modulo

        client.post(url_for("admin.campionato.wizard_step2"), data=_passo1("Quarta"))
        risposta = client.post(
            url_for("admin.campionato.wizard_create"),
            data={"default_rounds_count": "3"},
            follow_redirects=True,
        )
        assert "prove aperte" in risposta.get_data(as_text=True)
        assert len(ProvaService.prove_attive(direttore_id)) == LIMITE_PROVE_ATTIVE


class TestLeGareDelCampionato:
    def test_la_gara_nasce_di_prova_e_la_data_proposta_e_domani(
        self, direttore_loggato
    ):
        client, direttore = direttore_loggato
        campionato_id = _campionato_di_prova(direttore)
        _pulisci_stato_fra_richieste()

        pagina = client.get(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        ).get_data(as_text=True)
        domani = (date.today() + timedelta(days=1)).isoformat()
        assert f'id="create_date" value="{domani}"' in pagina

        creazione = client.post(
            url_for("admin.competition.create_gara"),
            data={
                "campionato_id": str(campionato_id),
                "number": "1",
                "name": "Gara 1",
                "date": domani,
                "time": "20:00",
                "discipline": Discipline.NINE_BALL.value,
                "distance": "5",
                "rounds_count": "3",
                "min_participants": "4",
                "max_participants": "8",
                "location": "Sala di prova",
            },
        )
        assert creazione.status_code == 302, creazione.get_data(as_text=True)
        with prova_visibili():
            gara = Gara.query.filter_by(campionato_id=campionato_id).one()
            assert gara.is_prova is True
            gara_id = gara.id
        _pulisci_stato_fra_richieste()

        # La gara ha il banner — che da qui elimina tutto il campionato — e la
        # prossima data proposta e' il giorno dopo la gara appena creata.
        gara_html = client.get(
            url_for("admin.competition.gara_detail", gara_id=gara_id)
        ).get_data(as_text=True)
        assert "Competizione di prova" in gara_html
        assert "con tutto il campionato" in gara_html
        pagina = client.get(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        ).get_data(as_text=True)
        dopodomani = (date.today() + timedelta(days=2)).isoformat()
        assert f'id="create_date" value="{dopodomani}"' in pagina

    def test_la_vetrina_rimanda_al_campionato(self, direttore_loggato):
        client, direttore = direttore_loggato
        campionato_id = _campionato_di_prova(direttore)
        _pulisci_stato_fra_richieste()
        risposta = client.get(
            url_for("admin.campionato.campionato_vetrina", campionato_id=campionato_id),
            follow_redirects=True,
        )
        assert "non ha vetrina" in risposta.get_data(as_text=True)


class TestGliInvitiAlPlayoff:
    def test_la_pagina_offre_accetta_rifiuta_e_tutti_i_rimanenti(
        self, direttore_loggato
    ):
        client, direttore = direttore_loggato
        scenario = _playoff_con_inviti(direttore)
        _pulisci_stato_fra_richieste()
        html = client.get(
            url_for(
                "admin.campionato.campionato_detail",
                campionato_id=scenario["campionato_id"],
            )
        ).get_data(as_text=True)
        assert "Accetta tutti i rimanenti" in html
        for invito_id in scenario["inviti_ids"]:
            assert f"/prova/invito/{invito_id}/accetta" in html
            assert f"/prova/invito/{invito_id}/rifiuta" in html

    def test_un_rifiuto_fa_comparire_il_sostituto(self, direttore_loggato):
        client, direttore = direttore_loggato
        scenario = _playoff_con_inviti(direttore)
        secondo = scenario["inviti_ids"][1]
        _pulisci_stato_fra_richieste()
        risposta = client.post(
            url_for(
                "admin.campionato.prova_rispondi_invito",
                campionato_id=scenario["campionato_id"],
                qualification_id=secondo,
                risposta="rifiuta",
            ),
            follow_redirects=True,
        )
        html = risposta.get_data(as_text=True)
        assert risposta.status_code == 200
        assert "passa a" in html
        with prova_visibili():
            db.session.expire_all()
            inviti = PlayoffQualification.query.filter_by(
                configuration_id=scenario["config_id"]
            ).all()
            assert len(inviti) == 3
            sostituto = next(q for q in inviti if q.id not in scenario["inviti_ids"])
            assert sostituto.user_id == scenario["fittizi_ids"][2]
            assert sostituto.status == QualificationStatus.PENDING

    def test_accetta_tutti_i_rimanenti(self, direttore_loggato):
        client, direttore = direttore_loggato
        scenario = _playoff_con_inviti(direttore)
        _pulisci_stato_fra_richieste()
        risposta = client.post(
            url_for(
                "admin.campionato.prova_accetta_inviti",
                campionato_id=scenario["campionato_id"],
            ),
            follow_redirects=True,
        )
        assert "2 inviti accettati" in risposta.get_data(as_text=True)
        with prova_visibili():
            db.session.expire_all()
            stati = {
                q.status
                for q in PlayoffQualification.query.filter_by(
                    configuration_id=scenario["config_id"]
                ).all()
            }
            assert stati == {QualificationStatus.CONFIRMED}

    def test_una_risposta_inventata_e_404(self, direttore_loggato):
        client, direttore = direttore_loggato
        scenario = _playoff_con_inviti(direttore)
        _pulisci_stato_fra_richieste()
        risposta = client.post(
            url_for(
                "admin.campionato.prova_rispondi_invito",
                campionato_id=scenario["campionato_id"],
                qualification_id=scenario["inviti_ids"][0],
                risposta="forse",
            )
        )
        assert risposta.status_code == 404

    def test_le_route_sono_riservate_ai_direttori(self):
        for endpoint in (
            "admin.campionato.prova_rispondi_invito",
            "admin.campionato.prova_accetta_inviti",
            "admin.campionato.prova_elimina",
        ):
            assert ENDPOINT_ROLES[endpoint] == {"director"}


class TestEliminazione:
    def test_dal_banner_del_campionato(self, direttore_loggato):
        client, direttore = direttore_loggato
        scenario = _playoff_con_inviti(direttore)
        campionato_id = scenario["campionato_id"]
        _pulisci_stato_fra_richieste()
        risposta = client.post(
            url_for("admin.campionato.prova_elimina", campionato_id=campionato_id),
            follow_redirects=False,
        )
        assert risposta.status_code == 302
        assert risposta.headers["Location"].endswith(url_for("dashboard.dashboard"))
        with prova_visibili():
            assert db.session.get(Campionato, campionato_id) is None
            assert Gara.query.filter_by(campionato_id=campionato_id).count() == 0
            assert User.query.filter(User.id.in_(scenario["fittizi_ids"])).count() == 0

    def test_un_campionato_vero_da_qui_e_404(self, direttore_loggato):
        client, direttore = direttore_loggato
        vero = TournamentService().create_campionato_with_director(
            name="Vero", creator_user_id=direttore.id
        )
        db.session.commit()
        vero_id = vero.id
        _pulisci_stato_fra_richieste()
        risposta = client.post(
            url_for("admin.campionato.prova_elimina", campionato_id=vero_id)
        )
        assert risposta.status_code == 404
        assert db.session.get(Campionato, vero_id) is not None
