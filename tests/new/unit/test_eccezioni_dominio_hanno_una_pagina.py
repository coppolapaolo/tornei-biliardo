"""Un'eccezione di dominio che arriva alla route non e' un guasto del server.

Due issue GlitchTip, stessa radice:

- `TORNEI-BILIARDO-5V` — `ValueError: Campionato not found` da
  `admin.campionato.campionato_detail`. La route non ha `try`, quindi un id
  inesistente dava **500** invece di 404.
- `TORNEI-BILIARDO-64` — `ConflictError: Iscrizioni chiuse` sfuggita da
  `inscribe_user`: «Errore interno del server» a chi aveva premuto un
  pulsante un minuto dopo la chiusura, piu' un evento su GlitchTip a
  consumare quota per un rifiuto previsto.

Le route AJAX la mappatura ce l'avevano gia' (`safe_json_error` passa da
`http_status_for_exception`); le pagine HTML no. Il gestore registrato in
`create_app` la estende a tutte.

L'app di prova e' costruita qui e non presa dalla fixture di sessione perche'
serve registrare delle route: Flask le rifiuta dopo la prima richiesta servita,
e la fixture di sessione ne ha gia' servite.
"""

import pytest
from flask import Blueprint
from sqlalchemy.pool import StaticPool

from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


@pytest.fixture(scope="module")
def client_con_trabocchetti():
    """Un'app vera con una route per ogni famiglia di eccezione."""
    from app import create_app
    from models import db

    flask_app = create_app("testing")
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_ENGINE_OPTIONS={
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        SERVER_NAME="localhost",
    )

    trabocchetti = Blueprint("trabocchetti", __name__)

    @trabocchetti.route("/non-trovato")
    def non_trovato():
        raise NotFoundError("Campionato not found")

    @trabocchetti.route("/conflitto")
    def conflitto():
        raise ConflictError("Iscrizioni chiuse")

    @trabocchetti.route("/non-valido")
    def non_valido():
        raise ValidationError("Il punteggio supera la distanza")

    @trabocchetti.route("/vietato")
    def vietato():
        raise PermissionDeniedError("Admin non può partecipare ai tornei")

    flask_app.register_blueprint(trabocchetti)

    with flask_app.app_context():
        db.create_all()
        yield flask_app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.mark.unit
@pytest.mark.parametrize(
    "percorso, atteso",
    [
        ("/non-trovato", 404),
        ("/conflitto", 409),
        ("/non-valido", 422),
        ("/vietato", 403),
    ],
)
def test_ogni_eccezione_di_dominio_ha_il_suo_stato(
    client_con_trabocchetti, percorso, atteso
):
    """Prima erano tutte 500, cioe' «e' colpa nostra» anche quando non lo era."""
    risposta = client_con_trabocchetti.get(percorso)
    assert risposta.status_code == atteso


@pytest.mark.unit
def test_il_conflitto_dice_a_chi_legge_cosa_e_successo(client_con_trabocchetti):
    """Il messaggio dell'eccezione e' scritto per l'utente, non per il log."""
    corpo = client_con_trabocchetti.get("/conflitto").get_data(as_text=True)
    assert "Iscrizioni chiuse" in corpo
    assert "Errore interno del server" not in corpo


@pytest.mark.unit
def test_le_chiamate_ajax_ricevono_json_non_una_pagina(client_con_trabocchetti):
    """Chi chiede JSON non sa cosa farsene di un `<html>`."""
    risposta = client_con_trabocchetti.get(
        "/conflitto", headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert risposta.status_code == 409
    assert risposta.get_json() == {"success": False, "error": "Iscrizioni chiuse"}


@pytest.mark.unit
def test_il_non_trovato_di_dominio_usa_la_pagina_del_404(client_con_trabocchetti):
    """Un campionato inesistente non deve sembrare diverso da un indirizzo sbagliato."""
    corpo = client_con_trabocchetti.get("/non-trovato").get_data(as_text=True)
    assert "Tiro sbagliato" in corpo
