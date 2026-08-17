"""Regression (review 2026-06-09, batch 4): correttezza dominio.

- kpi/metrics_service: get_activation_rate sommava distinct(p1)+distinct(p2)
  → doppio conteggio di chi gioca in entrambi i ruoli. Ora UNION.
- individual_match/match_models: _check_multi_set_completion assegnava la
  vittoria a player2 anche in parità (exact-sets). Ora None su tie.
- dashboard/section_builders: player_challenge_progress sovrascritto per gara
  (sopravviveva solo l'ultima). Ora unione delle challenge di tutte le gare.
- playoff/services: notify_qualified_players usava notified_at (deprecato) →
  ri-processava tutti i pending. Ora invited_at.
"""

import uuid

import pytest

from models.base import db
from models.user.models import User


def _make_user(suffix, i):
    u = User(username=f"b4_{suffix}_{i}", email=f"b4_{suffix}_{i}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


# -------------------------------------------------------- activation rate
@pytest.mark.unit
def test_activation_rate_no_double_count(db_session):
    """Un utente che gioca sia come p1 sia come p2 conta UNA volta."""
    from models.match.models import Match
    from models.status_enum import MatchStatus
    from models.kpi.metrics_service import MetricsService

    suffix = uuid.uuid4().hex[:8]
    a = _make_user(suffix, 1)
    b = _make_user(suffix, 2)
    db.session.flush()

    # a come player1 in un match, e come player2 in un altro (ruoli alternati).
    db.session.add(
        Match(
            player1_id=a.id,
            player2_id=b.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            round_number=1,
        )
    )
    db.session.add(
        Match(
            player1_id=b.id,
            player2_id=a.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            round_number=1,
        )
    )
    db.session.commit()

    total_users = User.query.filter(User.deleted_at.is_(None)).count()
    rate = MetricsService.get_activation_rate()
    # 2 giocatori distinti hanno giocato; il rate non deve superare 100% né
    # contare a/b due volte (vecchio bug: distinct(p1)+distinct(p2)=4).
    expected = round((2 / total_users) * 100, 1)
    assert rate == expected


# ------------------------------------------------- multi-set tie no winner
@pytest.mark.unit
def test_multi_set_tie_has_no_winner(db_session):
    from models.individual_match.match_models import IndividualMatch

    m = IndividualMatch(
        player1_id=1,
        player2_id=2,
        is_multi_set=True,
        is_race_to_sets=False,
        match_distance=2,
    )
    m.player1_score = 1
    m.player2_score = 1
    m._check_multi_set_completion()
    assert m.winner_id is None  # tie → nessun vincitore (non player2)


@pytest.mark.unit
def test_multi_set_clear_winner(db_session):
    from models.individual_match.match_models import IndividualMatch

    m = IndividualMatch(
        player1_id=1,
        player2_id=2,
        is_multi_set=True,
        is_race_to_sets=True,
        match_distance=2,
    )
    m.player1_score = 2
    m.player2_score = 1
    m._check_multi_set_completion()
    assert m.winner_id == 1


# -------------------------------------------- playoff notify invited_at
@pytest.mark.unit
def test_notify_qualified_players_does_not_reprocess_invited(db_session):
    """Chiamate ripetute non ri-processano i pending gia' invitati."""
    from models.campionato.models import Campionato
    from models.playoff.models import (
        PlayoffConfiguration,
        PlayoffQualification,
        PlayoffType,
        QualificationStatus,
    )
    from models.playoff.services import PlayoffService

    suffix = uuid.uuid4().hex[:8]
    camp = Campionato(name=f"C {suffix}", campionato_type="amalfi")
    db.session.add(camp)
    db.session.flush()
    config = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Elite",
        playoff_type=PlayoffType.TOP_N,
        max_participants=4,
    )
    db.session.add(config)
    db.session.flush()
    for i in range(2):
        u = _make_user(suffix, i)
        db.session.add(
            PlayoffQualification(
                configuration_id=config.id,
                user_id=u.id,
                qualifying_position=i + 1,
                qualification_reason="test",
                status=QualificationStatus.PENDING,
            )
        )
    db.session.commit()

    first = PlayoffService.notify_qualified_players(config.id)
    assert first == 2  # entrambi invitati
    # invited_at ora valorizzato → seconda chiamata non li ri-processa
    second = PlayoffService.notify_qualified_players(config.id)
    assert second == 0


# -------------------------------------- dashboard challenge progress merge
@pytest.mark.unit
def test_challenge_progress_merges_across_gare(db_session):
    """player_challenge_progress unisce le challenge di TUTTE le gare iscritte."""
    from datetime import date, time
    from models.campionato.models import Campionato
    from models.competition.models import Gara, Inscription
    from models.challenge.models import Challenge
    from models.competition.gara_challenge import GaraChallenge
    from models.dashboard.section_builders import DashboardSectionBuilder
    from models.status_enum import GaraStatus

    suffix = uuid.uuid4().hex[:8]
    user = _make_user(suffix, 0)
    camp = Campionato(name=f"C {suffix}", campionato_type="amalfi")
    db.session.add(camp)
    db.session.flush()

    for gi in range(2):
        gara = Gara(
            number=gi + 1,
            name=f"G{gi}_{suffix}",
            date=date(2026, 1, 1 + gi),
            time=time(18, 0),
            discipline="8_ball",
            distance=5,
            rounds_count=1,
            current_round=1,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            campionato_id=camp.id,
        )
        db.session.add(gara)
        db.session.flush()
        ch = Challenge(
            description=f"Ch{gi}_{suffix}", image_path="/x.jpg", pass_fail_only=False
        )
        db.session.add(ch)
        db.session.flush()
        db.session.add(
            GaraChallenge(
                gara_id=gara.id,
                challenge_id=ch.id,
                round_number=1,
                max_attempts=3,
                added_by_id=user.id,
            )
        )
        db.session.add(Inscription(user_id=user.id, gara_id=gara.id))
    db.session.commit()

    result = DashboardSectionBuilder.build_challenge_sections(user.id, None)
    progress = result["player_challenge_progress"].get(user.id)
    assert progress is not None
    # Senza il fix sopravviveva solo l'ultima gara (1 challenge); ora 2.
    assert len(progress["challenges"]) == 2
