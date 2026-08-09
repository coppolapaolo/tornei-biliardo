"""Integration test del leaderboard locale/contributo (ADR-037).

Verifica il rendering della pagina riorientata (tab Zona + Contributo) per
anonimo e per giocatore loggato con home_city. App context aperto per tutto il
test (cfr. test_geo_proximity.py) contro il DetachedInstanceError.
"""

import uuid

import pytest

from models import db, User
from models.user.role_enum import UserRole
from models.gamification.models import UserLevel


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(home_city=None, total_xp=None):
    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=UserRole.PLAYER.value,
        home_city=home_city,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    if total_xp is not None:
        db.session.add(UserLevel(user_id=u.id, total_xp=total_xp))
        db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


@pytest.mark.integration
class TestLeaderboardPage:
    def test_anonymous_sees_tabs_and_login_prompt(self, app):
        client = app.test_client()
        resp = client.get("/gamification/leaderboards")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Contributo" in body
        assert "La tua zona" in body
        # tab locale invita l'anonimo ad accedere (il redesign 7c ha spezzato
        # la frase in titolo + spiegazione dello stato vuoto)
        assert "Accedi per vedere la tua zona" in body

    def test_non_numeric_limit_does_not_500(self, app):
        # Regressione: un ?limit non numerico non deve generare un 500
        # (int('abc') → ValueError). Parse difensivo con fallback al default.
        client = app.test_client()
        resp = client.get("/gamification/leaderboards?limit=abc")
        assert resp.status_code == 200
        # anche valori fuori range o negativi sono tollerati
        assert client.get("/gamification/leaderboards?limit=-5").status_code == 200
        assert client.get("/gamification/leaderboards?limit=99999").status_code == 200

    def test_logged_in_local_board_lists_zone(self, app):
        viewer = _user(home_city="Napoli", total_xp=100)
        _user(home_city="Napoli", total_xp=500)
        viewer_id = viewer.id
        client = app.test_client()
        _login(client, viewer)

        resp = client.get("/gamification/leaderboards")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Napoli" in body  # zone label
        # il visitatore è elencato
        viewer_username = db.session.get(User, viewer_id).username
        assert viewer_username in body


@pytest.mark.integration
class TestKpiPerformanceTab:
    def test_performance_tab_renders(self, app):
        admin = User(
            username=f"adm_{uuid.uuid4().hex[:8]}",
            email=f"adm_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("pw123456")
        db.session.add(admin)
        db.session.commit()

        client = app.test_client()
        _login(client, admin)
        resp = client.get("/admin/kpi/?tab=performance")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Performance" in body
        assert "Contributori" in body
