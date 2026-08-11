"""Unit test del leaderboard locale + contributo (ADR-037, §11-bis)."""

import uuid
from datetime import timedelta

from models.base import db, utc_now
from models.user.role_enum import UserRole
from models.gamification.community_leaderboard_service import (
    CommunityLeaderboardService,
)

NAP_LAT, NAP_LNG = 40.8518, 14.2681


def _user(role=UserRole.PLAYER, home_city=None, total_xp=None):
    from models import User
    from models.gamification.models import UserLevel

    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=role.value,
        home_city=home_city,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    if total_xp is not None:
        db.session.add(UserLevel(user_id=u.id, total_xp=total_xp))
        db.session.commit()
    return u


def _napoli_venue():
    from models.location.models import BilliardHall

    uid = str(uuid.uuid4())[:8]
    hall = BilliardHall(
        name=f"Sala_{uid}",
        city="Napoli",
        number_of_tables=4,
        is_active=True,
        latitude=NAP_LAT,
        longitude=NAP_LNG,
    )
    db.session.add(hall)
    db.session.commit()
    return hall


# ── Locale ───────────────────────────────────────────────────────────────────


def test_local_unavailable_without_home_city(db_session):
    user = _user(home_city=None)
    board = CommunityLeaderboardService.get_local_leaderboard(user.id)
    assert board["available"] is False
    assert board["entries"] == []


def test_local_ranks_same_city_by_xp(db_session):
    viewer = _user(home_city="Napoli", total_xp=100)
    top = _user(home_city="Napoli", total_xp=500)
    _user(home_city="Napoli", total_xp=50)
    # Giocatore di un'altra città lontana, non deve comparire.
    _user(home_city="Milano", total_xp=9999)

    board = CommunityLeaderboardService.get_local_leaderboard(viewer.id)
    assert board["available"] is True
    assert board["zone_label"] == "Napoli"
    # Tutti e soli i 3 di Napoli.
    usernames = {e["user"].username for e in board["entries"]}
    assert top.username in usernames
    assert len(board["entries"]) == 3
    # Ordinati per XP desc → il primo è top (500).
    assert board["entries"][0]["user"].id == top.id
    assert board["entries"][0]["score"] == 500
    # viewer evidenziato e con rank corretto (2° con 100 XP).
    viewer_entry = next(e for e in board["entries"] if e["is_viewer"])
    assert viewer_entry["rank"] == board["viewer_rank"]


def test_local_city_match_is_case_insensitive(db_session):
    viewer = _user(home_city="Napoli", total_xp=10)
    other = _user(home_city="  napoli ", total_xp=20)
    board = CommunityLeaderboardService.get_local_leaderboard(viewer.id)
    ids = {e["user"].id for e in board["entries"]}
    assert other.id in ids and viewer.id in ids


def test_cities_in_zone_expands_to_nearby_via_centroid(db_session):
    _napoli_venue()  # centroide risolvibile per "Napoli"
    zone = CommunityLeaderboardService.cities_in_zone("Napoli", radius_km=30)
    assert "napoli" in zone


# ── Contributo ───────────────────────────────────────────────────────────────


def _challenge(author_id):
    from models.challenge.models import Challenge

    c = Challenge(
        description="drill",
        image_path="x.png",
        created_by_id=author_id,
    )
    db.session.add(c)
    db.session.commit()
    return c


def _attempt(challenge_id, user_id, completed=True):
    from models.challenge.models import ChallengeAttempt

    a = ChallengeAttempt(
        challenge_id=challenge_id, user_id=user_id, completed=completed
    )
    db.session.add(a)
    db.session.commit()
    return a


def _accepted_open_proposal(proposer_id):
    from models.individual_match.models import (
        MatchProposal,
        ProposalType,
        ProposalStatus,
    )

    p = MatchProposal(
        proposer_id=proposer_id,
        proposal_type=ProposalType.OPEN,
        status=ProposalStatus.ACCEPTED,
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(days=2),
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_compute_contribution_breakdown(db_session):
    from datetime import date, timedelta as td
    from models.competition.services import GaraService

    author = _user(role=UserRole.DIRECTOR)
    other = _user()

    # 2 drill completati da altri (+1 dello stesso autore, che NON conta).
    ch = _challenge(author.id)
    _attempt(ch.id, other.id, completed=True)
    other2 = _user()
    _attempt(ch.id, other2.id, completed=True)
    _attempt(ch.id, author.id, completed=True)  # self → escluso

    # 1 gara organizzata.
    GaraService.create_gara(
        number=1,
        name="G",
        date=date.today() + td(days=2),
        discipline="8_ball",
        distance=5,
        director_id=author.id,
    )

    # 1 proposta aperta accettata.
    _accepted_open_proposal(author.id)

    b = CommunityLeaderboardService.compute_contribution(author.id)
    assert b["drills_engaged"] == 2
    assert b["gare_organized"] == 1
    assert b["proposals_accepted"] == 1
    assert b["total"] == 4


def test_contribution_leaderboard_ranks_and_excludes_zero(db_session):
    author = _user(role=UserRole.DIRECTOR)
    other = _user()
    ch = _challenge(author.id)
    _attempt(ch.id, other.id, completed=True)

    # Utente senza contributo: non deve comparire.
    _user()

    board = CommunityLeaderboardService.get_contribution_leaderboard()
    assert len(board) == 1
    assert board[0]["user"].id == author.id
    assert board[0]["rank"] == 1
    assert board[0]["score"] == 1


def test_gare_organized_counts_director_assignment(db_session):
    """gare_organized include le gare assegnate via DirectorAssignment
    (ADR-037 open item 4), non solo Gara.director_id."""
    from datetime import date, timedelta as td
    from models.competition.services import GaraService
    from models.user.models import DirectorAssignment

    director = _user(role=UserRole.DIRECTOR)
    admin = _user(role=UserRole.ADMIN)

    # Gara standalone via director_id.
    GaraService.create_gara(
        number=1,
        name="Standalone",
        date=date.today() + td(days=2),
        discipline="8_ball",
        distance=5,
        director_id=director.id,
    )

    # Gara "di campionato" simulata: assegnazione esplicita via DirectorAssignment.
    other_gara = GaraService.create_gara(
        number=1,
        name="Assigned",
        date=date.today() + td(days=3),
        discipline="8_ball",
        distance=5,
        director_id=admin.id,
    )
    db.session.add(
        DirectorAssignment(
            user_id=director.id,
            entity_type="gara",
            entity_id=other_gara.id,
            assigned_by_id=admin.id,
        )
    )
    db.session.commit()

    b = CommunityLeaderboardService.compute_contribution(director.id)
    assert b["gare_organized"] == 2


def test_contribution_total_uses_weights(db_session, monkeypatch):
    """Il total del contributo rispetta CONTRIBUTION_WEIGHTS (taratura ADR-037)."""
    from models.gamification import community_leaderboard_service as mod

    author = _user(role=UserRole.DIRECTOR)
    other = _user()
    ch = _challenge(author.id)
    _attempt(ch.id, other.id, completed=True)  # 1 drill engaged

    # Peso 3 sui drill → total = 3 (gli altri componenti sono 0).
    monkeypatch.setitem(mod.CONTRIBUTION_WEIGHTS, "drills_engaged", 3)
    b = mod.CommunityLeaderboardService.compute_contribution(author.id)
    assert b["drills_engaged"] == 1
    assert b["total"] == 3


def test_performance_stats_shape_and_recommendation(db_session):
    """performance_stats espone i conteggi e NON raccomanda materializzazione
    su community piccola (ADR-037 KPI admin)."""
    author = _user(role=UserRole.DIRECTOR)
    other = _user()
    ch = _challenge(author.id)
    _attempt(ch.id, other.id, completed=True)

    stats = CommunityLeaderboardService.performance_stats()
    assert set(stats) >= {
        "contributors",
        "distinct_cities",
        "total_users",
        "contribution_compute_ms",
        "cache_ttl_seconds",
        "recommend_materialization",
        "reasons",
        "thresholds",
    }
    assert stats["contributors"] == 1  # solo l'autore ha contributo
    assert stats["recommend_materialization"] is False
    assert stats["reasons"] == []
    assert stats["contribution_compute_ms"] >= 0


def test_contribution_leaderboard_hydrates_from_cache(db_session):
    """get_contribution_leaderboard ritorna oggetti User idratati (non ORM in
    cache): lo username è accessibile senza DetachedInstanceError."""
    author = _user(role=UserRole.DIRECTOR)
    other = _user()
    ch = _challenge(author.id)
    _attempt(ch.id, other.id, completed=True)

    board = CommunityLeaderboardService.get_contribution_leaderboard()
    assert len(board) == 1
    assert board[0]["user"].username == author.username
    assert board[0]["score"] == 1
