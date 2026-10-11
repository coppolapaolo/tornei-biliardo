"""La nuova gara del campionato a piazzamenti sceglie formato e sistema (ADR-080).

In un campionato a piazzamenti ogni serata può avere il suo formato (Amalfi,
casuale, girone a uno o più gironi, tabellone) e il suo sistema di classifica:
nel campionato entra il posto. Il modale «Nuova gara» lo permette, con le
proposte del campionato già scelte. In un campionato che somma i totali il
modale resta com'era: formato e sistema li impone il campionato.

Qui si inviano i campi che il modale manda davvero, coi nomi del modale; le
regole del parser hanno i loro unit test
(`tests/new/unit/test_nuova_gara_formato_a_piazzamenti.py`).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

import pytest

from models import Gara, User
from models.campionato.models import Campionato
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def direttore(db_session):
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


def _wizard(client, nome, sistema, tipo, sistema_gare=None):
    passo1 = {
        "name": nome,
        "planned_gare_count": "3",
        "campionato_type": tipo,
        "default_classification_system": sistema,
    }
    if sistema_gare:
        passo1["default_gara_classification_system"] = sistema_gare
    client.post("/admin/campionato/wizard/step2", data=passo1)
    # Senza la casella dell'anti-reincontro: il campionato non lo propone.
    client.post(
        "/admin/campionato/wizard/create",
        data={"default_odd_policy": "bye", "default_rounds_count": "3"},
        follow_redirects=True,
    )
    return Campionato.query.filter_by(name=nome).first()


def _dal_modale(client, camp, numero, **campi):
    """I campi che il modale manda, come li manda il browser."""
    dati = {
        "campionato_id": str(camp.id),
        "number": str(numero),
        "name": f"Serata {numero}",
        "date": (date.today() + timedelta(days=7 * numero)).isoformat(),
        "time": "20:00",
        "location": "",
        "available_tables": "",
        "min_participants": "4",
        "max_participants": "16",
        "entry_fee": "0",
        "discipline": "8_ball",
        "distance": "3",
        "rounds_count": "3",
        "withdraw_policy": "Forfeit",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "has_handicap": "",
        "weight": "1",
        "description": "",
    }
    dati.update(campi)
    return client.post("/admin/gara/create", data=dati, follow_redirects=True)


def _tag(pagina, id_):
    """Il tag di apertura dell'elemento con quell'id."""
    trovato = re.search(r"<[a-z]+[^>]*\bid=\"" + re.escape(id_) + r"\"[^>]*>", pagina)
    assert trovato, id_
    return trovato.group(0)


def _opzione_scelta(pagina, id_select):
    inizio = pagina.index(_tag(pagina, id_select))
    fine = pagina.index("</select>", inizio)
    scelta = re.search(r'<option value="([^"]*)"[^>]*\bselected\b', pagina[inizio:fine])
    return scelta.group(1) if scelta else None


def test_il_modale_a_piazzamenti_propone_formato_e_sistema(
    client, db_session, direttore
):
    _login(client, direttore)
    camp = _wizard(
        client, f"Piazzamenti {uuid.uuid4().hex[:6]}", "POSITION", "random", "RACK"
    )
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)

    # Le proposte del campionato sono già scelte.
    assert _opzione_scelta(pagina, "create_matchmaking_strategy") == "random"
    assert _opzione_scelta(pagina, "create_classification_system") == "RACK"
    # Tutti i formati, tabellone compreso.
    menu = pagina[pagina.index(_tag(pagina, "create_matchmaking_strategy")) :]
    menu = menu[: menu.index("</select>")]
    for formato in (
        "amalfi",
        "random",
        "round_robin",
        "direct_elimination",
        "double_knockout",
    ):
        assert f'value="{formato}"' in menu
    # Le opzioni del tabellone e i gironi seguono il formato scelto.
    assert 'id="create_bracket_options_section"' in pagina
    assert 'data-strategia-da="#create_matchmaking_strategy"' in pagina
    assert "strategia_gara.js" in pagina


def test_dal_modale_tre_serate_di_formato_diverso(client, db_session, direttore):
    _login(client, direttore)
    camp = _wizard(
        client,
        f"Lunedì {uuid.uuid4().hex[:6]}",
        "POSITION",
        "round_robin",
        "POINTS",
    )

    # Amalfi coi triangoli: il modale manda l'anti-reincontro acceso, che
    # Amalfi impone.
    _dal_modale(
        client,
        camp,
        1,
        matchmaking_strategy="amalfi",
        classification_system="RACK",
        odd_number_policy="no",
        anti_rematch_enabled="on",
    )
    # Girone a due gironi, a punti.
    _dal_modale(
        client,
        camp,
        2,
        matchmaking_strategy="round_robin",
        classification_system="POINTS",
        points_win="3",
        points_draw="1",
        points_loss="0",
        max_groups="2",
        group_seeding="sorteggio",
    )
    # Tabellone con la finalina: il sistema della serata, nascosto, arriva lo
    # stesso e il server impone il piazzamento.
    _dal_modale(
        client,
        camp,
        3,
        matchmaking_strategy="direct_elimination",
        classification_system="POINTS",
        third_place_match="on",
    )

    gare = {g.number: g for g in Gara.query.filter_by(campionato_id=camp.id)}
    assert set(gare) == {1, 2, 3}
    assert gare[1].matchmaking_strategy == "amalfi"
    assert gare[1].classification_system == "RACK"
    assert gare[1].anti_rematch_enabled is True
    assert gare[2].matchmaking_strategy == "round_robin"
    assert gare[2].classification_system == "POINTS"
    assert gare[2].max_groups == 2
    assert gare[3].matchmaking_strategy == "direct_elimination"
    assert gare[3].classification_system == "POSITION"
    assert gare[3].third_place_match is True


def test_amalfi_in_un_campionato_girone_senza_anti_reincontro(
    client, db_session, direttore
):
    """Il guasto: il modale non mandava l'anti-reincontro, e la gara non nasceva.

    Il campionato è un girone all'italiana e non propone l'anti-reincontro
    (nel girone non serve: ognuno incontra tutti una volta). La serata
    Amalfi lo richiede, e Amalfi lo impone acceso: la gara nasce con
    l'anti-reincontro, anche se il campo non arriva.
    """
    _login(client, direttore)
    camp = _wizard(
        client, f"Girone {uuid.uuid4().hex[:6]}", "POSITION", "round_robin", "WINS"
    )
    assert camp.default_anti_rematch is False

    _dal_modale(client, camp, 1, matchmaking_strategy="amalfi")

    gara = Gara.query.filter_by(campionato_id=camp.id).one()
    assert gara.matchmaking_strategy == "amalfi"
    assert gara.anti_rematch_enabled is True


def test_il_modale_di_un_campionato_a_vittorie_resta_com_era(
    client, db_session, direttore
):
    _login(client, direttore)
    camp = _wizard(client, f"Vittorie {uuid.uuid4().hex[:6]}", "WINS", "amalfi")
    pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)

    # Nessun menu di formato o di sistema, nessuna opzione del tabellone.
    assert 'id="create_matchmaking_strategy"' not in pagina
    assert 'id="create_classification_system"' not in pagina
    assert 'id="create_bracket_options_section"' not in pagina
    # Amalfi impone l'anti-reincontro: casella spenta, valore nascosto.
    assert '<input type="hidden" name="anti_rematch_enabled" value="on">' in pagina
    # I dispari offrono solo ciò che Amalfi ammette, come prima.
    assert _opzione_scelta(pagina, "create_odd_number_policy") == "bye"

    # Formato e sistema chiesti a mano non passano: decide il campionato.
    _dal_modale(
        client,
        camp,
        1,
        matchmaking_strategy="direct_elimination",
        classification_system="RACK",
        anti_rematch_enabled="on",
    )
    gara = Gara.query.filter_by(campionato_id=camp.id).one()
    assert gara.matchmaking_strategy == "amalfi"
    assert gara.classification_system == "WINS"
