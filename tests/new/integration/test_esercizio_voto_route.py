"""Il voto dalla scheda dell'esercizio (fase 4d, D6)."""

from __future__ import annotations

import uuid

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeRating
from models.user.models import User
from models.user.role_enum import UserRole

AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _utente() -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{suffix}",
        email=f"u_{suffix}@test.local",
        role=UserRole.PLAYER.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = db.session.get(User, user_id).get_id()
        session["_fresh"] = True


def _esercizio(provato_da=None) -> int:
    c = Challenge(
        title=f"Voto {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="x.png",
        pass_fail_only=False,
        is_active=True,
    )
    db.session.add(c)
    db.session.commit()
    if provato_da:
        # A mano e non dal servizio: gli handler della gamification leggono
        # `current_user` fuori da una richiesta e le richieste dopo risultano
        # anonime (memoria di progetto sul leak di Flask-Login nei test).
        db.session.add(
            ChallengeAttempt(
                user_id=provato_da, challenge_id=c.id, score=3, completed=True
            )
        )
        db.session.commit()
    return c.id


def test_chi_ha_provato_trova_le_bilie_e_vota(app, client):
    with app.app_context():
        player = _utente()
        cid = _esercizio(provato_da=player)
    _login(client, player)

    scheda = client.get(f"/challenges/{cid}").get_data(as_text=True)
    assert "data-rating" in scheda and 'data-ball="5"' in scheda

    risposta = client.post(f"/challenges/{cid}/rate", json={"rating": 4}, headers=AJAX)
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    corpo = risposta.get_json()
    assert (corpo["rating"], corpo["rating_count"], corpo["rating_average"]) == (
        4,
        1,
        4,
    )

    dopo = client.get(f"/challenges/{cid}").get_data(as_text=True)
    assert 'data-rating-value="4"' in dopo
    assert "4,0" in dopo  # in testata, accanto ai giocatori


def test_un_voto_vuoto_lo_toglie(app, client):
    with app.app_context():
        player = _utente()
        cid = _esercizio(provato_da=player)
    _login(client, player)
    client.post(f"/challenges/{cid}/rate", json={"rating": 5}, headers=AJAX)
    corpo = client.post(
        f"/challenges/{cid}/rate", json={"rating": None}, headers=AJAX
    ).get_json()
    assert corpo["rating"] is None and corpo["rating_count"] == 0
    with app.app_context():
        assert ChallengeRating.query.filter_by(challenge_id=cid).count() == 0


def test_chi_non_ha_provato_non_vede_le_bilie_e_non_vota(app, client):
    with app.app_context():
        player = _utente()
        cid = _esercizio()
    _login(client, player)

    scheda = client.get(f"/challenges/{cid}").get_data(as_text=True)
    assert "data-ball=" not in scheda
    assert "Provalo almeno una volta per poterlo votare" in scheda

    risposta = client.post(f"/challenges/{cid}/rate", json={"rating": 5}, headers=AJAX)
    assert risposta.status_code == 403
    with app.app_context():
        assert ChallengeRating.query.filter_by(challenge_id=cid).count() == 0


def test_un_voto_fuori_scala_e_422(app, client):
    with app.app_context():
        player = _utente()
        cid = _esercizio(provato_da=player)
    _login(client, player)
    risposta = client.post(f"/challenges/{cid}/rate", json={"rating": 9}, headers=AJAX)
    assert risposta.status_code == 422
