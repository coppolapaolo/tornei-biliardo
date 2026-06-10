"""Regression (review 2026-06-09, batch 6 parte 2): LOW nits correttezza."""

from datetime import datetime, time

import pytest


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
