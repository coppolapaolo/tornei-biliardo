"""Parsing dei form per il flag handicap (Gara tri-state, Campionato checkbox).

Feature (2026-06): l'handicap mode è configurabile via UI su campionato/gara.
- GaraFormParser: select tri-state "" (eredita→None) / "true" / "false".
- CampionatoFormParser: checkbox booleano.
"""

from __future__ import annotations

import pytest

from routes.admin.competition.form_parser import GaraFormParser
from routes.admin.campionato_form_parser import CampionatoFormParser


def _gara_form(app, **extra):
    base = {
        "date": "2026-12-01",
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "2",
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
    }
    base.update(extra)
    return app.test_request_context(method="POST", data=base)


@pytest.mark.unit
def test_gara_parser_handicap_true(app):
    with _gara_form(app, has_handicap="true"):
        data = GaraFormParser(campionato=None).parse()
    assert data["has_handicap"] is True


@pytest.mark.unit
def test_gara_parser_handicap_false(app):
    with _gara_form(app, has_handicap="false"):
        data = GaraFormParser(campionato=None).parse()
    assert data["has_handicap"] is False


@pytest.mark.unit
def test_gara_parser_handicap_inherit_when_empty(app):
    with _gara_form(app, has_handicap=""):
        data = GaraFormParser(campionato=None).parse()
    assert data["has_handicap"] is None


@pytest.mark.unit
def test_gara_parser_handicap_inherit_when_absent(app):
    with _gara_form(app):  # campo assente del tutto
        data = GaraFormParser(campionato=None).parse()
    assert data["has_handicap"] is None


@pytest.mark.unit
def test_campionato_parser_handicap_checked(app):
    with app.test_request_context(method="POST", data={"has_handicap": "on"}):
        from flask import request

        settings = CampionatoFormParser.parse_default_settings(request.form)
    assert settings["has_handicap"] is True


@pytest.mark.unit
def test_campionato_parser_handicap_unchecked(app):
    with app.test_request_context(method="POST", data={}):
        from flask import request

        settings = CampionatoFormParser.parse_default_settings(request.form)
    assert settings["has_handicap"] is False
