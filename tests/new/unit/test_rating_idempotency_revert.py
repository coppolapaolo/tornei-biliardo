"""Rating: idempotenza, revert e skip dei match con handicap.

Bug (review 2026-06-09, HIGH correttezza) — `calculation_service.py:39`:
`process_match_result` non era idempotente. Ogni MatchCompletedEvent ri-emesso
(reset→ricompletamento) o un recalc_elo su match già processati ri-applicava il
delta Elo e ri-incrementava games_played in modo cumulativo.

Fix: `match_rating_history` registra il delta per ogni (match, giocatore,
sistema). Idempotenza (skip se esiste già history) + revert su riapertura.

Feature (2026-06): i match "con handicap" (effective_has_handicap, ereditato
da gara/campionato) NON aggiornano i rating.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara
from models.match.models import Match
from models.rating.models import PlayerRating, RatingSystem, MatchRatingHistory
from models.rating.calculation_service import RatingCalculationService
from models.status_enum import GaraStatus, MatchStatus


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    return u


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    return Gara(**base)


def _completed_match(gara_id, p1, p2, **overrides):
    base = dict(
        gara_id=gara_id,
        round_number=1,
        player1_id=p1,
        player2_id=p2,
        player1_score=5,
        player2_score=2,
        winner_id=p1,
        status=MatchStatus.COMPLETED.value,
    )
    base.update(overrides)
    return Match(**base)


def _elo(user_id):
    obj = PlayerRating.get_user_rating(user_id, RatingSystem.ELO)
    return obj.rating_value if obj else None


@pytest.mark.unit
def test_process_is_idempotent(db_session):
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "elo_p1"), _user(suffix, "elo_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    elo1_after_first = _elo(p1.id)
    elo2_after_first = _elo(p2.id)
    games1 = PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played

    # Vincitore sale sopra 1200, perdente scende sotto.
    assert elo1_after_first > 1200
    assert elo2_after_first < 1200
    assert games1 == 1
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 2

    # Seconda chiamata (es. MatchCompletedEvent ri-emesso): NO-OP.
    RatingCalculationService.process_match_result(match)
    db.session.flush()
    assert _elo(p1.id) == elo1_after_first
    assert _elo(p2.id) == elo2_after_first
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 1
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 2


@pytest.mark.unit
def test_revert_restores_rating_and_games(db_session):
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rev_p1"), _user(suffix, "rev_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    assert _elo(p1.id) != 1200

    # Revert: l'ultimo match processato torna esattamente allo stato iniziale.
    RatingCalculationService.revert_match_result(match)
    db.session.flush()
    assert _elo(p1.id) == 1200
    assert _elo(p2.id) == 1200
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 0
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


@pytest.mark.unit
def test_reprocess_after_revert_applies_again(db_session):
    # Dopo un revert il match può essere riprocessato (es. ricompletamento):
    # l'idempotenza non lo blocca più, niente inflazione.
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rr_p1"), _user(suffix, "rr_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    elo1 = _elo(p1.id)

    RatingCalculationService.revert_match_result(match)
    db.session.flush()
    RatingCalculationService.process_match_result(match)
    db.session.flush()

    # Stesso risultato del primo calcolo, non raddoppiato.
    assert _elo(p1.id) == elo1
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 1


@pytest.mark.unit
def test_handler_skips_handicap_match(db_session):
    from models.rating.event_handlers import RatingEventHandlers
    from models.events import MatchCompletedEvent

    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "hc_p1"), _user(suffix, "hc_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara = _gara(suffix, has_handicap=True)  # gara con handicap
    db.session.add(gara)
    db.session.flush()
    match = _completed_match(gara.id, p1.id, p2.id, has_handicap=None)  # eredita
    db.session.add(match)
    db.session.flush()
    assert match.effective_has_handicap is True

    event = MatchCompletedEvent(
        match_id=match.id,
        player1_id=p1.id,
        player1_name="p1",
        player2_id=p2.id,
        player2_name="p2",
        winner_id=p1.id,
    )
    RatingEventHandlers.handle_match_completed(event)
    db.session.flush()

    # Nessun rating, nessuna history per un match con handicap.
    assert _elo(p1.id) is None
    assert _elo(p2.id) is None
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


@pytest.mark.unit
def test_to_playing_reopen_triggers_revert(db_session):
    # Wiring end-to-end: riaprire un match completato e RATED via to_playing
    # deve emettere MatchReopenedEvent → handler → revert (history svuotata,
    # rating ripristinato). Verifica il punto-hook centrale in to_playing.
    from models.match.state_service import MatchStateService

    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rp_p1"), _user(suffix, "rp_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 2

    # Riapertura: completed → playing.
    MatchStateService.to_playing(match.id)
    db.session.flush()

    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0
    assert _elo(p1.id) == 1200
    assert _elo(p2.id) == 1200


# Helper: crea una gara standalone e ritorna l'id (per i test che non
# necessitano dei flag handicap).
def _gara_id(suffix):
    gara = _gara(suffix)
    db.session.add(gara)
    db.session.flush()
    return gara.id
