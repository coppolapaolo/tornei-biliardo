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


# Qui c'erano due test su `/rating/handicap/calculate` (input JSON malformato
# che non deve dare 500). L'endpoint e tutto il blueprint `/rating` sono stati
# rimossi (ADR-049): erano irraggiungibili, senza template e senza entry
# nell'allowlist di produzione. Una route che non esiste non ha input da
# irrobustire.


def test_x_replacement_json_invalid_challenge_id_no_500(client, player_user):
    """challenge_id in JSON non deve sollevare TypeError → 500."""
    _login(client, player_user)
    resp = client.post(
        "/challenges/x-replacement/999999/1",
        json={"challenge_id": "not-a-number"},
    )
    assert resp.status_code != 500
