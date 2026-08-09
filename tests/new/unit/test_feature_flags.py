"""Unit tests for ADR-028 production endpoint allowlist engine."""

from __future__ import annotations

import pytest

from utils.feature_flags import (
    ENDPOINT_ROLES,
    INFRASTRUCTURE_ALLOWLIST,
    _user_roles,
    is_endpoint_visible,
)


class FakeUser:
    """Minimal stand-in for Flask-Login's current_user / AnonymousUserMixin."""

    def __init__(
        self,
        is_authenticated: bool = False,
        is_admin: bool = False,
        is_director: bool = False,
        is_player: bool = False,
        is_examiner: bool = False,
    ):
        self.is_authenticated = is_authenticated
        self.is_admin = is_admin
        self.is_director = is_director
        self.is_player = is_player
        self.is_examiner = is_examiner


@pytest.fixture
def production_mode(app):
    """Force production-style config (TESTING=False, DEBUG_MODE=False).

    Restored after the test so subsequent tests in the session see the usual
    test config. ``app`` is session-scoped, so leaking would corrupt later
    tests — the try/finally is non-negotiable.
    """
    orig_testing = app.config.get("TESTING")
    orig_debug = app.config.get("DEBUG_MODE")
    app.config["TESTING"] = False
    app.config["DEBUG_MODE"] = False
    try:
        yield
    finally:
        app.config["TESTING"] = orig_testing
        app.config["DEBUG_MODE"] = orig_debug


def test_passthrough_in_test_mode(app):
    """During tests (TESTING=True) every endpoint is visible regardless."""
    with app.app_context():
        anon = FakeUser()
        # Endpoint that is admin-only by default in production
        assert is_endpoint_visible("admin.kpi.index", anon) is True
        # And a non-existent endpoint too — irrelevant in tests, just verifies
        # the pass-through doesn't depend on the matrix.
        assert is_endpoint_visible("nonexistent.endpoint", anon) is True


def test_passthrough_in_dev_mode(app):
    """DEBUG_MODE=True (dev) also yields pass-through."""
    with app.app_context():
        orig_testing = app.config.get("TESTING")
        orig_debug = app.config.get("DEBUG_MODE")
        app.config["TESTING"] = False
        app.config["DEBUG_MODE"] = True
        try:
            anon = FakeUser()
            assert is_endpoint_visible("admin.kpi.index", anon) is True
        finally:
            app.config["TESTING"] = orig_testing
            app.config["DEBUG_MODE"] = orig_debug


def test_admin_bypass_in_production(app, production_mode):
    """Admin sees every endpoint in production, even those absent from matrix."""
    with app.app_context():
        admin = FakeUser(is_authenticated=True, is_admin=True)
        assert is_endpoint_visible("admin.kpi.index", admin) is True
        assert is_endpoint_visible("gamification.admin_dashboard", admin) is True
        assert is_endpoint_visible("nonexistent.endpoint", admin) is True


def test_anonymous_can_access_public_pages(app, production_mode):
    """Pages declared for {"anonimo", ...} are visible to non-authenticated users."""
    with app.app_context():
        anon = FakeUser()
        assert is_endpoint_visible("auth.login", anon) is True
        assert is_endpoint_visible("auth.register", anon) is True
        assert is_endpoint_visible("main.public_garas_list", anon) is True
        assert is_endpoint_visible("main.gara_detail_public", anon) is True


def test_anonymous_blocked_from_logged_in_pages(app, production_mode):
    """Pages declared only for {"player", "director"} are 404 for anonymous."""
    with app.app_context():
        anon = FakeUser()
        assert is_endpoint_visible("dashboard.dashboard", anon) is False
        assert is_endpoint_visible("player.profile", anon) is False
        assert is_endpoint_visible("player.add_rack_simplified", anon) is False


def test_player_sees_player_endpoints(app, production_mode):
    """A regular player has access to logged-in non-director endpoints."""
    with app.app_context():
        player = FakeUser(is_authenticated=True, is_player=True)
        assert is_endpoint_visible("dashboard.dashboard", player) is True
        assert is_endpoint_visible("player.profile", player) is True
        assert is_endpoint_visible("player.inscribe_to_gara", player) is True
        assert is_endpoint_visible("player.add_rack_simplified", player) is True


def test_player_blocked_from_director_only(app, production_mode):
    """A player cannot see director-only management endpoints."""
    with app.app_context():
        player = FakeUser(is_authenticated=True, is_player=True)
        assert is_endpoint_visible("admin.campionato.wizard_start", player) is False
        assert (
            is_endpoint_visible("admin.competition.create_gara_standalone", player)
            is False
        )
        # admin.match.match_detail is the unified match view (player + director),
        # see B8 fix and the comment in utils/feature_flags.py.
        assert (
            is_endpoint_visible("admin.match.set_match_result_direct", player) is False
        )


def test_director_sees_director_endpoints(app, production_mode):
    """A director has access to gara/campionato management endpoints."""
    with app.app_context():
        director = FakeUser(is_authenticated=True, is_director=True)
        assert is_endpoint_visible("admin.campionato.wizard_start", director) is True
        assert (
            is_endpoint_visible("admin.competition.create_gara_standalone", director)
            is True
        )
        assert is_endpoint_visible("admin.match.match_detail", director) is True


def test_director_also_sees_player_endpoints(app, production_mode):
    """A director can also play in someone else's gara, so player endpoints
    that include "director" in their role set must be reachable."""
    with app.app_context():
        director = FakeUser(is_authenticated=True, is_director=True)
        assert is_endpoint_visible("dashboard.dashboard", director) is True
        assert is_endpoint_visible("player.profile", director) is True
        assert is_endpoint_visible("player.inscribe_to_gara", director) is True
        assert is_endpoint_visible("player.add_rack_simplified", director) is True


def test_unlisted_endpoint_admin_only(app, production_mode):
    """Endpoints absent from ENDPOINT_ROLES are admin-only by default."""
    with app.app_context():
        # gamification.admin_dashboard is NOT in the MVP matrix
        assert "gamification.admin_dashboard" not in ENDPOINT_ROLES

        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)

        assert is_endpoint_visible("gamification.admin_dashboard", anon) is False
        assert is_endpoint_visible("gamification.admin_dashboard", player) is False
        assert is_endpoint_visible("gamification.admin_dashboard", director) is False
        assert is_endpoint_visible("gamification.admin_dashboard", admin) is True


def test_gamification_hidden_from_player_and_anonymous(app, production_mode):
    """Gamification UI/API are director-only (admin bypasses). Player and
    anonymous viewers must NOT see them in production until the feature
    stabilises — toasts/widgets are filtered by feature_visible() and the
    nudge/unlock dispatcher in models/gamification/frontend_bridge.py."""
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)

        for endpoint in (
            "gamification.dashboard",
            "gamification.achievements",
            "gamification.quests",
            "gamification.streaks",
            "gamification.leaderboards",
            "gamification.api_level_progress",
            "gamification.api_user_stats",
            "gamification.api_achievements",
            "gamification.api_streaks",
        ):
            assert is_endpoint_visible(endpoint, anon) is False, endpoint
            assert is_endpoint_visible(endpoint, player) is False, endpoint
            assert is_endpoint_visible(endpoint, director) is True, endpoint
            assert is_endpoint_visible(endpoint, admin) is True, endpoint


def test_privacy_endpoints_visible_to_player_and_director(app, production_mode):
    """Privacy controls (privacy_settings + hide/show toggles for
    matches/inscriptions/campionati) must be reachable by every logged-in
    user managing their own data — both player and director."""
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)

        for endpoint in (
            "player.privacy_settings",
            "player.hide_match",
            "player.show_match",
            "player.hide_inscription",
            "player.show_inscription",
            "player.hide_campionato",
            "player.show_campionato",
        ):
            assert is_endpoint_visible(endpoint, anon) is False, endpoint
            assert is_endpoint_visible(endpoint, player) is True, endpoint
            assert is_endpoint_visible(endpoint, director) is True, endpoint


def test_delete_account_visible_to_player_and_director(app, production_mode):
    """Self-service account deletion (player.delete_account) must be reachable
    by every logged-in user managing their own account — player and director.

    Regression: the endpoint was missing from ENDPOINT_ROLES, so in production
    it fell through to admin-only and a real player hitting the "Elimina
    account" link got a 404 (ADR-028). Anonymous users still 404 (they have no
    account to delete); admin bypasses the matrix.
    """
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)

        assert is_endpoint_visible("player.delete_account", anon) is False
        assert is_endpoint_visible("player.delete_account", player) is True
        assert is_endpoint_visible("player.delete_account", director) is True
        assert is_endpoint_visible("player.delete_account", admin) is True


def test_infrastructure_allowlist_visible_to_everyone(app, production_mode):
    """Polling and static endpoints are reachable for every role."""
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)
        for endpoint in INFRASTRUCTURE_ALLOWLIST:
            assert is_endpoint_visible(endpoint, anon) is True
            assert is_endpoint_visible(endpoint, player) is True
            assert is_endpoint_visible(endpoint, director) is True
            assert is_endpoint_visible(endpoint, admin) is True


def test_none_endpoint_is_passthrough(app, production_mode):
    """When request.endpoint is None (no rule matched), Flask raises 404
    on its own — the middleware must not interfere by returning False."""
    with app.app_context():
        anon = FakeUser()
        assert is_endpoint_visible(None, anon) is True


def test_polymorphic_endpoint_for_all_roles(app, production_mode):
    """The unified gara detail view is a polymorphic endpoint: same URL,
    template adapts to the viewer's role."""
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        ep = "admin.competition.gara_detail"
        assert is_endpoint_visible(ep, anon) is True
        assert is_endpoint_visible(ep, player) is True
        assert is_endpoint_visible(ep, director) is True


def test_user_roles_is_a_set_not_a_single_role(app, production_mode):
    """Il ruolo primario e i ruoli concedibili coesistono (ADR-038).

    Regressione: con un solo ruolo string-valued, un esaminatore che non è
    anche director ricadeva in "player" e perdeva ogni endpoint dichiarato
    per {"examiner"} in produzione.
    """
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        examiner = FakeUser(is_authenticated=True, is_player=True, is_examiner=True)
        director_examiner = FakeUser(
            is_authenticated=True, is_director=True, is_examiner=True
        )

        assert _user_roles(anon) == {"anonimo"}
        assert _user_roles(player) == {"player"}
        assert _user_roles(examiner) == {"player", "examiner"}
        assert _user_roles(director_examiner) == {"director", "examiner"}


def test_examiner_not_degraded_to_player(app, production_mode, monkeypatch):
    """Un endpoint dichiarato {"examiner"} è visibile a un esaminatore che NON
    è director, e invisibile a un player qualunque.

    Il test monkeypatcha la matrice invece di leggerla: quello che va protetto
    dalla regressione è la **semantica a intersezione** del motore, non lo
    stato del rollout (oggi la superficie /roles è ancora admin-only, vedi
    ``test_role_endpoints_are_dark_until_phase_5``).
    """
    with app.app_context():
        monkeypatch.setitem(ENDPOINT_ROLES, "roles.role_requests", {"examiner"})

        player = FakeUser(is_authenticated=True, is_player=True)
        examiner = FakeUser(is_authenticated=True, is_player=True, is_examiner=True)

        assert is_endpoint_visible("roles.role_requests", player) is False
        assert is_endpoint_visible("roles.role_requests", examiner) is True

        # E non perde per strada gli endpoint del suo ruolo primario.
        assert is_endpoint_visible("dashboard.dashboard", examiner) is True
        assert is_endpoint_visible("player.profile", examiner) is True


def test_grantable_role_is_not_probed_when_endpoint_ignores_it(app, production_mode):
    """``is_endpoint_visible`` non accerta i ruoli concedibili se non servono.

    ``is_examiner`` fa una query su ``role_grant``, e ``feature_visible()`` è
    un global di template chiamato una volta per ogni link protetto: senza il
    corto circuito una singola pagina costerebbe decine di SELECT. Qui
    l'utente finto esplode se qualcuno legge ``is_examiner``, così il test
    fallisce se il corto circuito viene rimosso.
    """

    class ExplodingExaminerUser:
        """Player normale, ma leggere ``is_examiner`` è un errore."""

        is_authenticated = True
        is_admin = False
        is_director = False
        is_player = True

        @property
        def is_examiner(self):  # pragma: no cover - deve non essere chiamata
            raise AssertionError("is_examiner non va accertato per questo endpoint")

    with app.app_context():
        user = ExplodingExaminerUser()

        # Endpoint concesso dal solo ruolo primario: risposta senza query.
        assert is_endpoint_visible("dashboard.dashboard", user) is True
        # Endpoint negato che non ammette concedibili: idem.
        assert is_endpoint_visible("admin.campionato.wizard_start", user) is False
        # Endpoint assente dalla matrice (admin-only): idem.
        assert is_endpoint_visible("gamification.admin_dashboard", user) is False


def test_grantable_role_is_probed_when_endpoint_admits_it(
    app, production_mode, monkeypatch
):
    """Il corto circuito non deve rendere i ruoli concedibili inefficaci."""
    with app.app_context():
        monkeypatch.setitem(ENDPOINT_ROLES, "roles.role_requests", {"examiner"})

        player = FakeUser(is_authenticated=True, is_player=True)
        examiner = FakeUser(is_authenticated=True, is_player=True, is_examiner=True)

        assert is_endpoint_visible("roles.role_requests", player) is False
        assert is_endpoint_visible("roles.role_requests", examiner) is True


def test_role_endpoints_are_dark_until_phase_5(app, production_mode):
    """ROLLOUT: la superficie /roles è admin-only finché gli esami non esistono.

    Il ruolo di esaminatore serve a somministrare esami: esporlo prima delle
    Fasi 2-5 offrirebbe ai giocatori un percorso che non porta da nessuna
    parte. Admin bypassa la matrice, quindi il bootstrap resta possibile.

    Quando la Fase 5 accende il catalogo esami, questo test va aggiornato
    insieme alle entry di ``ENDPOINT_ROLES``.
    """
    with app.app_context():
        anon = FakeUser()
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        examiner = FakeUser(is_authenticated=True, is_player=True, is_examiner=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)

        role_endpoints = [ep for ep in ENDPOINT_ROLES if ep.startswith("roles.")]
        assert role_endpoints, "le entry roles.* devono essere dichiarate"

        for endpoint in role_endpoints:
            for viewer in (anon, player, director, examiner):
                assert is_endpoint_visible(endpoint, viewer) is False, endpoint
            assert is_endpoint_visible(endpoint, admin) is True, endpoint


def test_logged_in_user_blocked_from_anonymous_only(app, production_mode):
    """Login/register pages are declared {"anonimo"} only — a logged-in
    player landing there in production gets 404 (he should be redirected
    to the dashboard by the login_view, but if he forces the URL we 404
    rather than expose stale flows). Admin still bypasses."""
    with app.app_context():
        player = FakeUser(is_authenticated=True, is_player=True)
        director = FakeUser(is_authenticated=True, is_director=True)
        admin = FakeUser(is_authenticated=True, is_admin=True)
        assert is_endpoint_visible("auth.login", player) is False
        assert is_endpoint_visible("auth.login", director) is False
        assert is_endpoint_visible("auth.login", admin) is True
