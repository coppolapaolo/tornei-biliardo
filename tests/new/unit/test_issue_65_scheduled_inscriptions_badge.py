"""Regressione issue #65 — gare con apertura iscrizioni nel futuro.

`GaraStatusResolver` restituisce già `inscription_not_yet_open` per una gara
in INSCRIPTION la cui apertura è nel futuro, ma `StatusPresenter.gara` non
mappava quello stato: cadeva sul fallback e mostrava "Sconosciuto" in
homepage, nel riquadro di gestione del director e nell'elenco gare del
campionato. Le due mappe di badge devono anche concordare sull'etichetta.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import utc_now
from models.competition.status_resolver import STATUS_BADGE_MAP, get_status_badge
from models.status_enum import GaraStatus, ProvaDerivedStatus
from utils.status_ui import StatusPresenter


class _FakeGara:
    """Gara in iscrizione la cui apertura è programmata nel futuro."""

    def __init__(self, *, starts_in_days: int = 3):
        self.status = GaraStatus.INSCRIPTION.value
        self.inscription_start = utc_now() + timedelta(days=starts_in_days)
        self.inscription_end = utc_now() + timedelta(days=starts_in_days + 7)

    def get_real_status(self):
        from models.competition.status_resolver import GaraStatusResolver

        return GaraStatusResolver.resolve(self)


@pytest.mark.unit
def test_scheduled_inscriptions_are_not_unknown(app):
    """Il badge non è più "Sconosciuto" (locale di test = it)."""
    gara = _FakeGara()
    assert gara.get_real_status() == ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value

    with app.test_request_context("/"):
        css, text = StatusPresenter.gara(gara)

    assert text != "Sconosciuto"
    assert text == "Iscrizioni Programmate"
    assert css == "bg-secondary"


@pytest.mark.unit
def test_open_inscriptions_still_render_as_open(app):
    """Nessuna regressione sullo stato adiacente: apertura già passata."""
    gara = _FakeGara()
    gara.inscription_start = utc_now() - timedelta(days=1)

    with app.test_request_context("/"):
        _css, text = StatusPresenter.gara(gara)

    assert text == "Iscrizioni Aperte"


@pytest.mark.unit
def test_both_badge_maps_agree_on_the_label(app):
    """Le due mappe coprono punti diversi della UI: stesso stato, stesso nome."""
    gara = _FakeGara()

    with app.test_request_context("/"):
        _css, presenter_text = StatusPresenter.gara(gara)

    resolver_badge = get_status_badge(gara)

    assert resolver_badge["text"] == presenter_text
    assert (
        STATUS_BADGE_MAP[ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value]["text"]
        == presenter_text
    )
