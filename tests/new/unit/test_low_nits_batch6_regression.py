"""Regression (review 2026-06-09, batch 6): LOW nits correttezza."""

import pytest

from models.base import db
from models.user.models import User


def _make_user(suffix):
    u = User(username=f"b6_{suffix}", email=f"b6_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


# Qui c'era `test_update_user_rating_persists_confidence`, che presidiava
# `RatingService.update_user_rating`. Il servizio è stato rimosso con tutto il
# blueprint `/rating`, che era irraggiungibile (ADR-049). `PlayerRating.confidence`
# resta una colonna che nessuno scrive più: toglierla richiederebbe un rebuild
# di tabella per zero guadagno.


@pytest.mark.unit
def test_direct_elimination_validation_excludes_waitlist(db_session):
    """player_count della validazione esclude i waitlist (come il pairing)."""
    from types import SimpleNamespace
    from models.matchmaking.strategies.direct_elimination import (
        DirectEliminationStrategy,
    )

    # 4 attivi + 2 waitlist: con i waitlist contati (vecchio bug) required_rounds
    # = ceil(log2(6)) = 3; senza = ceil(log2(4)) = 2.
    inscriptions = [
        SimpleNamespace(is_withdrawn=False, is_waitlist=False) for _ in range(4)
    ] + [SimpleNamespace(is_withdrawn=False, is_waitlist=True) for _ in range(2)]
    gara = SimpleNamespace(inscriptions=inscriptions, rounds_count=2)

    strategy = DirectEliminationStrategy()
    result = strategy._validate_strategy_specific(gara)
    # rounds_count=2 e' sufficiente per 4 attivi → nessun errore di required_rounds
    assert result["errors"] == []


@pytest.mark.unit
def test_email_service_sender_outside_app_context():
    """_get_sender non esplode fuori dall'application context (no ImportError)."""
    from models.shared.email_service import EmailService

    sender = EmailService._get_sender()
    assert isinstance(sender, str) and sender
