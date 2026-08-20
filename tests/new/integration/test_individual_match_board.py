"""Il tabellone orizzontale sulle sfide individuali (issue #170).

Il componente era pensato fin dall'inizio per tutt'e due i tipi di partita
(«match: Match o IndividualMatch», dice la sua intestazione), ma la pagina
della sfida individuale non lo includeva: girare il telefono, lì, non dava
niente. Questi test presidiano l'inclusione e le due condizioni che la
governano — chi guarda dev'essere uno dei due giocatori, e il referto TPA, se
aperto, resta l'unico segnapunti (ADR-044).
"""

import uuid
from datetime import timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.individual_match.models import IndividualMatch
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player():
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"b_{uid}",
        email=f"b_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _match_in_corso(player1, player2, **kwargs):
    defaults = dict(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Sala Test",
        scheduled_at=utc_now() - timedelta(minutes=10),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
    )
    defaults.update(kwargs)
    match = IndividualMatch(**defaults)
    match.started_at = utc_now()
    db.session.add(match)
    db.session.commit()
    return match


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


META_TOCCABILE = 'class="c7-board__side c7-board__side--tap"'


@pytest.mark.integration
class TestTabelloneSullaSfidaIndividuale:
    def test_chi_gioca_ha_il_tabellone(self, app):
        player1, player2 = _player(), _player()
        match = _match_in_corso(player1, player2)

        body = _get(
            _client_for(app, player1), f"/match/matches/{match.id}"
        ).get_data(as_text=True)

        assert 'id="matchBoard"' in body
        assert body.count(META_TOCCABILE) == 2

    def test_le_meta_chiamano_il_segnapunti_di_questa_pagina(self, app):
        """Il tabellone non ha endpoint suoi: passa dalle funzioni della pagina."""
        player1, player2 = _player(), _player()
        match = _match_in_corso(player1, player2)

        body = _get(
            _client_for(app, player1), f"/match/matches/{match.id}"
        ).get_data(as_text=True)

        assert f"addRack({player1.id}, this)" in body
        assert f"addRack({player2.id}, this)" in body
        assert "function addRack(" in body

    def test_a_distanza_raggiunta_le_meta_cedono_il_posto(self, app):
        player1, player2 = _player(), _player()
        match = _match_in_corso(player1, player2, player1_score=5, player2_score=2)

        body = _get(
            _client_for(app, player1), f"/match/matches/{match.id}"
        ).get_data(as_text=True)

        assert META_TOCCABILE not in body
        assert 'id="matchBoard"' in body

    def test_col_referto_tpa_aperto_il_tabellone_sparisce(self, app):
        """Due segnapunti sullo stesso match si contraddicono al primo tocco.

        Col referto aperto il punteggio **discende** dal referto (ADR-044):
        sparisce il segnapunti verticale, e deve sparire anche il tabellone.
        """
        from models.tpa.models import TpaReferto
        from models.tpa.services import TpaRefertoService

        player1, player2 = _player(), _player()
        match = _match_in_corso(player1, player2, discipline=Discipline.NINE_BALL.value)
        db.session.add(
            TpaReferto(
                individual_match_id=match.id,
                compiler_id=player1.id,
                game_type=TpaRefertoService.game_type_for(match.discipline),
            )
        )
        db.session.commit()

        body = _get(
            _client_for(app, player1), f"/match/matches/{match.id}"
        ).get_data(as_text=True)

        assert 'id="matchBoard"' not in body

    def test_partita_non_ancora_iniziata_niente_tabellone(self, app):
        player1, player2 = _player(), _player()
        match = _match_in_corso(player1, player2, status=MatchStatus.SCHEDULED)

        body = _get(
            _client_for(app, player1), f"/match/matches/{match.id}"
        ).get_data(as_text=True)

        assert 'id="matchBoard"' not in body
