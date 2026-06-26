"""Workstream B — dual ELO: pool competitivo (ELO) vs globale (ELO_GLOBAL).

Vincoli verificati:
- un match di torneo aggiorna ENTRAMBI i pool;
- un casual VALIDATO aggiorna SOLO ELO_GLOBAL;
- `User.elo_rating` (fonte autorevole competitiva) NON è toccato dai casual;
- idempotenza per-sorgente della history.
"""

from datetime import timedelta

from models.individual_match.models import IndividualMatch
from models.match.models import Match
from models.rating.calculation_service import RatingCalculationService
from models.rating.models import PlayerRating, MatchRatingHistory, RatingSystem
from models.status_enum import MatchStatus
from models.base import utc_now


def _validate_casual(db_session, p1, p2, s1, s2):
    m = IndividualMatch(
        player1_id=p1,
        player2_id=p2,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=5,
        is_race_to=True,
        player1_score=s1,
        player2_score=s2,
    )
    db_session.add(m)
    db_session.commit()
    m.confirm_result(p1)
    m.confirm_result(p2)
    db_session.commit()
    return m


def test_casual_updates_only_global_pool(app, db_session, isolated_players):
    winner, loser = isolated_players[:2]
    _validate_casual(db_session, winner.id, loser.id, 5, 2)

    # ELO_GLOBAL valorizzato per entrambi
    assert (
        PlayerRating.query.filter_by(rating_system=RatingSystem.ELO_GLOBAL).count() == 2
    )
    # ELO competitivo intoccato
    assert PlayerRating.query.filter_by(rating_system=RatingSystem.ELO).count() == 0

    # User.elo_rating (fonte autorevole competitiva) resta None
    db_session.refresh(winner)
    db_session.refresh(loser)
    assert winner.elo_rating is None
    assert loser.elo_rating is None

    # history su sorgente individual_match, non match
    hist = MatchRatingHistory.query.filter_by(
        rating_system=RatingSystem.ELO_GLOBAL
    ).all()
    assert all(h.individual_match_id is not None and h.match_id is None for h in hist)


def test_tournament_match_updates_both_pools(app, db_session, isolated_players):
    p1, p2 = isolated_players[:2]
    match = Match(
        gara_id=None,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.COMPLETED.value,
        player1_score=5,
        player2_score=2,
        winner_id=p1.id,
        ended_at=utc_now(),
    )
    db_session.add(match)
    db_session.commit()

    RatingCalculationService.process_match_result(match)
    db_session.commit()

    assert PlayerRating.query.filter_by(rating_system=RatingSystem.ELO).count() == 2
    assert (
        PlayerRating.query.filter_by(rating_system=RatingSystem.ELO_GLOBAL).count() == 2
    )

    # I due pool partono uguali per lo stesso match
    elo_p1 = PlayerRating.get_user_rating(p1.id, RatingSystem.ELO)
    glob_p1 = PlayerRating.get_user_rating(p1.id, RatingSystem.ELO_GLOBAL)
    assert elo_p1.rating_value == glob_p1.rating_value

    # User.elo_rating sincronizzato col SOLO pool competitivo
    db_session.refresh(p1)
    assert p1.elo_rating == elo_p1.rating_value


def test_casual_idempotent(app, db_session, isolated_players):
    """Riprocessare lo stesso casual non duplica la history globale."""
    winner, loser = isolated_players[:2]
    m = _validate_casual(db_session, winner.id, loser.id, 5, 0)

    # Seconda chiamata diretta: no-op idempotente
    RatingCalculationService.process_individual_match_result(m)
    db_session.commit()

    hist = MatchRatingHistory.query.filter_by(
        individual_match_id=m.id, rating_system=RatingSystem.ELO_GLOBAL
    ).count()
    assert hist == 2  # un record per giocatore, non di più
