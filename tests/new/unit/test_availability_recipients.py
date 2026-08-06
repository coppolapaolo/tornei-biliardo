"""Regressione: i destinatari di proposte aperte su località testo-libero non
devono includere account soft-deleted/anonimizzati.

``AvailabilityService.get_players_who_played_at_location`` interroga solo le
colonne id di ``IndividualMatch`` (non l'entità ``User``), quindi il filtro
soft-delete a livello di sessione non scatta: va escluso esplicitamente.
"""

from datetime import timedelta

from models.base import db, utc_now
from models.individual_match.models import IndividualMatch
from models.individual_match.availability_service import AvailabilityService
from models.status_enum import MatchStatus

LOC = "Sala Regressione Soft-Delete"


def _played(p1_id, p2_id, location=LOC):
    db.session.add(
        IndividualMatch(
            player1_id=p1_id,
            player2_id=p2_id,
            location=location,
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.COMPLETED,
            distance=5,
        )
    )


def test_recipients_exclude_soft_deleted_players(db_session, isolated_players):
    p0, p1, p2 = isolated_players[0], isolated_players[1], isolated_players[2]
    _played(p0.id, p1.id)
    _played(p0.id, p2.id)
    db.session.commit()

    # Prima dell'anonimizzazione: entrambi gli avversari sono destinatari.
    ids = set(
        AvailabilityService.get_players_who_played_at_location(
            LOC, exclude_user_id=p0.id
        )
    )
    assert ids == {p1.id, p2.id}

    # Anonimizziamo p1 → deve sparire dai destinatari (niente notifiche ad
    # account cancellati), mentre p2 resta.
    p1_id = p1.id
    p1.anonymize()
    db.session.commit()

    ids_after = set(
        AvailabilityService.get_players_who_played_at_location(
            LOC, exclude_user_id=p0.id
        )
    )
    assert ids_after == {p2.id}
    assert p1_id not in ids_after
