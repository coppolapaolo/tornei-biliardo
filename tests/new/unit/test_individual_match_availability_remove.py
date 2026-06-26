"""Tests for availability removal (owner-only) and upsert behavior."""

import pytest

from models.individual_match.services import IndividualMatchService
from models.individual_match.availability_models import PlayerAvailability


def _make_availability(db_session, user_id, location="Sala Test"):
    rec = PlayerAvailability(user_id=user_id, location=location, is_available=True)
    db_session.add(rec)
    db_session.commit()
    return rec


def test_remove_user_availability_deletes_record(app, db_session, isolated_players):
    player = isolated_players[0]
    rec = _make_availability(db_session, player.id)
    rec_id = rec.id

    IndividualMatchService.remove_user_availability(rec_id, player.id)

    assert db_session.get(PlayerAvailability, rec_id) is None


def test_remove_user_availability_rejects_non_owner(app, db_session, isolated_players):
    owner, other = isolated_players[:2]
    rec = _make_availability(db_session, owner.id)
    rec_id = rec.id

    with pytest.raises(ValueError, match="non trovata"):
        IndividualMatchService.remove_user_availability(rec_id, other.id)

    # Record ancora presente: non rimosso da un non-proprietario
    assert db_session.get(PlayerAvailability, rec_id) is not None


def test_update_user_availability_upsert_no_duplicates(
    app, db_session, isolated_players
):
    """Salvataggi ripetuti sulla stessa località aggiornano, non duplicano."""
    player = isolated_players[0]

    IndividualMatchService.update_user_availability(
        player.id, [{"location": "Sala X", "preferred_times": "18:00-20:00"}]
    )
    IndividualMatchService.update_user_availability(
        player.id, [{"location": "Sala X", "preferred_times": "20:00-22:00"}]
    )

    recs = PlayerAvailability.query.filter_by(
        user_id=player.id, location="Sala X"
    ).all()
    assert len(recs) == 1
    assert recs[0].preferred_times == "20:00-22:00"
