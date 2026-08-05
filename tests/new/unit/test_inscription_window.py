"""Regression: la finestra di iscrizione (inscription_start/end) deve essere
rispettata sia da `Gara.can_inscribe` sia da `Gara.get_real_status`.

Scenario originale (docs/debug20260528.md bug 1): una Gara con
`status=INSCRIPTION` e `inscription_start` futura veniva mostrata in
dashboard come "iscrizioni aperte" e il pulsante "Iscriviti" appariva
attivo, salvo poi essere bloccato dal controllo lato route con un flash
"le iscrizioni non sono disponibili". Causa: `_resolve_inscription`
controllava solo `inscription_end`, mai `inscription_start`.
"""

from datetime import date, timedelta

import pytest

from models import Gara
from models.base import utc_now
from models.competition.models import WithdrawPolicy
from models.status_enum import GaraStatus, ProvaDerivedStatus


def _make_inscription_gara(inscription_start, inscription_end):
    """Build an in-memory Gara stub (no DB) for resolver tests."""
    return Gara(
        campionato_id=None,
        number=1,
        name="Stub",
        date=date.today() + timedelta(days=7),
        location="Loc",
        description="d",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        entry_fee=0,
        discipline="palla 9",
        distance=5,
        is_race_to=True,
        withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=inscription_start,
        inscription_end=inscription_end,
    )


@pytest.mark.unit
class TestInscriptionWindow:
    def test_get_real_status_when_start_is_future(self):
        now = utc_now()
        gara = _make_inscription_gara(
            inscription_start=now + timedelta(days=2),
            inscription_end=now + timedelta(days=5),
        )
        expected = ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value
        assert gara.get_real_status() == expected
        assert gara.can_inscribe() is False

    def test_get_real_status_when_inside_window(self):
        now = utc_now()
        gara = _make_inscription_gara(
            inscription_start=now - timedelta(hours=1),
            inscription_end=now + timedelta(days=1),
        )
        assert gara.get_real_status() == GaraStatus.INSCRIPTION.value
        assert gara.can_inscribe() is True

    def test_get_real_status_when_end_is_past(self):
        now = utc_now()
        gara = _make_inscription_gara(
            inscription_start=now - timedelta(days=3),
            inscription_end=now - timedelta(hours=1),
        )
        assert gara.get_real_status() == ProvaDerivedStatus.INSCRIPTION_CLOSED.value
        assert gara.can_inscribe() is False

    def test_can_inscribe_without_window_dates(self):
        """Gara senza vincoli di start/end: si può iscrivere se status=INSCRIPTION."""
        gara = _make_inscription_gara(inscription_start=None, inscription_end=None)
        assert gara.can_inscribe() is True
        assert gara.get_real_status() == GaraStatus.INSCRIPTION.value
