"""L'avvio rapido dice a cosa si gioca prima di chiedere con chi.

Rilievo dell'utente del 12/11/2026: disciplina, distanza e sala stavano in una
scheda sotto l'avversario. Su un telefono finivano dietro il pulsante «Inizia
a segnare», e «Cambia» era una scritta piccola in un angolo: si partiva senza
aver letto a cosa si giocava.

Ora la prima scheda è «A cosa giocate», con una tessera per valore; ogni
tessera apre i propri campi.
"""

import uuid

import pytest
from flask import g

from models import User, db
from models.individual_match.models import IndividualMatch
from models.status_enum import Discipline
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _giocatore():
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"avvio_{uid}",
        email=f"avvio_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _pagina(app, user):
    g.pop("_login_user", None)
    risposta = _client_for(app, user).get("/match/quick")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def test_il_gioco_viene_prima_dell_avversario(app):
    html = _pagina(app, _giocatore())

    assert html.index("A cosa giocate") < html.index("Chi hai davanti")


def test_ogni_valore_ha_la_sua_tessera_e_il_suo_pannello(app):
    html = _pagina(app, _giocatore())

    for tessera in ("discipline", "format", "location", "opening"):
        assert f'data-tile="{tessera}"' in html
        assert f'id="panel-{tessera}"' in html
        assert f'aria-controls="panel-{tessera}"' in html


def test_la_disciplina_si_sceglie_fra_tutte(app):
    html = _pagina(app, _giocatore())

    for valore, _etichetta in Discipline.get_choices():
        assert f'name="discipline" value="{valore}"' in html


def test_i_campi_arrivano_al_servizio_come_prima(app):
    """I nomi dei campi non sono cambiati: la partita nasce coi valori scelti."""
    io, avversario = _giocatore(), _giocatore()

    g.pop("_login_user", None)
    risposta = _client_for(app, io).post(
        "/match/quick",
        data={
            "opponent_id": str(avversario.id),
            "discipline": Discipline.NINE_BALL.value,
            "match_format": "multi",
            "distance": "6",
            "match_distance": "3",
            "is_race_to": "true",
            "location": "Sala di prova",
        },
    )

    assert risposta.status_code == 302
    partita = IndividualMatch.query.one()
    assert partita.discipline == Discipline.NINE_BALL.value
    assert (partita.distance, partita.match_distance) == (6, 3)
    assert partita.location == "Sala di prova"
