"""Integration tests for playoff routes (start, confirm/decline, create gara)."""

import pytest
import uuid
from datetime import date

from models import Campionato, db
from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.classification.models import Classification
from models.status_enum import Discipline, GaraStatus
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.user.models import User


def _uid():
    return str(uuid.uuid4())[:8]


@pytest.fixture
def admin_user(db_session):
    u = User(username=f"admin_{_uid()}", email=f"admin_{_uid()}@t.com", role="admin")
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def player_user(db_session):
    u = User(username=f"player_{_uid()}", email=f"player_{_uid()}@t.com", role="player")
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def terminated_campionato_with_playoff(db_session, admin_user):
    """Campionato TERMINATED with Elite config (pos 1-6) and 8 classified players."""
    c = Campionato(name=f"Camp {_uid()}", campionato_type="amalfi", is_active=True)
    db_session.add(c)
    db_session.flush()

    gara = Gara(
        campionato_id=c.id,
        number=1,
        name="Gara 1",
        date=date(2026, 1, 15),
        discipline=Discipline.NINE_BALL.value,
        status=GaraStatus.COMPLETED.value,
        rounds_count=3,
        current_round=1,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()

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
    db_session.flush()

    players = []
    for i in range(8):
        p = User(username=f"p{_uid()}", email=f"p{_uid()}@t.com", role="player")
        p.set_password("test1234")
        db_session.add(p)
        db_session.flush()
        Classification(
            campionato_id=c.id,
            user_id=p.id,
            position=i + 1,
            total_matches_won=10 - i,
            total_point_difference=20 - i,
            gare_played=5,
        )
        db_session.add(
            Classification(
                campionato_id=c.id,
                user_id=p.id,
                position=i + 1,
                total_matches_won=10 - i,
                total_point_difference=20 - i,
                gare_played=5,
            )
        )
        db_session.add(Inscription(user_id=p.id, gara_id=gara.id))
        players.append(p)

    c.terminated_at = utc_now()
    db_session.commit()
    return c, cfg, players, gara


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


class TestStartPlayoffRoute:
    def test_admin_can_start_playoff(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True
        )
        assert resp.status_code == 200

        quals = PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()
        assert len(quals) == 6

    def test_player_cannot_start_playoff(
        self, client, db_session, player_user, terminated_campionato_with_playoff
    ):
        c, _, _, _ = terminated_campionato_with_playoff
        _login(client, player_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True
        )
        # Should be forbidden or redirected
        assert resp.status_code in (403, 200)  # 200 if redirected with flash
        quals = PlayoffQualification.query.all()
        assert len(quals) == 0

    def test_start_playoff_already_started(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)
        resp = client.post(
            f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True
        )
        assert resp.status_code == 200  # Redirected with flash error
        assert b"avviati" in resp.data or b"error" in resp.data.lower()


class TestPlayerConfirmDeclineRoute:
    def test_player_can_view_invitation_page(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        """Bug 15: la pagina di invito (target dell'action_url della notifica)
        è raggiungibile dal player e mostra i bottoni Conferma/Rifiuto."""
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)
        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)

        player = players[0]
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=player.id
        ).first()

        _login(client, player)
        resp = client.get(f"/player/playoff/invitation/{qual.id}")
        assert resp.status_code == 200
        # I due form di azione devono essere presenti
        assert f"/player/playoff/confirm/{qual.id}".encode() in resp.data
        assert f"/player/playoff/decline/{qual.id}".encode() in resp.data

    def test_player_can_confirm(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)
        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)

        player = players[0]
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=player.id
        ).first()

        _login(client, player)
        resp = client.post(f"/player/playoff/confirm/{qual.id}", follow_redirects=True)
        assert resp.status_code == 200

        updated = db.session.get(PlayoffQualification, qual.id)
        assert updated.status == QualificationStatus.CONFIRMED

    def test_player_can_decline(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)
        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)

        player = players[0]
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=player.id
        ).first()

        _login(client, player)
        resp = client.post(f"/player/playoff/decline/{qual.id}", follow_redirects=True)
        assert resp.status_code == 200

        updated = db.session.get(PlayoffQualification, qual.id)
        assert updated.status == QualificationStatus.DECLINED

    def test_other_player_cannot_confirm(
        self,
        client,
        db_session,
        admin_user,
        player_user,
        terminated_campionato_with_playoff,
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)
        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)

        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()

        _login(client, player_user)  # Different player
        resp = client.post(f"/player/playoff/confirm/{qual.id}", follow_redirects=True)
        assert resp.status_code == 404


class TestCreatePlayoffGaraRoute:
    def test_create_playoff_gara(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, players, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        # Start playoff
        client.post(f"/admin/campionato/{c.id}/start-playoff", follow_redirects=True)

        # Confirm 5 players
        from models.playoff.services import PlayoffService

        for p in players[:5]:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        # Create gara
        resp = client.post(
            f"/admin/campionato/{c.id}/create-playoff-gara/{cfg.id}",
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Verify gara created
        updated_cfg = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated_cfg.gara is not None
        assert updated_cfg.gara.playoff_config_id == cfg.id


class TestConfigManagementRoute:
    def test_edit_config(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, _, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/playoff/config/{cfg.id}/edit",
            data={"name": "Super Elite", "positions_to": "8", "max_participants": "8"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.name == "Super Elite"
        assert updated.positions_to == 8

    def test_edit_config_salva_le_opzioni_della_finale(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        """Le opzioni della finale arrivano dal form fino alla colonna, e un
        campo lasciato vuoto torna a ereditare."""
        c, cfg, _, _ = terminated_campionato_with_playoff
        cfg.final_ranking_mode = "playoff_only"
        cfg.odd_number_policy = "trio"
        db_session.commit()
        _login(client, admin_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/playoff/config/{cfg.id}/edit",
            data={
                "discipline": Discipline.TEN_BALL.value,
                "strategy_type": "random",
                "odd_number_policy": "",
                "classification_system": "RACK",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        db.session.expire_all()
        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.discipline == Discipline.TEN_BALL.value
        assert updated.strategy_type == "random"
        assert updated.odd_number_policy is None
        assert updated.classification_system == "RACK"

    def test_la_pagina_mostra_le_opzioni_della_finale(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        """Prima dell'avvio la configurazione chiede tutte le opzioni della
        finale, non solo distanza e turni."""
        c, _, _, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        html = client.get(f"/admin/campionato/{c.id}").get_data(as_text=True)

        for campo in (
            "discipline",
            "strategy_type",
            "odd_number_policy",
            "classification_system",
        ):
            assert f'name="{campo}"' in html, campo

    def test_add_config(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, _, _, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/playoff/config/add",
            data={
                "name": "Consolazione",
                "positions_from": "7",
                "positions_to": "12",
                "max_participants": "6",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        configs = PlayoffConfiguration.query.filter_by(
            campionato_id=c.id, is_active=True
        ).all()
        assert len(configs) == 2

    def test_deactivate_config(
        self, client, db_session, admin_user, terminated_campionato_with_playoff
    ):
        c, cfg, _, _ = terminated_campionato_with_playoff
        _login(client, admin_user)

        resp = client.post(
            f"/admin/campionato/{c.id}/playoff/config/{cfg.id}/deactivate",
            follow_redirects=True,
        )
        assert resp.status_code == 200

        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.is_active is False
