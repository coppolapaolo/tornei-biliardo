"""La pagina Sfide ha un solo ingresso all'avvio rapido, e si legge (issue #740).

Segnalazione di un utente: due pulsanti diversi portavano nello stesso posto,
e il titolo della tessera in cima non si leggeva. Il titolo era scuro su fondo
scuro per un `color:inherit` in linea, che scavalcava il colore della tessera.
"""

import re
import uuid

import pytest
from flask import g

from models import User, db
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _pagina(app):
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"sf740_{uid}",
        email=f"sf740_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    g.pop("_login_user", None)
    risposta = client.get("/match/")
    assert risposta.status_code == 200
    html = risposta.get_data(as_text=True)
    # Il contenuto della pagina, senza menu, testata e pannello di debug.
    return html[html.index("c7-sections") :]


def test_nel_contenuto_un_solo_collegamento_all_avvio_rapido(app):
    contenuto = _pagina(app)

    assert len(re.findall(r'href="/match/quick"', contenuto)) == 1


def test_la_tessera_prende_il_colore_del_suo_fondo(app):
    contenuto = _pagina(app)

    tessera = re.search(r'<a class="c7-card c7-card--accent[^>]*>', contenuto)
    assert tessera is not None
    assert "color:inherit" not in tessera.group(0)
