"""Regression: create_handicap_rule costruisce RatingHandicapRule con i campi giusti.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/rating/handicap_service.py:83`:

create_handicap_rule costruiva RatingHandicapRule con kwargs inesistenti
(`rating_difference_threshold`, `handicap_per_point`). Il modello ha invece
`min_difference`, `max_difference`, `points_per_handicap`, `max_handicap`
(vedi create_standard_handicap_rule, che usa i nomi giusti). Risultato:
TypeError 'invalid keyword argument' → la creazione di una regola con
rating_rules falliva sempre.
"""

from __future__ import annotations

import pytest

from models.rating.handicap_service import HandicapService
from models.rating.models import RatingHandicapRule, RatingSystem


@pytest.mark.unit
def test_create_handicap_rule_with_rating_rules(db_session):
    rule = HandicapService.create_handicap_rule(
        name="Test Rating Rule",
        description="x",
        rating_rules=[
            {
                "rating_system": "fargo",
                "min_difference": 50,
                "max_difference": 500,
                "points_per_handicap": 100,
                "max_handicap": 5,
            }
        ],
    )
    db_session.flush()

    rating_rules = RatingHandicapRule.query.filter_by(rule_id=rule.id).all()
    assert len(rating_rules) == 1
    rr = rating_rules[0]
    assert rr.rating_system == RatingSystem.FARGO
    assert rr.min_difference == 50
    assert rr.max_difference == 500
    assert rr.points_per_handicap == 100
    assert rr.max_handicap == 5


@pytest.mark.unit
def test_create_handicap_rule_rating_rules_defaults(db_session):
    """Campi opzionali assenti: usa i default del modello (min=50, points=100)."""
    rule = HandicapService.create_handicap_rule(
        name="Test Defaults",
        rating_rules=[{"rating_system": "elo"}],
    )
    db_session.flush()

    rr = RatingHandicapRule.query.filter_by(rule_id=rule.id).first()
    assert rr is not None
    assert rr.rating_system == RatingSystem.ELO
    assert rr.min_difference == 50
    assert rr.points_per_handicap == 100
    assert rr.max_difference is None
    assert rr.max_handicap is None
