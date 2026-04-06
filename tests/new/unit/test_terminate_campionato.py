"""Unit tests for campionato termination feature."""

import pytest
import uuid
from datetime import date

from models import Campionato
from models.base import db, utc_now
from models.competition.models import Gara
from models.status_enum import TournamentStatus, GaraStatus
from models.campionato.services import TournamentService
from models.campionato.statistics_service import compute_campionato_status
from models.playoff.models import PlayoffConfiguration, PlayoffType


def _make_campionato(db_session, name_suffix=""):
    uid = str(uuid.uuid4())[:8]
    c = Campionato(
        name=f"Camp {uid}{name_suffix}",
        campionato_type="amalfi",
        is_active=True,
    )
    db_session.add(c)
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


def _add_playoff_config(db_session, campionato, min_garas=0):
    cfg = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Elite Playoff",
        playoff_type=PlayoffType.TOP_N,
        max_participants=6,
        positions_from=1,
        positions_to=6,
        is_active=True,
        auto_generate=True,
        min_garas_played=min_garas,
    )
    db_session.add(cfg)
    db_session.flush()
    return cfg


@pytest.mark.unit
class TestTerminateCampionato:
    """Test terminate_campionato service method."""

    def test_happy_path_mixed_gare(self, db_session):
        """Terminate campionato with mix of completed and non-completed gare."""
        service = TournamentService()
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        g2 = _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        g3 = _make_gara(db_session, c, 3, GaraStatus.INSCRIPTION.value)
        db_session.commit()

        result = service.terminate_campionato(c.id)

        assert result is True
        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.terminated_at is not None
        assert refreshed.is_active is False

        # Non-completed gare should be soft-deleted
        g2_ref = db_session.get(Gara, g2.id)
        g3_ref = db_session.get(Gara, g3.id)
        assert g2_ref.deleted_at is not None
        assert g3_ref.deleted_at is not None

    def test_zero_completed_gare(self, db_session):
        """Terminate when no gare are completed — all get soft-deleted."""
        service = TournamentService()
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.SETUP.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        db_session.commit()

        result = service.terminate_campionato(c.id)
        assert result is True

        refreshed = db_session.get(Campionato, c.id)
        assert refreshed.terminated_at is not None

    def test_all_already_completed(self, db_session):
        """Terminate when all gare already completed — no soft-deletes."""
        service = TournamentService()
        c = _make_campionato(db_session)
        g1 = _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        g2 = _make_gara(db_session, c, 2, GaraStatus.COMPLETED.value)
        db_session.commit()

        result = service.terminate_campionato(c.id)
        assert result is True

        g1_ref = db_session.get(Gara, g1.id)
        g2_ref = db_session.get(Gara, g2.id)
        assert g1_ref.deleted_at is None
        assert g2_ref.deleted_at is None

    def test_idempotent_already_terminated(self, db_session):
        """Second terminate call returns False, no changes."""
        service = TournamentService()
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        db_session.commit()

        service.terminate_campionato(c.id)
        result = service.terminate_campionato(c.id)

        assert result is False

    def test_not_found_raises(self, db_session):
        service = TournamentService()
        with pytest.raises(ValueError, match="not found"):
            service.terminate_campionato(999999)

    def test_soft_deleted_raises(self, db_session):
        service = TournamentService()
        c = _make_campionato(db_session)
        c.is_deleted = True
        c.deleted_at = utc_now()
        db_session.commit()

        with pytest.raises(ValueError, match="eliminato"):
            service.terminate_campionato(c.id)


@pytest.mark.unit
class TestComputeStatusTerminated:
    """Test compute_campionato_status and get_status with terminated_at."""

    def test_terminated_no_playoff_returns_completed(self, db_session):
        c = _make_campionato(db_session)
        c.terminated_at = utc_now()
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.COMPLETED.value
        assert c.get_status() == TournamentStatus.COMPLETED.value

    def test_terminated_with_playoff_returns_terminated(self, db_session):
        c = _make_campionato(db_session)
        _add_playoff_config(db_session, c)
        c.terminated_at = utc_now()
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.TERMINATED.value
        assert c.get_status() == TournamentStatus.TERMINATED.value

    def test_terminated_all_completed_with_playoff(self, db_session):
        """Terminate when all gare already completed + playoff config → TERMINATED."""
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.COMPLETED.value)
        _add_playoff_config(db_session, c)
        c.terminated_at = utc_now()
        db_session.commit()

        assert compute_campionato_status(c) == TournamentStatus.TERMINATED.value
        assert c.get_status() == TournamentStatus.TERMINATED.value

    def test_not_terminated_unchanged(self, db_session):
        """Normal (non-terminated) campionato status unchanged."""
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        db_session.commit()

        assert c.get_status() == TournamentStatus.IN_PROGRESS.value


@pytest.mark.unit
class TestCanCreateGara:
    """Test can_create_gara method."""

    def test_normal_campionato_can_create(self, db_session):
        c = _make_campionato(db_session)
        db_session.commit()
        assert c.can_create_gara() is True

    def test_terminated_cannot_create(self, db_session):
        c = _make_campionato(db_session)
        c.terminated_at = utc_now()
        db_session.commit()
        assert c.can_create_gara() is False

    def test_deleted_cannot_create(self, db_session):
        c = _make_campionato(db_session)
        c.is_deleted = True
        c.deleted_at = utc_now()
        db_session.commit()
        assert c.can_create_gara() is False


@pytest.mark.unit
class TestCheckPlayoffFeasibility:
    """Test check_playoff_feasibility service method."""

    def test_feasible(self, db_session):
        service = TournamentService()
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.COMPLETED.value)
        _add_playoff_config(db_session, c, min_garas=2)
        db_session.commit()

        result = service.check_playoff_feasibility(c.id)
        assert result["feasible"] is True
        assert result["completed_count"] == 2

    def test_infeasible(self, db_session):
        service = TournamentService()
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _add_playoff_config(db_session, c, min_garas=5)
        db_session.commit()

        result = service.check_playoff_feasibility(c.id)
        assert result["feasible"] is False
        assert result["completed_count"] == 1
        assert result["configs"][0]["min_garas_played"] == 5

    def test_no_min_requirement_always_feasible(self, db_session):
        service = TournamentService()
        c = _make_campionato(db_session)
        _add_playoff_config(db_session, c, min_garas=0)
        db_session.commit()

        result = service.check_playoff_feasibility(c.id)
        assert result["feasible"] is True


@pytest.mark.unit
class TestUpdatePlayoffMinGaras:
    """Test update_playoff_min_garas service method."""

    def test_update_min(self, db_session):
        service = TournamentService()
        c = _make_campionato(db_session)
        cfg = _add_playoff_config(db_session, c, min_garas=7)
        db_session.commit()

        service.update_playoff_min_garas(c.id, cfg.id, 3)

        refreshed = db_session.get(PlayoffConfiguration, cfg.id)
        assert refreshed.min_garas_played == 3

    def test_not_found_raises(self, db_session):
        service = TournamentService()
        with pytest.raises(ValueError, match="not found"):
            service.update_playoff_min_garas(1, 999999, 3)

    def test_wrong_campionato_raises(self, db_session):
        """IDOR guard: config must belong to the given campionato."""
        service = TournamentService()
        c1 = _make_campionato(db_session, "_A")
        c2 = _make_campionato(db_session, "_B")
        cfg = _add_playoff_config(db_session, c1, min_garas=5)
        db_session.commit()

        with pytest.raises(ValueError, match="non appartiene"):
            service.update_playoff_min_garas(c2.id, cfg.id, 3)
