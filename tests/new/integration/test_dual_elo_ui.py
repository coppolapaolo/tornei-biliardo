"""Workstream B (UI) — supporto dati del dual ELO.

- la macro `elo_display` emette entrambi i valori come data-attributes;
- `User.elo_global_rating` legge il pool ELO_GLOBAL;
- la classifica ELO globale è ordinata sul pool globale (display-only).
"""

from datetime import timedelta

from flask import render_template_string

from models.individual_match.models import IndividualMatch
from models.gamification.leaderboard_service import LeaderboardService
from models.gamification.models import LeaderboardType
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import MatchStatus
from models.base import utc_now


def test_macro_emits_both_values(app):
    out = render_template_string(
        "{% from 'components/_elo_display.html' import elo_display %}"
        "{{ elo_display(1500, 1620) }}"
    )
    assert 'data-elo-competitive="1500"' in out
    assert 'data-elo-global="1620"' in out
    assert 'class="elo-value"' in out
    # render iniziale mostra il competitivo
    assert ">1500<" in out


def test_macro_defaults_when_none(app):
    out = render_template_string(
        "{% from 'components/_elo_display.html' import elo_display %}"
        "{{ elo_display(None, None) }}"
    )
    # default 1200 per il competitivo, globale ricade sul competitivo
    assert 'data-elo-competitive="1200"' in out
    assert 'data-elo-global="1200"' in out


def test_user_elo_global_rating_property(app, db_session, isolated_players):
    user = isolated_players[0]
    assert user.elo_global_rating is None  # nessun match ancora

    db_session.add(
        PlayerRating(
            user_id=user.id,
            rating_system=RatingSystem.ELO_GLOBAL,
            rating_value=1333,
            robustness=1,
        )
    )
    db_session.commit()
    db_session.refresh(user)
    assert user.elo_global_rating == 1333


def test_global_leaderboard_ranks_by_global_pool(app, db_session, isolated_players):
    a, b = isolated_players[:2]
    # casual: a batte b → a sale, b scende nel pool globale
    m = IndividualMatch(
        player1_id=a.id,
        player2_id=b.id,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=5,
        is_race_to=True,
        player1_score=5,
        player2_score=2,
    )
    db_session.add(m)
    db_session.commit()
    m.confirm_result(a.id)
    m.confirm_result(b.id)
    db_session.commit()

    board = LeaderboardService.get_leaderboard(
        LeaderboardType.ELO_GLOBAL_RATING, limit=10, force_refresh=True
    )
    assert len(board) == 2
    assert board[0]["user"].id == a.id  # vincitore in cima
    assert board[0]["score"] > board[1]["score"]

    # Il pool competitivo NON ha entry (il casual non lo alimenta)
    assert PlayerRating.query.filter_by(rating_system=RatingSystem.ELO).count() == 0
