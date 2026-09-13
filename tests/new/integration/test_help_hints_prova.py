"""Aiuto contestuale (ADR-058, tappa 4): il giunto fra pagina, API e testi.

Il test statico (`test_help_anchors.py`) garantisce che ogni ancora abbia un
elemento *da qualche parte*. Qui si guarda la pagina renderizzata: che le
schermate della prova portino l'interruttore e le ancore dei loro comandi, e
che ogni `data-help` presente sulla pagina sia servito dall'API **di quella
schermata** — altrimenti la «?» non compare, perché il componente chiede i
testi per endpoint e un'ancora dichiarata per un'altra schermata non arriva.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

import pytest
from flask import url_for

from models.base import db
from models.campionato.tournament_service import TournamentService
from models.competition.models import Gara
from models.competition.services import GaraService
from models.matchmaking.configuration import (
    FirstRoundPolicy,
    MatchmakingStrategy,
    OddNumberPolicy,
)
from models.prova.service import ProvaService
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

DATA_HELP = re.compile(r"""\bdata-help=["']([a-z0-9-]+)["']""")


def _prova(direttore: User, *, iscritti: int = 6) -> Gara:
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Prova {uuid.uuid4().hex[:4]}",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        min_participants=iscritti,
        max_participants=iscritti,
        rounds_count=3,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
        first_round_policy=FirstRoundPolicy.RANDOM.value,
        odd_number_policy=OddNumberPolicy.BYE.value,
        status=GaraStatus.INSCRIPTION.value,
        **ProvaService.campi_di_creazione(),
    )
    db.session.commit()
    return gara


def _pulisci_stato_fra_richieste() -> None:
    from flask import g

    g.pop("_login_user", None)
    db.session.expunge_all()


def _anchors_serviti(client, screen: str) -> set[str]:
    risposta = client.get(url_for("help.screen_api", screen=screen))
    assert risposta.status_code == 200, screen
    return {hint["anchor"] for hint in risposta.get_json()["hints"]}


def _anchors_in_pagina(html: str) -> set[str]:
    return set(DATA_HELP.findall(html))


def _config_screen(html: str) -> str:
    """L'endpoint che il guscio dichiara al componente."""
    blocco = html.split('id="help-hints-config"', 1)[1]
    trovato = re.search(r'"screen":\s*"([^"]+)"', blocco)
    assert trovato, "configurazione senza `screen`"
    return trovato.group(1)


@pytest.fixture
def direttore_loggato(logged_in_client):
    client, direttore = logged_in_client(role=UserRole.DIRECTOR, username_prefix="dir")
    return client, direttore


class TestGaraDiProva:
    def test_iscrizioni_aperte(self, direttore_loggato):
        client, direttore = direttore_loggato
        gara_id = _prova(direttore).id
        _pulisci_stato_fra_richieste()
        html = client.get(
            url_for("admin.competition.gara_detail", gara_id=gara_id)
        ).get_data(as_text=True)

        assert "data-help-toggle" in html, "l'interruttore sta nel banner"
        assert _config_screen(html) == "admin.competition.gara_detail"
        in_pagina = _anchors_in_pagina(html)
        assert {"prova-fittizi", "prova-aiuto", "prova-elimina"} <= in_pagina

        serviti = _anchors_serviti(client, "admin.competition.gara_detail")
        assert in_pagina <= serviti, sorted(in_pagina - serviti)

    def test_in_gioco(self, direttore_loggato):
        client, direttore = direttore_loggato
        gara_id = _prova(direttore).id
        client.post(
            url_for(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="minimo",
            ),
            follow_redirects=True,
        )
        risposta = client.post(
            url_for("admin.competition.start_first_round", gara_id=gara_id),
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        _pulisci_stato_fra_richieste()
        with prova_visibili():
            gara = db.session.get(Gara, gara_id)
            assert gara is not None and gara.status == GaraStatus.PLAYING.value

        html = client.get(
            url_for("admin.competition.gara_detail", gara_id=gara_id)
        ).get_data(as_text=True)
        in_pagina = _anchors_in_pagina(html)
        assert "prova-simulazione" in in_pagina
        serviti = _anchors_serviti(client, "admin.competition.gara_detail")
        assert in_pagina <= serviti, sorted(in_pagina - serviti)


class TestCampionatoDiProva:
    def test_pagina_del_campionato(self, direttore_loggato):
        client, direttore = direttore_loggato
        campionato = TournamentService().create_campionato_with_director(
            name=f"Campionato di prova {uuid.uuid4().hex[:4]}",
            creator_user_id=direttore.id,
            planned_gare_count=2,
            **ProvaService.campi_di_creazione(),
        )
        db.session.commit()
        campionato_id = campionato.id
        _pulisci_stato_fra_richieste()

        html = client.get(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        ).get_data(as_text=True)
        assert "data-help-toggle" in html
        assert _config_screen(html) == "admin.campionato.campionato_detail"
        in_pagina = _anchors_in_pagina(html)
        assert {
            "campionato-nuova-gara",
            "campionato-termina",
            "prova-aiuto",
        } <= in_pagina
        serviti = _anchors_serviti(client, "admin.campionato.campionato_detail")
        assert in_pagina <= serviti, sorted(in_pagina - serviti)

    def test_wizard(self, direttore_loggato):
        client, _ = direttore_loggato
        html = client.get(url_for("admin.campionato.wizard_start")).get_data(
            as_text=True
        )
        assert _config_screen(html) == "admin.campionato.wizard_start"
        in_pagina = _anchors_in_pagina(html)
        assert {"prova-spunta", "campionato-gare-pianificate"} <= in_pagina
        serviti = _anchors_serviti(client, "admin.campionato.wizard_start")
        assert in_pagina <= serviti, sorted(in_pagina - serviti)
        # La presentazione del wizard esiste: e' la schermata da cui un
        # direttore nuovo comincia.
        assert client.get(
            url_for("help.screen_api", screen="admin.campionato.wizard_start")
        ).get_json()["tour"]


class TestGaraNuova:
    def test_spunta_della_prova(self, direttore_loggato):
        client, _ = direttore_loggato
        html = client.get(url_for("admin.competition.create_gara_standalone")).get_data(
            as_text=True
        )
        in_pagina = _anchors_in_pagina(html)
        assert "prova-spunta" in in_pagina
        serviti = _anchors_serviti(client, "admin.competition.create_gara_standalone")
        assert in_pagina <= serviti, sorted(in_pagina - serviti)


class TestSottopagineDellaProva:
    """Preparazione e «Impostazioni gara» sono pagine a se': fino al
    2026-09-13 non includevano il banner, quindi li' la modalita' aiuto non
    si accendeva e «Elimina la prova» non c'era."""

    @pytest.mark.parametrize(
        "endpoint, extra",
        [
            ("admin.competition.gara_preparazione", {"passo": "tavoli"}),
            ("admin.competition.gara_impostazioni", {}),
        ],
    )
    def test_il_banner_accende_l_aiuto(self, direttore_loggato, endpoint, extra):
        client, direttore = direttore_loggato
        gara_id = _prova(direttore).id
        _pulisci_stato_fra_richieste()
        html = client.get(url_for(endpoint, gara_id=gara_id, **extra)).get_data(
            as_text=True
        )
        assert "data-help-toggle" in html
        assert html.count("data-help-toggle") == 1, "un banner solo"
        assert _config_screen(html) == endpoint
        in_pagina = _anchors_in_pagina(html)
        assert {"prova-aiuto", "prova-elimina"} <= in_pagina
        serviti = _anchors_serviti(client, endpoint)
        assert in_pagina <= serviti, sorted(in_pagina - serviti)

    @pytest.mark.parametrize(
        "endpoint, extra",
        [
            ("admin.competition.gara_preparazione", {"passo": "tavoli"}),
            ("admin.competition.gara_impostazioni", {}),
        ],
    )
    def test_una_gara_vera_non_ha_l_interruttore(
        self, direttore_loggato, endpoint, extra
    ):
        client, direttore = direttore_loggato
        vera = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Vera",
            date=date.today() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            director_id=direttore.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db.session.commit()
        vera_id = vera.id
        _pulisci_stato_fra_richieste()
        html = client.get(url_for(endpoint, gara_id=vera_id, **extra)).get_data(
            as_text=True
        )
        assert "data-help-toggle" not in html
