"""Unit tests for campionato termination feature."""

import pytest
import uuid
from datetime import date

from models import Campionato
from models.base import utc_now
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


def _make_user(db_session, idx):
    from models import User
    from models.user.role_enum import UserRole

    uid = str(uuid.uuid4())[:6]
    u = User(
        username=f"p{idx}_{uid}",
        email=f"p{idx}_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _add_completed_match(db_session, gara, round_number, p1, p2):
    from models.match.models import Match
    from models.status_enum import MatchStatus

    m = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.COMPLETED.value,
        winner_id=p1.id,
        player1_score=5,
        player2_score=0,
    )
    db_session.add(m)
    db_session.flush()
    return m


def _add_playing_match(db_session, gara, round_number, p1, p2):
    from models.match.models import Match
    from models.status_enum import MatchStatus

    m = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(m)
    db_session.flush()
    return m


@pytest.mark.unit
class TestTerminatePreservesPlayedGare:
    """Regression: terminate_campionato non deve MAI soft-eliminare una gara
    con risultati reali (match conclusi) — perderemmo dati di classifica.

    Bug (code review 2026-06-09, HIGH correttezza) —
    `models/campionato/tournament_service.py:567`. La logica decideva via
    stato derivato: una gara PLAYING a metà round (alcuni match completati,
    altri in corso) ha derived='playing' (non terminale) → finiva nel
    fallback `gara.soft_delete()` perdendo i match già giocati. Idem per le
    gare AWAITING_SSR. Il criterio corretto è oggettivo: se esiste almeno un
    match concluso la gara non va eliminata.
    """

    def test_playing_mid_round_with_results_not_soft_deleted(self, db_session):
        """Gara PLAYING con un match concluso + uno in corso: dati preservati."""
        service = TournamentService()
        c = _make_campionato(db_session)
        g = _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        g.rounds_count = 2
        g.current_round = 1
        p1 = _make_user(db_session, 1)
        p2 = _make_user(db_session, 2)
        p3 = _make_user(db_session, 3)
        p4 = _make_user(db_session, 4)
        _add_completed_match(db_session, g, 1, p1, p2)
        _add_playing_match(db_session, g, 1, p3, p4)
        db_session.commit()

        result = service.terminate_campionato(c.id)
        assert result is True

        g_ref = db_session.get(Gara, g.id)
        # Prima del fix: soft-eliminata (deleted_at != None) → dati persi.
        assert g_ref.deleted_at is None, "gara con match conclusi non va eliminata"

    def test_round_completed_gara_preserved(self, db_session):
        """Gara ROUND_COMPLETED (round 1 di 2 giocato): preservata, non eliminata."""
        service = TournamentService()
        c = _make_campionato(db_session)
        g = _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        g.rounds_count = 2
        g.current_round = 1
        p1 = _make_user(db_session, 1)
        p2 = _make_user(db_session, 2)
        _add_completed_match(db_session, g, 1, p1, p2)
        db_session.commit()

        service.terminate_campionato(c.id)

        g_ref = db_session.get(Gara, g.id)
        assert g_ref.deleted_at is None

    def test_never_played_gara_still_soft_deleted(self, db_session):
        """Gara mai giocata (nessun match) resta soft-eliminata come prima."""
        service = TournamentService()
        c = _make_campionato(db_session)
        g = _make_gara(db_session, c, 1, GaraStatus.INSCRIPTION.value)
        db_session.commit()

        service.terminate_campionato(c.id)

        g_ref = db_session.get(Gara, g.id)
        assert g_ref.deleted_at is not None


@pytest.mark.unit
class TestIsReadyForPlayoffTransition:
    """Bug 14: il bottone 'Termina Campionato' diventa 'Passa alla fase
    playoff' quando tutte le gare sono di fatto concluse e c'è un playoff."""

    def test_all_completed_with_playoff_is_ready(self, db_session):
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.COMPLETED.value)
        _add_playoff_config(db_session, c)
        db_session.commit()

        assert c.all_gare_concluded() is True
        assert c.is_ready_for_playoff_transition() is True

    def test_all_completed_without_playoff_not_ready(self, db_session):
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        db_session.commit()

        assert c.all_gare_concluded() is True
        assert c.is_ready_for_playoff_transition() is False

    def test_gara_still_playing_not_ready(self, db_session):
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _make_gara(db_session, c, 2, GaraStatus.PLAYING.value)
        _add_playoff_config(db_session, c)
        db_session.commit()

        assert c.all_gare_concluded() is False
        assert c.is_ready_for_playoff_transition() is False

    def test_already_terminated_not_ready(self, db_session):
        c = _make_campionato(db_session)
        _make_gara(db_session, c, 1, GaraStatus.COMPLETED.value)
        _add_playoff_config(db_session, c)
        c.terminated_at = utc_now()
        db_session.commit()

        assert c.is_ready_for_playoff_transition() is False

    def test_no_gare_not_ready(self, db_session):
        c = _make_campionato(db_session)
        _add_playoff_config(db_session, c)
        db_session.commit()

        assert c.all_gare_concluded() is False
        assert c.is_ready_for_playoff_transition() is False

    def test_playing_but_tournament_completed_is_ready(self, db_session):
        """Caso bug 8: gara PLAYING ma tutti i match dell'ultimo turno
        completati (stato derivato TOURNAMENT_COMPLETED) → conta come
        conclusa, il bottone diventa 'Passa alla fase playoff'."""
        c = _make_campionato(db_session)
        g = _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        g.rounds_count = 1
        g.current_round = 1
        p1 = _make_user(db_session, 1)
        p2 = _make_user(db_session, 2)
        _add_completed_match(db_session, g, 1, p1, p2)
        _add_playoff_config(db_session, c)
        db_session.commit()

        assert g.get_real_status() == "campionato_completed"
        assert c.all_gare_concluded() is True
        assert c.is_ready_for_playoff_transition() is True

    def test_playing_round_completed_not_ready(self, db_session):
        """Gara PLAYING con turno finito ma altri turni da giocare
        (ROUND_COMPLETED) NON conta come conclusa."""
        c = _make_campionato(db_session)
        g = _make_gara(db_session, c, 1, GaraStatus.PLAYING.value)
        g.rounds_count = 2
        g.current_round = 1
        p1 = _make_user(db_session, 1)
        p2 = _make_user(db_session, 2)
        _add_completed_match(db_session, g, 1, p1, p2)
        _add_playoff_config(db_session, c)
        db_session.commit()

        assert g.get_real_status() == "round_completed"
        assert c.all_gare_concluded() is False
        assert c.is_ready_for_playoff_transition() is False


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
