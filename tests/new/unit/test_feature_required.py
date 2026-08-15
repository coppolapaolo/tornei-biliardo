"""L'enforcement del layer L2 (progressione) lato server.

Fino a qui ``can_access`` viveva **solo nei template**: la voce di menu spariva,
ma la POST diretta passava lo stesso. ``player.request_director`` era
raggiungibile senza aver sbloccato nulla — buco noto n.1 del piano esami.

Qui si verifica il decoratore che chiude quel buco, e i due bypass che deve
continuare a rispettare perché sono la via di debug prevista (US-D1):
``gamification_override`` e admin.
"""

from __future__ import annotations

import uuid

import pytest
from flask import abort
from flask_login import login_user

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from utils.permissions import examiner_required, feature_required

pytestmark = pytest.mark.unit


LOCKED_FEATURE = "create_match_direct"  # seminata in conftest: 5+ match


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=role,
        **kwargs,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _guarded_view():
    """Vista fittizia protetta dal decoratore."""

    @feature_required(LOCKED_FEATURE)
    def view():
        return "ok"

    return view


def _call_as(app, user, view):
    """Esegue la vista con ``user`` autenticato, restituendo il risultato."""
    with app.test_request_context("/x"):
        if user is not None:
            login_user(user)
        return view()


class TestFeatureRequired:
    def test_a_locked_feature_is_refused(self, app, db_session):
        """Zero match giocati, feature che ne chiede 5: 403, non un redirect."""
        user = _make_user()
        view = _guarded_view()

        with pytest.raises(Exception) as exc:
            _call_as(app, user, view)
        assert "403" in str(exc.value)

    def test_the_gamification_override_opens_it(self, app, db_session):
        """È l'override già esistente, quello che lo sviluppatore attiva da admin."""
        user = _make_user(gamification_override=True)
        assert _call_as(app, user, _guarded_view()) == "ok"

    def test_admin_passes_through(self, app, db_session):
        admin = _make_user(role=UserRole.ADMIN.value)
        assert _call_as(app, admin, _guarded_view()) == "ok"

    def test_an_unseeded_feature_code_stays_open(self, app, db_session):
        """``UnlockEngine`` è fail-open sui codici non ancora seminati.

        Non è un dettaglio innocuo: finché la migration di seed non è girata,
        un ``feature_required("take_exam")`` non blocca nessuno. Il test lo
        fissa perché sia una scelta consapevole e non una sorpresa in
        produzione — l'unica difesa vera resta ADR-028 (endpoint non listato =
        admin-only).
        """

        @feature_required("codice_che_non_esiste")
        def view():
            return "ok"

        assert _call_as(app, _make_user(), view) == "ok"

    def test_an_anonymous_visitor_is_sent_to_the_login(self, app):
        """Senza utente non c'è progressione da valutare: si passa dal login."""
        with app.test_request_context("/x"):
            response = _guarded_view()()
        assert response.status_code in (301, 302)
        assert "/login" in response.headers.get("Location", "")


class TestExaminerRequired:
    def test_a_player_without_the_grant_is_refused(self, app, db_session):
        @examiner_required
        def view():
            return "ok"

        with pytest.raises(Exception) as exc:
            _call_as(app, _make_user(), view)
        assert "403" in str(exc.value)

    def test_the_grant_holder_passes(self, app, db_session):
        from models.user.role_enum import GrantableRole
        from models.user.role_grant_service import RoleGrantService

        admin = _make_user(role=UserRole.ADMIN.value)
        examiner = _make_user()
        RoleGrantService.grant(examiner.id, GrantableRole.EXAMINER, granted_by=admin)
        db.session.commit()

        @examiner_required
        def view():
            return "ok"

        assert _call_as(app, examiner, view) == "ok"

    def test_admin_is_examiner_too(self, app, db_session):
        """Stessa semantica di ``is_venue_manager``: admin vede tutto."""

        @examiner_required
        def view():
            return "ok"

        assert _call_as(app, _make_user(role=UserRole.ADMIN.value), view) == "ok"

    def test_an_anonymous_visitor_is_sent_to_the_login(self, app):
        """Non ha *ancora* il ruolo, non gli è stato *negato*: login, non 403.

        Il controllo vive nel decoratore e non è delegato a un
        ``@login_required`` sopra, così regge anche applicato da solo.
        """

        @examiner_required
        def view():
            return "ok"

        with app.test_request_context("/x"):
            response = view()
        assert response.status_code in (301, 302)
        assert "/login" in response.headers.get("Location", "")


def test_the_decorators_do_not_swallow_the_view_errors(app, db_session):
    """Un 404 sollevato dalla vista deve restare un 404, non diventare 403."""

    @feature_required(LOCKED_FEATURE)
    def view():
        abort(404)

    user = _make_user(gamification_override=True)
    with pytest.raises(Exception) as exc:
        _call_as(app, user, view)
    assert "404" in str(exc.value)
