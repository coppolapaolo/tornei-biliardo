"""
Contract tests – StatusPresenter (badge class + text) per tutti i domini coperti.
Non richiede il contesto Flask: usa direttamente il presenter.
"""
from types import SimpleNamespace

from utils.status_ui import StatusPresenter
from models.status_enum import (
    ProvaStatus,
    ProvaDerivedStatus,
    TournamentStatus,
    MatchStatus,
    DirectorRequestStatus,
    PlayoffConfirmationStatus,
)


def test_presenter_prova_persisted():
    css, text = StatusPresenter.prova(ProvaStatus.PLAYING.value)
    assert css and text


def test_presenter_prova_derived():
    css, text = StatusPresenter.prova(ProvaDerivedStatus.READY_TO_START.value)
    assert css and text


def test_presenter_tournament():
    fake = SimpleNamespace(get_status=lambda: TournamentStatus.IN_PROGRESS.value)
    css, text = StatusPresenter.tournament(fake)
    assert css and text


def test_presenter_match():
    css, text = StatusPresenter.match(MatchStatus.COMPLETED.value)
    assert css and text


def test_presenter_director_request():
    css, text = StatusPresenter.director_request(DirectorRequestStatus.APPROVED.value)
    assert css and text


def test_presenter_playoff_confirmation():
    css, text = StatusPresenter.playoff_confirmation(
        PlayoffConfirmationStatus.PENDING.value
    )
    assert css and text
