"""Unit tests for playoff start: config, qualifications, player management."""

import pytest
import uuid
from datetime import date

from models import Campionato
from models.base import db, utc_now
from models.competition.models import Gara, Inscription
from models.classification.models import Classification
from models.status_enum import GaraStatus
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.user.models import User


def _uid():
    return str(uuid.uuid4())[:8]


def _make_user(db_session, role="player"):
    u = User(username=f"user_{_uid()}", email=f"{_uid()}@test.com", role=role)
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _make_campionato(db_session, terminated=False):
    c = Campionato(name=f"Camp {_uid()}", campionato_type="amalfi", is_active=True)
    db_session.add(c)
    db_session.flush()
    if terminated:
        c.terminated_at = utc_now()
        db_session.flush()
    return c


def _make_gara(db_session, campionato, number=1, status=GaraStatus.COMPLETED.value):
    # Use modulo to keep day in valid range
    day = ((number - 1) % 28) + 1
    month = ((number - 1) // 28) % 12 + 1
    g = Gara(
        campionato_id=campionato.id,
        number=number,
        name=f"Gara {number}",
        date=date(2026, month, day),
        discipline="nine_ball",
        status=status,
        rounds_count=3,
        current_round=1,
        distance=5,
    )
    db_session.add(g)
    db_session.flush()
    return g


def _make_config(
    db_session, campionato, name="Elite", pos_from=1, pos_to=6, max_p=6, min_garas=0
):
    cfg = PlayoffConfiguration(
        campionato_id=campionato.id,
        name=name,
        playoff_type=PlayoffType.TOP_N,
        max_participants=max_p,
        positions_from=pos_from,
        positions_to=pos_to,
        is_active=True,
        auto_generate=True,
        min_garas_played=min_garas,
    )
    db_session.add(cfg)
    db_session.flush()
    return cfg


def _make_classification(db_session, campionato, user, position, gare_played=5):
    cls = Classification(
        campionato_id=campionato.id,
        user_id=user.id,
        position=position,
        total_matches_won=10 - position,
        total_point_difference=20 - position,
        gare_played=gare_played,
    )
    db_session.add(cls)
    db_session.flush()
    return cls


def _make_inscription(db_session, user, gara):
    ins = Inscription(user_id=user.id, gara_id=gara.id)
    db_session.add(ins)
    db_session.flush()
    return ins


# ── Config management tests ──────────────────────────────────────


class TestConfigManagement:
    def test_update_configuration(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        db_session.commit()

        PlayoffService.update_configuration(
            cfg.id, name="New Name", positions_to=8, max_participants=8
        )
        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.name == "New Name"
        assert updated.positions_to == 8
        assert updated.max_participants == 8

    def test_update_configuration_blocked_after_avvio(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        players = [_make_user(db_session) for _ in range(6)]
        gara = _make_gara(db_session, c)
        for i, p in enumerate(players):
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
        db_session.commit()

        PlayoffService.start_playoff(c.id)

        with pytest.raises(ValueError, match="Non modificabile"):
            PlayoffService.update_configuration(cfg.id, name="X")

    def test_add_configuration(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        db_session.commit()

        cfg = PlayoffService.add_configuration(
            c.id,
            "Consolazione",
            positions_from=9,
            positions_to=16,
            max_participants=8,
        )
        assert cfg.id is not None
        assert cfg.name == "Consolazione"
        assert cfg.positions_from == 9

    def test_deactivate_configuration(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        db_session.commit()

        PlayoffService.deactivate_configuration(cfg.id)
        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.is_active is False

    def test_update_gara_params(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        db_session.commit()

        PlayoffService.update_configuration(cfg.id, discipline="palla_8", distance=3)
        updated = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated.discipline == "palla_8"
        assert updated.distance == 3


# ── Start playoff tests ──────────────────────────────────────────


class TestStartPlayoff:
    def _setup_campionato(self, db_session, n_players=8, min_garas=0):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c, min_garas=min_garas)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(n_players):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1, gare_played=5)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()
        return c, cfg, players

    def test_start_playoff_happy_path(self, db_session):
        c, cfg, players = self._setup_campionato(db_session)

        results = PlayoffService.start_playoff(c.id)
        assert "Elite" in results
        assert len(results["Elite"]) == 6  # pos 1-6

        # Check qualifications are PENDING with invited_at
        quals = PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()
        assert all(q.status == QualificationStatus.PENDING for q in quals)
        assert all(q.invited_at is not None for q in quals)

    def test_start_playoff_sends_invitation_with_deeplink(self, db_session):
        """Bug 15: ogni qualificato riceve una notifica con action_url che
        deep-linka alla propria pagina di invito (dove conferma/rifiuta),
        e qualification_id nelle related_entities."""
        from models.notification.models import Notification, NotificationType

        c, cfg, players = self._setup_campionato(db_session)
        PlayoffService.start_playoff(c.id)

        quals = PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()
        assert len(quals) == 6
        for qual in quals:
            notif = Notification.query.filter_by(
                user_id=qual.user_id,
                notification_type=NotificationType.PLAYOFF_INVITATION,
            ).first()
            assert notif is not None, f"Nessuna notifica per user {qual.user_id}"
            assert notif.action_url == f"/player/playoff/invitation/{qual.id}"
            assert notif.action_text
            assert notif.get_related_entities().get("qualification_id") == qual.id

    def test_start_playoff_not_terminated(self, db_session):
        c = _make_campionato(db_session, terminated=False)
        _make_config(db_session, c)
        db_session.commit()

        with pytest.raises(ValueError, match="terminato"):
            PlayoffService.start_playoff(c.id)

    def test_start_playoff_already_started(self, db_session):
        c, cfg, players = self._setup_campionato(db_session)
        PlayoffService.start_playoff(c.id)

        with pytest.raises(ValueError, match="già avviati"):
            PlayoffService.start_playoff(c.id)

    def test_start_playoff_no_active_configs(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        # Add a config then deactivate it: campionato has configs but none active
        cfg = _make_config(db_session, c)
        cfg.is_active = False
        db_session.commit()

        with pytest.raises(ValueError, match="Nessuna configurazione"):
            PlayoffService.start_playoff(c.id)

    def test_min_garas_excludes_player(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        _make_config(db_session, c, min_garas=3)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(8):
            p = _make_user(db_session)
            gare_played = 5 if i != 2 else 1  # Player at pos 3 has only 1 gara
            _make_classification(db_session, c, p, i + 1, gare_played=gare_played)
            _make_inscription(db_session, p, gara)
            # Create actual inscriptions matching gare_played for min_garas check
            for j in range(gare_played):
                extra_gara = _make_gara(
                    db_session,
                    c,
                    number=10 + i * 10 + j,
                    status=GaraStatus.COMPLETED.value,
                )
                _make_inscription(db_session, p, extra_gara)
            players.append(p)
        db_session.commit()

        results = PlayoffService.start_playoff(c.id)
        qualified_user_ids = {q.user_id for q in results["Elite"]}
        # Player at pos 3 excluded, pos 7 should be replacement
        assert players[2].id not in qualified_user_ids
        assert len(results["Elite"]) == 6

    def test_response_deadline_default_7_days(self, db_session):
        c, cfg, _ = self._setup_campionato(db_session)

        PlayoffService.start_playoff(c.id)
        updated_cfg = db.session.get(PlayoffConfiguration, cfg.id)
        assert updated_cfg.response_deadline is not None
        delta = updated_cfg.response_deadline - utc_now()
        assert delta.days >= 6  # roughly 7 days


# ── Confirm/Decline tests ────────────────────────────────────────


class TestConfirmDecline:
    def _start(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(8):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()
        PlayoffService.start_playoff(c.id)
        return c, cfg, players

    def test_confirm_qualification(self, db_session):
        c, cfg, players = self._start(db_session)
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()

        PlayoffService.confirm_qualification(qual.id, players[0].id)
        updated = db.session.get(PlayoffQualification, qual.id)
        assert updated.status == QualificationStatus.CONFIRMED
        assert updated.responded_at is not None

    def test_decline_qualification(self, db_session):
        c, cfg, players = self._start(db_session)
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()

        PlayoffService.decline_qualification(qual.id, players[0].id)
        updated = db.session.get(PlayoffQualification, qual.id)
        assert updated.status == QualificationStatus.DECLINED

    def test_double_confirm_raises(self, db_session):
        c, cfg, players = self._start(db_session)
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()

        PlayoffService.confirm_qualification(qual.id, players[0].id)
        with pytest.raises(ValueError, match="pending"):
            PlayoffService.confirm_qualification(qual.id, players[0].id)


# ── Admin add/remove player tests ────────────────────────────────


class TestAdminPlayerManagement:
    def _start(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(8):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()
        PlayoffService.start_playoff(c.id)
        return c, cfg, gara, players

    def test_admin_add_player(self, db_session):
        c, cfg, gara, players = self._start(db_session)
        # Player 8 is pos 8, not in the 1-6 range
        extra = _make_user(db_session)
        _make_inscription(db_session, extra, gara)
        db_session.commit()

        qual = PlayoffService.admin_add_player(cfg.id, extra.id, "admin")
        assert qual.status == QualificationStatus.CONFIRMED
        assert "manualmente" in qual.qualification_reason

    def test_admin_add_already_present(self, db_session):
        c, cfg, gara, players = self._start(db_session)

        with pytest.raises(ValueError, match="già presente"):
            PlayoffService.admin_add_player(cfg.id, players[0].id, "admin")

    def test_admin_add_non_participant(self, db_session):
        c, cfg, gara, players = self._start(db_session)
        outsider = _make_user(db_session)
        db_session.commit()

        with pytest.raises(ValueError, match="non ha partecipato"):
            PlayoffService.admin_add_player(cfg.id, outsider.id, "admin")

    def test_admin_remove_player(self, db_session):
        c, cfg, gara, players = self._start(db_session)
        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()

        PlayoffService.admin_remove_player(qual.id, "admin")
        updated = db.session.get(PlayoffQualification, qual.id)
        assert updated.status == QualificationStatus.DECLINED
        assert "Rimosso da admin" in updated.qualification_reason
        assert "era:" in updated.qualification_reason

    def test_admin_remove_blocked_after_gara(self, db_session):
        c, cfg, gara, players = self._start(db_session)
        # Confirm all, then create gara
        for p in players[:6]:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        PlayoffService.create_playoff_gara(cfg.id)

        qual = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, user_id=players[0].id
        ).first()
        with pytest.raises(ValueError, match="dopo creazione gara"):
            PlayoffService.admin_remove_player(qual.id, "admin")


# ── Create playoff gara tests ────────────────────────────────────


class TestCreatePlayoffGara:
    def _setup_confirmed(self, db_session, n_confirmed=5):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(8):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)
        for p in players[:n_confirmed]:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        return c, cfg, players

    def test_create_playoff_gara(self, db_session):
        c, cfg, players = self._setup_confirmed(db_session, n_confirmed=5)

        gara = PlayoffService.create_playoff_gara(cfg.id)
        assert gara.playoff_config_id == cfg.id
        assert gara.campionato_id == c.id

        # Check inscriptions
        inscriptions = Inscription.query.filter_by(gara_id=gara.id).all()
        assert len(inscriptions) == 5

    def test_create_playoff_gara_idempotent(self, db_session):
        c, cfg, players = self._setup_confirmed(db_session, n_confirmed=5)

        gara1 = PlayoffService.create_playoff_gara(cfg.id)
        gara2 = PlayoffService.create_playoff_gara(cfg.id)
        assert gara1.id == gara2.id

    def test_create_playoff_gara_inherits_params(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)  # discipline=nine_ball, distance=5
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)
        for p in players:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        playoff_gara = PlayoffService.create_playoff_gara(cfg.id)
        assert playoff_gara.discipline == "nine_ball"
        assert playoff_gara.distance == 5

    def test_create_playoff_gara_override_params(self, db_session):
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        cfg.discipline = "palla_8"
        cfg.distance = 3
        gara = _make_gara(db_session, c)
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)
        for p in players:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        playoff_gara = PlayoffService.create_playoff_gara(cfg.id)
        assert playoff_gara.discipline == "palla_8"
        assert playoff_gara.distance == 3


# ── Inscription guard tests ───────────────────────────────────────


class TestPlayoffInscriptionGuard:
    def test_self_inscription_blocked_on_playoff_gara(self, db_session):
        from models.competition.inscription_service import InscriptionService

        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)
        for p in players:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        playoff_gara = PlayoffService.create_playoff_gara(cfg.id)

        outsider = _make_user(db_session)
        db_session.commit()

        with pytest.raises(ValueError, match="playoff"):
            InscriptionService.inscribe_user(outsider.id, playoff_gara.id)


# ── get_gara_params tests ────────────────────────────────────────


class TestGetGaraParams:
    def test_inherits_from_campionato(self, db_session):
        c = _make_campionato(db_session)
        cfg = _make_config(db_session, c)
        _make_gara(db_session, c)  # nine_ball, distance=5
        db_session.commit()

        params = cfg.get_gara_params()
        assert params["discipline"] == "nine_ball"
        assert params["distance"] == 5

    def test_explicit_override(self, db_session):
        c = _make_campionato(db_session)
        cfg = _make_config(db_session, c)
        cfg.discipline = "palla_8"
        cfg.distance = 3
        _make_gara(db_session, c)
        db_session.commit()

        params = cfg.get_gara_params()
        assert params["discipline"] == "palla_8"
        assert params["distance"] == 3

    def test_fallback_no_completed_gara(self, db_session):
        c = _make_campionato(db_session)
        cfg = _make_config(db_session, c)
        db_session.commit()

        params = cfg.get_gara_params()
        assert params["discipline"] == "palla_9"  # default fallback


# ── TERMINATED → COMPLETED transition tests ───────────────────────


class TestTerminatedToCompleted:
    def test_terminated_stays_terminated_without_playoff_tournament(self, db_session):
        """Campionato with playoff configs but no PlayoffTournament stays TERMINATED."""
        c = _make_campionato(db_session, terminated=True)
        _make_config(db_session, c)
        db_session.commit()

        assert c.get_status() == "terminated"

    def test_terminated_becomes_completed_when_all_playoffs_done(self, db_session):
        """When all PlayoffTournaments are completed, campionato becomes COMPLETED."""
        c = _make_campionato(db_session, terminated=True)
        cfg = _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)
        for p in players:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        PlayoffService.create_playoff_gara(cfg.id)

        # Status is TERMINATED while playoff in progress
        assert c.get_status() == "terminated"

        # Complete the playoff tournament
        tournament = PlayoffTournament.query.filter_by(configuration_id=cfg.id).first()
        PlayoffService.complete_playoff_campionato(
            tournament.id, winner_id=players[0].id
        )

        # Now should be COMPLETED
        assert c.get_status() == "completed"

    def test_stays_terminated_if_some_playoffs_incomplete(self, db_session):
        """With 2 playoff configs, if only 1 is completed, stay TERMINATED."""
        c = _make_campionato(db_session, terminated=True)
        cfg1 = _make_config(db_session, c, name="Elite", pos_from=1, pos_to=3, max_p=3)
        _make_config(db_session, c, name="Academy", pos_from=4, pos_to=6, max_p=3)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)

        # Confirm and create gara for config1 only
        for p in players[:3]:
            qual = PlayoffQualification.query.filter_by(
                configuration_id=cfg1.id, user_id=p.id
            ).first()
            PlayoffService.confirm_qualification(qual.id, p.id)

        PlayoffService.create_playoff_gara(cfg1.id)
        t1 = PlayoffTournament.query.filter_by(configuration_id=cfg1.id).first()
        PlayoffService.complete_playoff_campionato(t1.id)

        # Config2 not yet done → TERMINATED
        assert c.get_status() == "terminated"


# ── Notification tests ────────────────────────────────────────────


class TestPlayoffNotifications:
    def test_start_playoff_creates_notifications(self, db_session):
        """Starting playoff should create in-app notifications for qualified players."""
        from models.notification.models import Notification, NotificationType

        c = _make_campionato(db_session, terminated=True)
        _make_config(db_session, c)
        gara = _make_gara(db_session, c)
        players = []
        for i in range(6):
            p = _make_user(db_session)
            _make_classification(db_session, c, p, i + 1)
            _make_inscription(db_session, p, gara)
            players.append(p)
        db_session.commit()

        PlayoffService.start_playoff(c.id)

        # Each qualified player should have a PLAYOFF_INVITATION notification
        for p in players:
            notifs = Notification.query.filter_by(
                user_id=p.id,
                notification_type=NotificationType.PLAYOFF_INVITATION,
            ).all()
            assert len(notifs) == 1, f"Player {p.username} should have 1 notification"
            assert "Elite" in notifs[0].title
