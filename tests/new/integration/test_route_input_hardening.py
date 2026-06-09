"""Regression (review 2026-06-09): route che sollevavano 500 su input grezzo.

- /gamification/leaderboards?limit=<non-numerico>: `int(...)` su query param
  grezzo su route PUBBLICA → 500 banalmente innescabile (DoS).
- /rating/handicap/calculate (JSON): `data.get("rule_id", type=int)` su un dict
  solleva TypeError (non catturato da except ValueError) → 500; idem KeyError su
  player1_id/player2_id mancanti.
- /challenges/x-replacement/<g>/<r> (JSON): `data.get("challenge_id", type=int)`
  stesso TypeError → 500.

Dopo il fix questi path ritornano risposte controllate (200 / 4xx), mai 500.
"""

import pytest

from models import db, User


@pytest.fixture
def player_user(app):
    with app.app_context():
        user = User(
            username="hard_player",
            email="hard_player@example.com",
            password_hash="x",
            role="player",
        )
        db.session.add(user)
        db.session.commit()
        yield user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)


def test_leaderboards_non_numeric_limit_no_500(client):
    """Route pubblica: limit non numerico non deve dare 500."""
    resp = client.get("/gamification/leaderboards?limit=abc")
    assert resp.status_code != 500


def test_leaderboards_negative_limit_no_500(client):
    resp = client.get("/gamification/leaderboards?limit=-5")
    assert resp.status_code != 500


def test_handicap_calculate_json_missing_players_no_500(client, player_user):
    """JSON senza player ids: 4xx controllato, non TypeError/KeyError → 500."""
    _login(client, player_user)
    resp = client.post("/rating/handicap/calculate", json={})
    assert resp.status_code != 500
    assert resp.status_code in (400, 422)


def test_handicap_calculate_json_with_rule_id_no_typeerror(client, player_user):
    """rule_id in JSON non deve sollevare TypeError dal kwarg type=int."""
    _login(client, player_user)
    resp = client.post(
        "/rating/handicap/calculate",
        json={"player1_id": player_user.id, "player2_id": player_user.id, "rule_id": 1},
    )
    # Può essere 200 o 400 a seconda della regola, MAI 500.
    assert resp.status_code != 500


def test_x_replacement_json_invalid_challenge_id_no_500(client, player_user):
    """challenge_id in JSON non deve sollevare TypeError → 500."""
    _login(client, player_user)
    resp = client.post(
        "/challenges/x-replacement/999999/1",
        json={"challenge_id": "not-a-number"},
    )
    assert resp.status_code != 500
