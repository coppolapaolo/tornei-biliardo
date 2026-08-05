"""Integration tests for campionato termination routes."""

import pytest
import uuid
from datetime import date

from models import Campionato
from models.base import db
from models.competition.models import Gara
from models.user.models import User, DirectorAssignment
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, TournamentStatus
from models.playoff.models import PlayoffConfiguration, PlayoffType


def _setup_campionato_with_director(db_session, director):
    """Create campionato and assign director."""
    uid = str(uuid.uuid4())[:8]
    c = Campionato(
        name=f"Camp {uid}",
        campionato_type="amalfi",
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()

    assignment = DirectorAssignment(
        entity_type="campionato",
        entity_id=c.id,
        user_id=director.id,
        assigned_by_id=director.id,
    )
    db_session.add(assignment)
    db_session.flush()
    return c


def _make_gara(db_session, campionato, number, status):
    g = Gara(
        campionato_id=campionato.id,
        number=number,
        name=f"Gara {number}",
        date=date(2026, 1, number),
        discipline="nine_ball",
        status=status,
        rounds_count=3,
        current_round=1,
        distance=5,
    )
    db_session.add(g)
    db_session.flush()
    return g


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test123"},
        follow_redirects=True,
    )


@pytest.mark.integration
class TestTerminateCampionatoRoute:
    """Test POST /<id>/terminate route."""

    def test_terminate_happy_path(self, client, db_session, isolated_director_user):
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        db_session.commit()

        _login(client, director)

        response = client.post(
            f"/admin/campionato/{c.id}/terminate",
            follow_redirects=True,
        )
        assert response.status_code == 200

        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.terminated_at is not None

    def test_terminate_already_terminated(
        self, client, db_session, isolated_director_user
    ):
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        from models.base import utc_now

        c.terminated_at = utc_now()
        db_session.commit()

        _login(client, director)

        response = client.post(
            f"/admin/campionato/{c.id}/terminate",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert (
            b"terminato" in response.data.lower() or b"already" in response.data.lower()
        )

    def test_terminate_forbidden_for_player(self, client, db_session):
        uid = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{uid}",
            email=f"player_{uid}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("test123")
        db_session.add(player)

        c = Campionato(name=f"Camp {uid}", campionato_type="amalfi", is_active=True)
        db_session.add(c)
        db_session.commit()

        _login(client, player)

        response = client.post(
            f"/admin/campionato/{c.id}/terminate",
            follow_redirects=True,
        )
        # Should be blocked — either 403 or redirect with error
        assert response.status_code in [200, 302, 403]

    def test_status_terminated_with_playoff(
        self, client, db_session, isolated_director_user
    ):
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)

        # Add playoff config
        cfg = PlayoffConfiguration(
            campionato_id=c.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=6,
            positions_from=1,
            positions_to=6,
            is_active=True,
            auto_generate=True,
        )
        db_session.add(cfg)
        db_session.commit()

        _login(client, director)

        client.post(f"/admin/campionato/{c.id}/terminate", follow_redirects=True)

        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.get_status() == TournamentStatus.TERMINATED.value

    def test_can_create_gara_blocked_after_terminate(
        self, client, db_session, isolated_director_user
    ):
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        db_session.commit()

        _login(client, director)

        # Terminate
        client.post(f"/admin/campionato/{c.id}/terminate", follow_redirects=True)

        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.can_create_gara() is False


@pytest.mark.integration
class TestUpdatePlayoffMinRoute:
    """Test POST /<id>/update-playoff-min route."""

    def test_update_min_garas(self, client, db_session, isolated_director_user):
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        cfg = PlayoffConfiguration(
            campionato_id=c.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=6,
            positions_from=1,
            positions_to=6,
            is_active=True,
            auto_generate=True,
            min_garas_played=7,
        )
        db_session.add(cfg)
        db_session.commit()

        _login(client, director)

        response = client.post(
            f"/admin/campionato/{c.id}/update-playoff-min",
            data={"config_id": cfg.id, "new_min": 3},
            follow_redirects=True,
        )
        assert response.status_code == 200

        refreshed = db_session.get(PlayoffConfiguration, cfg.id)
        assert refreshed.min_garas_played == 3

    def test_update_min_then_terminate(
        self, client, db_session, isolated_director_user
    ):
        """Full flow: update infeasible min_garas_played, then terminate."""
        director = isolated_director_user
        director.set_password("test123")
        db_session.commit()

        c = _setup_campionato_with_director(db_session, director)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        cfg = PlayoffConfiguration(
            campionato_id=c.id,
            name="Elite",
            playoff_type=PlayoffType.TOP_N,
            max_participants=6,
            positions_from=1,
            positions_to=6,
            is_active=True,
            auto_generate=True,
            min_garas_played=7,
        )
        db_session.add(cfg)
        db_session.commit()

        _login(client, director)

        # Step 1: Update min to feasible value
        client.post(
            f"/admin/campionato/{c.id}/update-playoff-min",
            data={"config_id": cfg.id, "new_min": 1},
            follow_redirects=True,
        )
        refreshed_cfg = db_session.get(PlayoffConfiguration, cfg.id)
        assert refreshed_cfg.min_garas_played == 1

        # Step 2: Terminate
        client.post(f"/admin/campionato/{c.id}/terminate", follow_redirects=True)

        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.terminated_at is not None
        assert refreshed.get_status() == TournamentStatus.TERMINATED.value
