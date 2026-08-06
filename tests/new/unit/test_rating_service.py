"""Unit test del dominio rating (prima senza test dedicati).

Copre ``RatingService`` (categorie, categoria effettiva, rating, handicap match,
leaderboard/statistiche) e ``HandicapService`` (CRUD regole + calcolo).
"""

import uuid

import pytest

from models.base import db
from models.user.role_enum import UserRole
from models.rating.models import (
    PlayerCategory,
    PlayerRating,
    CategoryLevel,
    RatingSystem,
)
from models.rating.rating_service import RatingService, CategoryService
from models.rating.handicap_service import HandicapService


def _user():
    uid = str(uuid.uuid4())[:8]
    from models import User

    u = User(
        username=f"r_{uid}",
        email=f"r_{uid}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    return u


# ── Categorie ────────────────────────────────────────────────────────────────


def test_assign_category_creates_active_and_single(db_session):
    user = _user()
    admin = _user()
    CategoryService.assign_category(user.id, CategoryLevel.B, assigned_by_id=admin.id)

    current = CategoryService.get_user_current_category(user.id)
    assert current is not None and current.category == CategoryLevel.B
    assert current.is_active is True

    # Riassegnando, la vecchia categoria viene disattivata: una sola attiva.
    CategoryService.assign_category(user.id, CategoryLevel.A, assigned_by_id=admin.id)
    actives = PlayerCategory.query.filter_by(user_id=user.id, is_active=True).all()
    assert len(actives) == 1
    assert actives[0].category == CategoryLevel.A


def test_effective_category_prefers_assigned(db_session):
    user = _user()
    admin = _user()
    CategoryService.assign_category(user.id, CategoryLevel.C, assigned_by_id=admin.id)
    assert RatingService.get_player_effective_category(user.id) == CategoryLevel.C


def test_effective_category_defaults_to_D_without_data(db_session):
    user = _user()
    assert RatingService.get_player_effective_category(user.id) == CategoryLevel.D


def test_effective_category_derived_from_rating(db_session):
    user = _user()
    # Nessuna categoria assegnata, ma un rating Fargo alto → categoria derivata.
    RatingService.update_player_rating(user.id, RatingSystem.FARGO, 700)
    derived = RatingService.get_player_effective_category(user.id)
    # Fargo 700 è "Advanced" → A (vedi get_category_equivalent).
    assert derived == CategoryLevel.A


def test_get_user_category_info_shape(db_session):
    user = _user()
    admin = _user()
    CategoryService.assign_category(user.id, CategoryLevel.B, assigned_by_id=admin.id)
    info = CategoryService.get_user_category_info(user.id)
    assert info["current_category"].category == CategoryLevel.B
    assert info["effective_category"] == CategoryLevel.B
    assert info["is_rating_derived"] is False
    assert info["has_category_history"] is True


def test_expire_category(db_session):
    user = _user()
    admin = _user()
    cat = CategoryService.assign_category(
        user.id, CategoryLevel.B, assigned_by_id=admin.id
    )
    CategoryService.expire_category(cat.id)
    assert CategoryService.get_user_current_category(user.id) is None


def test_expire_category_unknown_raises(db_session):
    with pytest.raises(ValueError):
        CategoryService.expire_category(999999)


# ── Rating ───────────────────────────────────────────────────────────────────


def test_update_player_rating_create_and_update(db_session):
    user = _user()
    r = RatingService.update_player_rating(user.id, RatingSystem.ELO, 1500)
    assert r.rating_value == 1500
    # Aggiornamento dello stesso sistema: stessa riga, nuovo valore.
    r2 = RatingService.update_player_rating(user.id, RatingSystem.ELO, 1600)
    assert r2.id == r.id and r2.rating_value == 1600
    assert (
        PlayerRating.query.filter_by(
            user_id=user.id, rating_system=RatingSystem.ELO
        ).count()
        == 1
    )


# ── Handicap ─────────────────────────────────────────────────────────────────


def test_calculate_handicap_no_rule(db_session):
    p1, p2 = _user(), _user()
    result = HandicapService.calculate_handicap(p1.id, p2.id)
    assert result["method"] == "no_rule"
    assert result["player1_handicap"] == 0 and result["player2_handicap"] == 0


def test_create_rule_get_all_and_toggle(db_session):
    rule = HandicapService.create_handicap_rule(
        name="Standard",
        description="A vs C",
        category_rules=[
            {"higher_category": "A", "lower_category": "C", "handicap_value": 2}
        ],
    )
    assert rule.id is not None

    allr = HandicapService.get_all_rules()
    assert allr["total_rules"] == 1
    assert len(allr["active_rules"]) == 1

    HandicapService.update_rule_status(rule.id, is_active=False)
    allr2 = HandicapService.get_all_rules()
    assert len(allr2["active_rules"]) == 0
    assert len(allr2["inactive_rules"]) == 1


def test_update_rule_status_unknown_raises(db_session):
    with pytest.raises(ValueError):
        HandicapService.update_rule_status(999999, is_active=False)


def test_calculate_handicap_with_category_rule(db_session):
    admin = _user()
    p_a, p_c = _user(), _user()
    CategoryService.assign_category(p_a.id, CategoryLevel.A, assigned_by_id=admin.id)
    CategoryService.assign_category(p_c.id, CategoryLevel.C, assigned_by_id=admin.id)

    HandicapService.create_handicap_rule(
        name="Std",
        category_rules=[
            {"higher_category": "A", "lower_category": "C", "handicap_value": 2}
        ],
    )

    result = HandicapService.calculate_handicap(p_a.id, p_c.id)
    # Con regola di categoria attiva il metodo non è "no_rule" e c'è un handicap.
    assert result["method"] != "no_rule"
    assert "player1_handicap" in result and "player2_handicap" in result


# ── Smoke read-model ─────────────────────────────────────────────────────────


def test_leaderboard_and_statistics_smoke(db_session):
    user = _user()
    admin = _user()
    CategoryService.assign_category(user.id, CategoryLevel.B, assigned_by_id=admin.id)
    RatingService.update_player_rating(user.id, RatingSystem.FARGO, 500)

    lb = RatingService.get_public_leaderboard()
    assert isinstance(lb, dict)
    stats = RatingService.get_system_statistics()
    assert isinstance(stats, dict)
