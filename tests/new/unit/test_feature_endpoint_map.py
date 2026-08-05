"""Unit tests for the gamification ↔ ADR-028 allowlist alignment.

Verifica che ``feature_visible_to_user`` rispetti la matrice
``ENDPOINT_ROLES`` quando una feature è mappata a un endpoint, e che
features non mappate (UI-only) restino sempre proponibili.
"""

from __future__ import annotations

import pytest

from models.gamification.feature_endpoint_map import (
    FEATURE_PRIMARY_ENDPOINT,
    feature_visible_to_user,
)


class FakeUser:
    """Stand-in per ``current_user`` (vedi test_feature_flags.py)."""

    def __init__(
        self,
        is_authenticated: bool = False,
        is_admin: bool = False,
        is_director: bool = False,
        is_player: bool = False,
    ):
        self.is_authenticated = is_authenticated
        self.is_admin = is_admin
        self.is_director = is_director
        self.is_player = is_player


@pytest.fixture
def production_mode(app):
    """Forza configurazione production-like (cfr. test_feature_flags.py)."""
    orig_testing = app.config.get("TESTING")
    orig_debug = app.config.get("DEBUG_MODE")
    app.config["TESTING"] = False
    app.config["DEBUG_MODE"] = False
    try:
        yield
    finally:
        app.config["TESTING"] = orig_testing
        app.config["DEBUG_MODE"] = orig_debug


def test_unmapped_feature_is_always_proponibile(app, production_mode):
    """Una feature UI-only (senza endpoint in mappa) resta sempre proposta."""
    with app.app_context():
        director = FakeUser(is_authenticated=True, is_director=True)
        # legend_status / priority_invites / custom_badge_display: UI-only
        assert feature_visible_to_user("legend_status", director) is True
        assert feature_visible_to_user("priority_invites", director) is True


def test_mapped_feature_hidden_when_endpoint_not_allowlisted(app, production_mode):
    """Feature mappata a endpoint non in ENDPOINT_ROLES → suppressa per non-admin.

    Caso reale: ``do_challenge`` mappa a ``challenge.challenge_catalog``, non
    ancora in allowlist (feature challenge admin-only in prod). Senza questo
    filtro la gamification proporrebbe a un director un nudge che il navbar
    nasconde e l'URL diretto restituisce 404.
    """
    with app.app_context():
        director = FakeUser(is_authenticated=True, is_director=True)
        player = FakeUser(is_authenticated=True, is_player=True)
        anon = FakeUser()

        assert feature_visible_to_user("do_challenge", director) is False
        assert feature_visible_to_user("do_challenge", player) is False
        assert feature_visible_to_user("do_challenge", anon) is False


def test_mapped_feature_visible_when_endpoint_allowlisted(app, production_mode):
    """Feature mappata a endpoint che il ruolo VEDE → proponibile."""
    with app.app_context():
        director = FakeUser(is_authenticated=True, is_director=True)
        player = FakeUser(is_authenticated=True, is_player=True)
        # admin.competition.create_gara_standalone è in matrice per "director"
        assert feature_visible_to_user("create_gara", director) is True
        # create_match_direct → individual_match.dashboard, ora abilitato per
        # player e director (ADR-028: feature match individuali attivata).
        assert feature_visible_to_user("create_match_direct", director) is True
        assert feature_visible_to_user("create_match_direct", player) is True


def test_admin_sees_every_mapped_feature(app, production_mode):
    """Admin bypassa la matrice → ogni feature mappata risulta proponibile."""
    with app.app_context():
        admin = FakeUser(is_authenticated=True, is_admin=True)
        for code in FEATURE_PRIMARY_ENDPOINT:
            assert feature_visible_to_user(code, admin) is True, code


def test_passthrough_in_dev_mode(app):
    """In dev (DEBUG_MODE=True) ogni feature mappata è proponibile."""
    with app.app_context():
        orig_testing = app.config.get("TESTING")
        orig_debug = app.config.get("DEBUG_MODE")
        app.config["TESTING"] = False
        app.config["DEBUG_MODE"] = True
        try:
            director = FakeUser(is_authenticated=True, is_director=True)
            # Anche se l'endpoint non è in ENDPOINT_ROLES, in dev pass-through.
            assert feature_visible_to_user("create_match_direct", director) is True
        finally:
            app.config["TESTING"] = orig_testing
            app.config["DEBUG_MODE"] = orig_debug


def test_all_mapped_endpoints_actually_exist(app):
    """Ogni endpoint nella mappa deve corrispondere a una rotta registrata.

    Equivalente a ``test_endpoint_roles_names_are_real`` per la mappa
    feature → endpoint: una typo silenziosa qui equivale a un nudge mai
    inviato (la feature risulterebbe sempre nascosta in prod), che è un
    bug subdolo.
    """
    with app.app_context():
        all_endpoints = {r.endpoint for r in app.url_map.iter_rules()}
        missing = [
            ep for ep in FEATURE_PRIMARY_ENDPOINT.values() if ep not in all_endpoints
        ]
        assert not missing, f"Endpoint mappati inesistenti: {missing}"
