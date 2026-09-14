"""Il direttore che **non** dirige un campionato ne vede comunque le gare.

Segnalazione di un utente (14/09/2026): iscritto alla gara 3 della Prima
Rōnin CUP, sulla tessera aveva solo «Disiscriviti» e nessun modo di arrivare
all'elenco degli iscritti. Aveva ruolo direttore, ma non dirigeva quel
campionato: `build_unified_items` dava `can_view_details = is_co_director`,
cioè falso, e la tessera nascondeva «Dettagli» — mentre la pagina della gara
è aperta a chiunque, anonimo compreso (ADR-028). Lo stesso flag spegneva
«Classifica e risultati» sulla tessera del campionato.

La regola risaliva al refactor del 07/02/2026, quando la pagina non era
ancora unificata. Un giocatore con lo stesso posto vedeva il pulsante.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from flask import url_for

from models.campionato.tournament_service import TournamentService
from models.competition.inscription_service import InscriptionService
from models.competition.services import GaraService
from models.dashboard.services import DashboardService
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _direttore(db_session, prefisso: str) -> User:
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _campionato_con_gara_aperta(db_session, titolare: User):
    campionato = TournamentService().create_campionato_with_director(
        name=f"Cup {uuid.uuid4().hex[:6]}",
        creator_user_id=titolare.id,
        campionato_type="amalfi",
    )
    gara = GaraService.create_gara(
        campionato_id=campionato.id,
        number=1,
        name="Gara 1",
        date=date.today() + timedelta(days=7),
        location="Sala",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
    )
    gara.status = GaraStatus.INSCRIPTION.value
    db_session.commit()
    return campionato, gara


def test_il_direttore_non_titolare_puo_vedere_i_dettagli(db_session):
    titolare = _direttore(db_session, "titolare")
    altro = _direttore(db_session, "altro")
    campionato, gara = _campionato_con_gara_aperta(db_session, titolare)
    InscriptionService.inscribe_user(altro.id, gara.id)

    vm = DashboardService.for_director(altro.id)

    voce = next(
        i for i in vm.unified_items if i.type == "campionato" and i.id == campionato.id
    )
    assert voce.can_manage is False
    assert voce.can_view_details is True

    assert vm.gare is not None
    tessera = next(c for c in vm.gare.mie if c.id == gara.id)
    assert tessera.can_manage is False
    assert tessera.can_view_details is True


def test_la_tessera_del_direttore_non_titolare_ha_dettagli(app, client, db_session):
    """Il login va fatto **dopo** il setup: i servizi leggono `current_user`
    fuori da una richiesta, e in questa suite ciò rende anonime le richieste
    successive del client (vedi `_simula_richiesta_nuova` nei test del
    recupero password)."""
    titolare = _direttore(db_session, "titolare")
    altro = _direttore(db_session, "altro")
    campionato, gara = _campionato_con_gara_aperta(db_session, titolare)
    InscriptionService.inscribe_user(altro.id, gara.id)

    client.post(
        "/auth/login",
        data={"username": altro.username, "password": "test1234"},
        follow_redirects=True,
    )
    risposta = client.get("/dashboard")
    assert risposta.status_code == 200, risposta.headers.get("Location")
    html = risposta.get_data(as_text=True)

    with app.test_request_context():
        pagina_gara = url_for("admin.competition.gara_detail", gara_id=gara.id)
        pagina_campionato = url_for(
            "main.campionato_detail_public", campionato_id=campionato.id
        )
    assert f'href="{pagina_gara}"' in html, "manca «Dettagli» sulla tessera della gara"
    assert f'href="{pagina_campionato}"' in html, "manca «Classifica e risultati»"
