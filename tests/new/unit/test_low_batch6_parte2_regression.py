"""Regression (review 2026-06-09, batch 6 parte 2): LOW nits correttezza."""

import uuid
from datetime import date, datetime, time

import pytest

from models.base import db
from models.user.models import User


def _make_user(suffix):
    u = User(username=f"b6p2_{suffix}", email=f"b6p2_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


def _make_gara(**kwargs):
    from models.competition.models import Gara

    defaults = {
        "name": f"Gara b6p2 {uuid.uuid4().hex[:6]}",
        "number": db.session.query(Gara).count() + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "9_ball",
        "matchmaking_strategy": "random",
        "status": "playing",
        "is_race_to": True,
    }
    defaults.update(kwargs)
    gara = Gara(**defaults)
    db.session.add(gara)
    db.session.flush()
    return gara


@pytest.mark.unit
class TestQuietHoursLocalTime:
    """is_in_quiet_hours confronta l'orario locale (Europe/Rome), non UTC.

    Bug: le quiet hours sono impostate dall'utente in ora locale italiana,
    ma il confronto avveniva con utc_now().time() → finestra sfasata di
    1-2 ore (CET/CEST).
    """

    def _preference(self):
        from models.notification.models import NotificationPreference

        return NotificationPreference(
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
        )

    def test_inside_quiet_hours_winter(self, monkeypatch):
        # 21:30 UTC di gennaio = 22:30 a Roma (CET) → dentro le quiet hours
        import models.notification.models as notification_models

        monkeypatch.setattr(
            notification_models, "utc_now", lambda: datetime(2026, 1, 15, 21, 30)
        )
        assert self._preference().is_in_quiet_hours() is True

    def test_inside_quiet_hours_summer(self, monkeypatch):
        # 21:30 UTC di luglio = 23:30 a Roma (CEST) → dentro le quiet hours
        import models.notification.models as notification_models

        monkeypatch.setattr(
            notification_models, "utc_now", lambda: datetime(2026, 7, 15, 21, 30)
        )
        assert self._preference().is_in_quiet_hours() is True

    def test_outside_quiet_hours(self, monkeypatch):
        # 20:00 UTC di gennaio = 21:00 a Roma → fuori dalle quiet hours
        import models.notification.models as notification_models

        monkeypatch.setattr(
            notification_models, "utc_now", lambda: datetime(2026, 1, 15, 20, 0)
        )
        assert self._preference().is_in_quiet_hours() is False


@pytest.mark.unit
def test_opponent_filter_includes_trio_matches(db_session):
    """Il filtro opponent della history include anche i trio match.

    Bug: il filtro confrontava solo Match.player1/2_id → i trio match
    giocati contro quell'avversario (TrioMatch.player1/2/3_id) sparivano
    dalla history filtrata.
    """
    from models.match.models import Match, TrioMatch
    from models.player.history_service import HistoryFilters, PlayerHistoryService
    from models.status_enum import MatchStatus

    suffix = uuid.uuid4().hex[:8]
    user = _make_user(f"a_{suffix}")
    opponent = _make_user(f"b_{suffix}")
    third = _make_user(f"c_{suffix}")
    gara = _make_gara(odd_number_policy="trio")

    # L'avversario filtrato e' il TERZO giocatore del trio: compare solo in
    # TrioMatch.player3_id, NON su Match.player1/2_id (caso che il vecchio
    # filtro escludeva).
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=user.id,
        player2_id=third.id,
        is_trio=True,
        status=MatchStatus.COMPLETED.value,
    )
    db.session.add(match)
    db.session.flush()
    trio = TrioMatch(
        match_id=match.id,
        player1_id=user.id,
        player2_id=third.id,
        player3_id=opponent.id,
    )
    db.session.add(trio)
    db.session.commit()

    pagination, stats = PlayerHistoryService.get_match_history(
        user.id, HistoryFilters(opponent_id=opponent.id)
    )

    assert stats.total_matches == 1
    assert [m.id for m in pagination.items] == [match.id]


@pytest.mark.unit
def test_playoff_not_found_raises_notfounderror(db_session):
    """I not-found del PlayoffService sollevano NotFoundError (→404).

    Bug: ValueError generico → le route API mappavano a 400 invece di 404.
    NotFoundError sottoclassa ValueError, quindi gli except esistenti
    continuano a funzionare.
    """
    from models.exceptions import NotFoundError
    from models.playoff.services import PlayoffService

    with pytest.raises(NotFoundError):
        PlayoffService.update_configuration(999999)

    with pytest.raises(NotFoundError):
        PlayoffService.admin_remove_player(999999, "admin")
