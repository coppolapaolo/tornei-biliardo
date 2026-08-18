"""Il blocco «Come stai andando» si mostra una volta per sessione.

E' un saluto, non un cruscotto: al primo ingresso in dashboard dopo il login
c'e', e da li' in poi lascia il posto alle cose da fare. Chi torna in dashboard
dieci volte in un pomeriggio non deve rileggere dieci volte com'e' andata.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from models import db
from models.base import utc_now
from models.individual_match.match_models import IndividualMatch
from models.status_enum import MatchStatus
from models.user.models import User

TITOLO = "Come stai andando"


def _opponent() -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"opp_{tag}", email=f"{tag}@example.test", role="player")
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _played(player: User, opponent: User, days_ago: int) -> None:
    when = utc_now() - timedelta(days=days_ago)
    db.session.add(
        IndividualMatch(
            player1_id=player.id,
            player2_id=opponent.id,
            scheduled_at=when,
            ended_at=when,
            status=MatchStatus.CONFIRMED_BY_BOTH,
            discipline="palla_9",
            distance=5,
            player1_score=5,
            player2_score=3,
            winner_id=player.id,
        )
    )
    db.session.commit()


def _home(client) -> str:
    return client.get("/dashboard").get_data(as_text=True)


def test_la_prima_volta_c_e_la_seconda_no(logged_in_client):
    client, user = logged_in_client(role="player")
    other = _opponent()
    for i in range(3):
        _played(user, other, 3 - i)

    assert TITOLO in _home(client)
    assert TITOLO not in _home(client)
    assert TITOLO not in _home(client)


def test_le_cose_da_fare_restano_a_ogni_visita(logged_in_client):
    """Sparisce il feedback, non la dashboard: il blocco non doveva mai
    coprire le attivita' da svolgere, e non deve portarsele via andandosene."""
    client, user = logged_in_client(role="player")
    other = _opponent()
    for i in range(3):
        _played(user, other, 3 - i)

    _home(client)
    seconda = _home(client)
    assert "I tuoi match" in seconda or "Gare" in seconda


def test_il_direttore_segue_la_stessa_regola(logged_in_client):
    client, user = logged_in_client(role="director")
    other = _opponent()
    for i in range(3):
        _played(user, other, 3 - i)

    assert TITOLO in _home(client)
    assert TITOLO not in _home(client)


def test_dopo_un_nuovo_login_il_saluto_torna(client, app):
    """«Una volta per sessione» vuol dire da questo login.

    `logout_user()` toglie dalla sessione solo le chiavi di Flask-Login: senza
    un azzeramento esplicito, chi esce e rientra dallo stesso browser non
    rivedrebbe il blocco.
    """
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"p_{tag}", email=f"{tag}@example.test", role="player")
    user.set_password("segreta123")
    db.session.add(user)
    db.session.commit()

    other = _opponent()
    for i in range(3):
        _played(user, other, 3 - i)

    def login():
        return client.post(
            "/auth/login",
            data={"username": user.username, "password": "segreta123"},
            follow_redirects=True,
        )

    # Il redirect dopo il login **e' gia'** la prima visita alla dashboard:
    # il saluto sta li', non nella pagina successiva.
    assert TITOLO in login().get_data(as_text=True)
    assert TITOLO not in _home(client)

    client.get("/auth/logout", follow_redirects=True)
    assert TITOLO in login().get_data(as_text=True)


def test_anche_la_card_di_setup_si_mostra_una_volta_sola(logged_in_client):
    """Il turno vale per il posto, non per il singolo componente.

    Chi non ha ancora fatto niente riceve i tre passi al posto del blocco: e'
    la stessa cosa vista da prima, e segue la stessa regola.
    """
    client, _user = logged_in_client(role="player")

    prima = _home(client)
    assert "Il tuo profilo" in prima
    assert "Il tuo Elo parte da 1200" in prima

    seconda = _home(client)
    assert "Il tuo profilo" not in seconda
    assert "Il tuo Elo parte da 1200" not in seconda
