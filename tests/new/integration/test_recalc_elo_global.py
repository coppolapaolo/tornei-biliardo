"""Workstream B — recalculate_all_elo_global: fusione cronologica torneo+casual.

L'ELO è path-dependent: il recalc del pool globale deve fondere Match e
IndividualMatch in un unico ordine cronologico. Inoltre il recalc competitivo
deve restare invariato (non toccato dal globale).
"""

from datetime import timedelta

from models.individual_match.models import IndividualMatch
from models.match.models import Match
from models.rating.calculation_service import RatingCalculationService
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import MatchStatus
from models.base import utc_now


def _tournament(db_session, p1, p2, winner, when):
    m = Match(
        gara_id=None,
        round_number=1,
        player1_id=p1,
        player2_id=p2,
        player1_score=5 if winner == p1 else 2,
        player2_score=5 if winner == p2 else 2,
        winner_id=winner,
        # VALIDATED (non COMPLETED) → is_walkover=False senza dover creare Rack
        # sintetici: un match COMPLETED senza righe Rack verrebbe scambiato per
        # walkover e saltato dal recalc.
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        ended_at=when,
    )
    db_session.add(m)
    db_session.commit()
    return m


def _casual(db_session, p1, p2, winner, when):
    m = IndividualMatch(
        player1_id=p1,
        player2_id=p2,
        location="Hall",
        scheduled_at=when - timedelta(hours=1),
        status=MatchStatus.CONFIRMED_BY_BOTH,
        distance=5,
        is_race_to=True,
        player1_score=5 if winner == p1 else 2,
        player2_score=5 if winner == p2 else 2,
        winner_id=winner,
        ended_at=when,
    )
    db_session.add(m)
    db_session.commit()
    return m


def test_global_recalc_merges_and_leaves_competitive_intact(
    app, db_session, isolated_players
):
    a, b = isolated_players[:2]
    base = utc_now()
    # Torneo (a batte b), poi casual (b batte a) più tardi
    _tournament(db_session, a.id, b.id, a.id, base)
    _casual(db_session, a.id, b.id, b.id, base + timedelta(hours=2))

    # Recalc competitivo: SOLO il torneo conta
    RatingCalculationService.recalculate_all_elo()
    db_session.commit()
    elo_a_comp = PlayerRating.get_user_rating(a.id, RatingSystem.ELO).rating_value
    assert elo_a_comp > 1200  # a ha vinto l'unico match di torneo

    # Recalc globale: fonde torneo + casual
    RatingCalculationService.recalculate_all_elo_global()
    db_session.commit()

    glob_a = PlayerRating.get_user_rating(a.id, RatingSystem.ELO_GLOBAL).rating_value
    glob_b = PlayerRating.get_user_rating(b.id, RatingSystem.ELO_GLOBAL).rating_value

    # Due match in croce (1 vittoria a testa) → pool globale resta ~1200 per
    # entrambi e simmetrico (somma zero).
    assert glob_a + glob_b == 2400

    # Il pool competitivo NON è stato alterato dal recalc globale
    db_session.refresh(a)
    assert (
        PlayerRating.get_user_rating(a.id, RatingSystem.ELO).rating_value == elo_a_comp
    )
    assert a.elo_rating == elo_a_comp


def test_global_recalc_is_repeatable(app, db_session, isolated_players):
    """Due recalc consecutivi danno lo stesso risultato (reset pulito)."""
    a, b = isolated_players[:2]
    base = utc_now()
    _casual(db_session, a.id, b.id, a.id, base)

    RatingCalculationService.recalculate_all_elo_global()
    db_session.commit()
    first = PlayerRating.get_user_rating(a.id, RatingSystem.ELO_GLOBAL).rating_value

    RatingCalculationService.recalculate_all_elo_global()
    db_session.commit()
    second = PlayerRating.get_user_rating(a.id, RatingSystem.ELO_GLOBAL).rating_value

    assert first == second
