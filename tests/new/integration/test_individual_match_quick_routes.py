"""Integration test dell'avvio rapido (issue #176).

Stessa impalcatura di ``test_individual_match_proposal_routes.py``: app context
aperto per tutto il test e cache utente di Flask-Login azzerata prima di ogni
richiesta (vedi la docstring di quel modulo).
"""

import uuid

import pytest
from flask import g

from models import User, db
from models.individual_match.models import IndividualMatch
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player(override=True):
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"q_{uid}",
        email=f"q_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=override,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


@pytest.mark.integration
class TestQuickMatchForm:
    def test_la_pagina_si_apre(self, app):
        player = _player()

        resp = _get(_client_for(app, player), "/match/quick")

        assert resp.status_code == 200
        assert "Avvio rapido" in resp.get_data(as_text=True)

    def test_l_avversario_del_link_arriva_preselezionato(self, app):
        player, opponent = _player(), _player()

        resp = _get(_client_for(app, player), f"/match/quick?opponent_id={opponent.id}")

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert f'value="{opponent.id}"' in body
        assert opponent.username in body

    def test_serve_l_autenticazione(self, app):
        resp = app.test_client().get("/match/quick")

        assert resp.status_code in (302, 401)


@pytest.mark.integration
class TestQuickMatchStart:
    def test_una_richiesta_sola_porta_al_segnapunti(self, app):
        player, opponent = _player(), _player()

        resp = _post(
            _client_for(app, player),
            "/match/quick",
            data={"opponent_id": str(opponent.id)},
        )

        assert resp.status_code == 302
        match = IndividualMatch.query.one()
        assert resp.headers["Location"].endswith(f"/match/matches/{match.id}")
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.proposal_id is None
        assert {match.player1_id, match.player2_id} == {player.id, opponent.id}

    def test_il_segnapunti_e_gia_aperto(self, app):
        """Nessun «Inizia la sfida» da premere: la partita e' gia' in corso."""
        player, opponent = _player(), _player()
        client = _client_for(app, player)
        _post(client, "/match/quick", data={"opponent_id": str(opponent.id)})
        match = IndividualMatch.query.one()

        resp = _get(client, f"/match/matches/{match.id}")

        assert resp.status_code == 200
        assert "Inizia la sfida" not in resp.get_data(as_text=True)

    def test_i_campi_del_modulo_vincono_sui_default(self, app):
        player, opponent = _player(), _player()

        _post(
            _client_for(app, player),
            "/match/quick",
            data={
                "opponent_id": str(opponent.id),
                "location": "Sala del Test",
                "discipline": Discipline.NINE_BALL.value,
                "match_format": "single",
                "distance": "3",
                "is_race_to": "false",
                "break_rule": "loser_breaks",
            },
        )

        match = IndividualMatch.query.one()
        assert match.location == "Sala del Test"
        assert match.discipline == Discipline.NINE_BALL.value
        assert match.distance == 3
        assert match.is_race_to is False
        assert match.break_rule == "loser_breaks"

    def test_senza_avversario_non_apre_niente(self, app):
        player = _player()

        resp = _post(_client_for(app, player), "/match/quick", data={})

        assert resp.status_code == 302
        assert IndividualMatch.query.count() == 0

    def test_senza_avversario_in_json_e_400(self, app):
        player = _player()

        resp = _post(_client_for(app, player), "/match/quick", json={})

        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_contro_se_stessi_in_json_e_422(self, app):
        player = _player()

        resp = _post(
            _client_for(app, player), "/match/quick", json={"opponent_id": player.id}
        )

        assert resp.status_code == 422
        assert IndividualMatch.query.count() == 0

    def test_il_doppio_invio_non_apre_due_partite(self, app):
        player, opponent = _player(), _player()
        client = _client_for(app, player)

        prima = _post(
            client, "/match/quick", json={"opponent_id": opponent.id}
        ).get_json()
        seconda = _post(
            client, "/match/quick", json={"opponent_id": opponent.id}
        ).get_json()

        assert prima["match_id"] == seconda["match_id"]
        assert IndividualMatch.query.count() == 1

    def test_l_avversario_la_trova_fra_le_sue_sfide(self, app):
        """Non ha accettato niente, ma la partita e' sua quanto dell'altro."""
        player, opponent = _player(), _player()
        _post(
            _client_for(app, player),
            "/match/quick",
            json={"opponent_id": opponent.id},
        )

        resp = _get(_client_for(app, opponent), "/match/matches")

        assert resp.status_code == 200
        assert player.username in resp.get_data(as_text=True)

    def test_l_avversario_viene_avvisato(self, app):
        from models.notification.models import Notification

        player, opponent = _player(), _player()
        _post(
            _client_for(app, player),
            "/match/quick",
            json={"opponent_id": opponent.id},
        )

        notifiche = Notification.query.filter_by(user_id=opponent.id).all()
        assert len(notifiche) == 1
        assert player.username in notifiche[0].message
