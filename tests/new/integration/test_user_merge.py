# tests/new/integration/test_user_merge.py
"""Integration tests for UserMergeService.merge_users.

Covers: factual FK reassignment + source anonymization, per-row dedup on a
constrained table (user_level), head-to-head abort (rollback), and the
validation guards (self / admin / non-admin performer).
"""

import uuid
import warnings
from datetime import date, time, timedelta

import pytest
from sqlalchemy.exc import SAWarning

from models import db
from models.base import utc_now
from models.user.models import User
from models.user.role_enum import UserRole
from models.user.services import UserService
from models.exceptions import ConflictError, ValidationError
from models.competition.models import Gara
from models.match.models import Match
from models.classification.models import GaraClassification, RoundClassification
from models.status_enum import GaraStatus, MatchStatus
from models.gamification.models import UserLevel, XPTransaction, XPTransactionType


def _user(role="player"):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        username=f"{role}_{suffix}",
        email=f"{role}_{suffix}@example.com",
        role=UserRole.ADMIN.value if role == "admin" else role,
    )
    u.set_password("secret123")
    db.session.add(u)
    db.session.commit()
    return u


def _gara(director_id, status=GaraStatus.PLAYING.value):
    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:8]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        director_id=director_id,
        status=status,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() - timedelta(hours=1),
    )
    db.session.add(gara)
    db.session.flush()
    return gara


def _add_xp(user_id, amount):
    db.session.add(
        XPTransaction(
            user_id=user_id,
            transaction_type=XPTransactionType.MATCH_WIN,
            xp_amount=amount,
            reason="test",
            level_before=1,
            level_after=1,
        )
    )


def test_merge_reassigns_match_and_anonymizes_source(app, db_session):
    admin = _user("admin")
    source = _user()
    target = _user()
    third = _user()
    gara = _gara(admin.id)

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=source.id,
        player2_id=third.id,
        winner_id=source.id,
        status=MatchStatus.VALIDATED.value,
        ended_at=utc_now(),
    )
    db.session.add(match)
    _add_xp(source.id, 300)
    db.session.commit()

    source_id = source.id
    match_id = match.id
    UserService.merge_users(source_id, target.id, admin.id)

    reloaded_match = db_session.get(Match, match_id)
    assert reloaded_match.player1_id == target.id
    assert reloaded_match.winner_id == target.id

    src = db_session.execute(
        db.select(User)
        .where(User.id == source_id)
        .execution_options(include_deleted=True)
    ).scalar_one()
    assert src.deleted_at is not None
    assert src.email is None
    assert src.username.startswith(f"deleted-{source_id}-")

    # XP ledger moved to target → UserLevel rebuilt from the sum.
    target_level = db_session.get(UserLevel, target.id)
    assert target_level is not None
    assert target_level.total_xp == 300


def test_merge_dedup_user_level_no_integrity_error(app, db_session):
    admin = _user("admin")
    source = _user()
    target = _user()

    # Both have a UserLevel (PK = user_id) and some XP in the ledger.
    db.session.add(UserLevel(user_id=source.id, total_xp=100))
    db.session.add(UserLevel(user_id=target.id, total_xp=50))
    _add_xp(source.id, 100)
    _add_xp(target.id, 50)
    db.session.commit()

    source_id = source.id
    UserService.merge_users(source_id, target.id, admin.id)

    # Source UserLevel gone, target rebuilt from combined ledger (150).
    assert db_session.get(UserLevel, source_id) is None
    target_level = db_session.get(UserLevel, target.id)
    assert target_level is not None
    assert target_level.total_xp == 150


def test_merge_head_to_head_aborts_and_rolls_back(app, db_session):
    admin = _user("admin")
    source = _user()
    target = _user()
    gara = _gara(admin.id)

    db.session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=source.id,
            player2_id=target.id,
            status=MatchStatus.VALIDATED.value,
            ended_at=utc_now(),
        )
    )
    db.session.commit()
    source_id = source.id

    with pytest.raises(ConflictError):
        UserService.merge_users(source_id, target.id, admin.id)

    # Source must be untouched (not anonymized).
    src = db_session.get(User, source_id)
    assert src is not None
    assert src.deleted_at is None
    assert src.email is not None


def test_merge_no_sawarning_on_classification_recalc(app, db_session):
    """Regression #46: il ricalcolo classifiche nel merge non deve emettere
    la SAWarning "Identity map already had an identity ... replacing it".

    Lo scenario riproduce la causa: source e target hanno righe
    GaraClassification/RoundClassification in una gara conclusa. Il merge le
    riattribuisce a target e poi ricostruisce le classifiche con DELETE+INSERT;
    SQLite riusa i rowid liberati, quindi senza il fix gli oggetti caricati in
    identity-map collidono con gli INSERT freschi e SQLAlchemy avvisa.
    """
    admin = _user("admin")
    source = _user()
    target = _user()
    third = _user()
    gara = _gara(admin.id)
    gara.current_round = 1
    db.session.flush()

    # Match concluso source vs third: dopo il merge diventa target vs third e
    # alimenta il ricalcolo (l'aggregator legge i match finished con punteggi).
    db.session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=source.id,
            player2_id=third.id,
            player1_score=5,
            player2_score=2,
            winner_id=source.id,
            status=MatchStatus.VALIDATED.value,
            ended_at=utc_now(),
        )
    )

    # Righe di classifica pre-esistenti (di source e third): restano in
    # identity-map e vengono cancellate+reinserite dal ricalcolo.
    for user, pos, won, lost in [(source, 1, 5, 2), (third, 2, 2, 5)]:
        db.session.add(
            RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=user.id,
                position=pos,
                matches_won=1 if pos == 1 else 0,
                rack_difference=won - lost,
            )
        )
        db.session.add(
            GaraClassification(
                gara_id=gara.id,
                user_id=user.id,
                position=pos,
                matches_won=1 if pos == 1 else 0,
                racks_won=won,
                racks_lost=lost,
                rack_difference=won - lost,
            )
        )
    db.session.commit()

    source_id = source.id
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        UserService.merge_users(source_id, target.id, admin.id)

    identity_warnings = [
        w
        for w in caught
        if issubclass(w.category, SAWarning)
        and "Identity map already had an identity" in str(w.message)
    ]
    assert not identity_warnings, (
        "Il ricalcolo classifiche ha emesso SAWarning identity-map: "
        f"{[str(w.message) for w in identity_warnings]}"
    )

    # Le classifiche post-merge devono restare coerenti: target eredita la
    # posizione vincente, source sparisce dalle classifiche.
    gc_target = GaraClassification.query.filter_by(
        gara_id=gara.id, user_id=target.id
    ).one()
    assert gc_target.position == 1
    assert (
        GaraClassification.query.filter_by(gara_id=gara.id, user_id=source_id).count()
        == 0
    )


def test_merge_rejects_self(app, db_session):
    admin = _user("admin")
    target = _user()
    with pytest.raises(ValidationError):
        UserService.merge_users(target.id, target.id, admin.id)


def test_merge_rejects_admin_account(app, db_session):
    admin = _user("admin")
    other_admin = _user("admin")
    target = _user()
    with pytest.raises(ValidationError):
        UserService.merge_users(other_admin.id, target.id, admin.id)


def test_merge_requires_admin_performer(app, db_session):
    source = _user()
    target = _user()
    non_admin = _user()
    with pytest.raises(ValidationError):
        UserService.merge_users(source.id, target.id, non_admin.id)
