"""La home vista da chi non è entrato.

L'ospite non ha una `/dashboard`: `DashboardService.for_guest()` esiste ma
nessuna route la chiama, e `main.index` manda gli autenticati altrove. Quindi
`templates/index.html` **è** la dashboard dell'ospite, ed è lì che vale la
forma scelta il 30/08 — «ospite C»: si parte da quello che sta succedendo, e
l'account si chiede dove serve.

Tre regressioni presidiate qui:

* la pagina apriva con «Come si partecipa», cioè con l'ostacolo invece che con
  il contenuto;
* il pulsante diceva «Accedi per iscriverti» e non diceva che l'account è
  gratuito, cioè l'unica informazione che l'ostacolo lo toglie;
* la barra laterale chiamava «giocatore» chi non è entrato.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import utc_now
from models.competition.models import Gara
from models.status_enum import Discipline, GaraStatus


def _uid() -> str:
    return str(uuid.uuid4())[:8]


@pytest.fixture
def gara_aperta(db_session):
    gara = Gara(
        name=f"Gara Aperta {_uid()}",
        number=1,
        date=date.today() + timedelta(days=10),
        discipline=Discipline.NINE_BALL.value,
        status=GaraStatus.INSCRIPTION.value,
        distance=5,
        is_race_to=True,
        max_participants=24,
        min_participants=4,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=5),
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.mark.integration
def test_la_home_non_apre_piu_con_come_si_partecipa(client, gara_aperta):
    """Chi arriva vuole prima sapere se qui succede qualcosa.

    Il blocco resta — in fondo — ma non è più la prima cosa: la sezione delle
    iscrizioni aperte lo precede.
    """
    html = client.get("/").get_data(as_text=True)

    assert "Come si partecipa" in html, "il blocco non va cancellato, va spostato"
    assert "Iscrizioni aperte" in html
    assert html.index("Iscrizioni aperte") < html.index("Come si partecipa")


@pytest.mark.integration
def test_il_pulsante_dice_iscriviti_e_spiega_che_l_account_e_gratuito(
    client, gara_aperta
):
    html = client.get("/").get_data(as_text=True)

    assert "Accedi per iscriverti" not in html
    assert "Iscriviti" in html
    assert "account gratuito" in html


@pytest.mark.integration
def test_dopo_l_accesso_si_torna_alla_pagina_da_cui_si_era_partiti(client, gara_aperta):
    """Senza `next` si finisce in dashboard e la gara che interessava è persa."""
    html = client.get("/").get_data(as_text=True)

    assert "next=%2F" in html or "next=/" in html


@pytest.mark.integration
def test_chi_non_e_entrato_non_viene_chiamato_giocatore(client):
    """Il ramo `else` dava un ruolo a chi non ne ha nessuno."""
    html = client.get("/").get_data(as_text=True)

    assert "vista pubblica" in html
    # `giocatore` compare ancora in pagina — ad esempio in «14 giocatori» —
    # quindi si guarda il posto giusto: il sottotitolo del marchio.
    marchio = html.split("c7-side__role", 1)[1].split("</span>", 1)[0]
    assert "giocatore" not in marchio
