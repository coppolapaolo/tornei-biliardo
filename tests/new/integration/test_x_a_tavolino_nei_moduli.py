"""I menu «giocatori dispari» dicono «X a tavolino», come la pagina della gara.

Il giunto fra `opzioni_dispari` e le schermate vere: il wizard del campionato
al passo 2, il modulo della gara singola, la modifica del campionato.
"""

from __future__ import annotations

import re
import uuid

import pytest

from models import Campionato, User
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def director(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _menu_dispari(pagina: str, nome_campo: str) -> str:
    inizio = pagina.index(f'name="{nome_campo}"')
    return pagina[inizio : pagina.index("</select>", inizio)]


def _passo1(sistema: str) -> dict:
    return {
        "name": f"Campionato {uuid.uuid4().hex[:6]}",
        "planned_gare_count": "3",
        "campionato_type": "amalfi",
        "default_classification_system": sistema,
    }


def test_wizard_passo2_mostra_la_x_a_tavolino(client, director):
    _login(client, director)
    pagina = client.post("/admin/campionato/wizard/step2", data=_passo1("WINS"))
    assert pagina.status_code == 200
    menu = _menu_dispari(pagina.get_data(as_text=True), "default_odd_policy")

    assert re.search(r'value="bye"\s+selected>X a tavolino<', menu)
    assert "X a tavolino con esercizio" in menu
    assert "Trio, partita a tre" in menu
    assert "Bye" not in menu and "match" not in menu.lower()


def test_wizard_passo2_col_sistema_rack_toglie_la_x_semplice(client, director):
    _login(client, director)
    pagina = client.post("/admin/campionato/wizard/step2", data=_passo1("RACK"))
    menu = _menu_dispari(pagina.get_data(as_text=True), "default_odd_policy")

    assert 'value="bye"' not in menu
    assert "X a tavolino con esercizio" in menu


def test_la_gara_singola_propone_la_x_a_tavolino(client, director):
    _login(client, director)
    pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
    menu = _menu_dispari(pagina, "odd_number_policy")

    # La X resta la scelta predefinita anche ora che non e' la prima voce.
    assert re.search(r'value="bye"\s+selected>X a tavolino<', menu)
    assert "Riposo" not in menu and "Match a 3" not in menu


def test_la_modifica_del_campionato_ritrova_la_lista_d_attesa(
    client, db_session, director
):
    """Il menu della modifica non aveva la voce «lista d'attesa»: un campionato
    nato cosi' si apriva con la X preselezionata, e salvare la cambiava in
    silenzio."""
    campionato = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system="WINS",
        default_odd_policy="no",
    )
    db_session.add(campionato)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=campionato.id,
            user_id=director.id,
            assigned_by_id=director.id,
        )
    )
    db_session.commit()
    _login(client, director)

    pagina = client.get(f"/admin/campionato/{campionato.id}/edit").get_data(
        as_text=True
    )
    menu = _menu_dispari(pagina, "default_odd_policy")

    # Jinja scrive l'apostrofo come entita' HTML.
    assert re.search(r'value="no"\s+selected>\s*Lista d(&#39;|\')attesa\s*<', menu)
    assert "X a tavolino" in menu and "Challenge" not in menu
