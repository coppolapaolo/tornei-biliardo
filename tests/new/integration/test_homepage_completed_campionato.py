"""Regression tests: completed campionato must NOT appear in the
"active" homepage section.

Bug: a campionato where all gare were COMPLETED naturally (without
manual termination) kept `is_active=True`, so the previous
`HomepageService.get_homepage_data()` query (filter_by(is_active=True))
listed it under "Campionati Attivi" — with the badge "Completato" — which
contradicted the section header.

Fix: HomepageService now partitions by derived status
(`compute_campionato_status`), exposes `active_count` separately, and
appends at most HOMEPAGE_COMPLETED_LIMIT completed campionati as a
"recent completed" tail. The /campionatos page provides full browsing.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara
from models.campionato.homepage_service import (
    HomepageService,
    HOMEPAGE_COMPLETED_LIMIT,
)
from models.campionato.services import TournamentService
from models.competition.services import GaraService
from models.status_enum import GaraStatus, TournamentStatus


def _guest_render(app, endpoint_path, query_string=""):
    """Render a route as a guest by pushing a fresh anonymous request
    context.

    We deliberately do not go through `app.test_client()`: when other
    tests on the same xdist worker have logged users in, Flask-Login
    state can survive at the app/session level, and `current_user`
    resolves to a (detached) authenticated user — making `/` redirect
    to `/dashboard`. A bare `test_request_context` is the only way to
    guarantee `current_user.is_authenticated is False`.
    """
    from flask_login import AnonymousUserMixin

    url = endpoint_path + ("?" + query_string if query_string else "")
    with app.test_request_context(url):
        # Force anonymous: Flask-Login reads session, which is empty here
        from flask import g
        g._login_user = AnonymousUserMixin()
        # Dispatch through the app: matches the URL and runs the view
        # function with the normal middleware/before_request chain.
        return app.full_dispatch_request()


def _make_campionato(name_prefix: str, director_id: int) -> Campionato:
    """Helper to build a campionato with a unique name."""
    suffix = uuid.uuid4().hex[:6]
    return TournamentService().create_campionato_with_director(
        name=f"{name_prefix}_{suffix}",
        creator_user_id=director_id,
        campionato_type="Amalfi",
        is_active=True,
    )


def _add_completed_gara(
    db_session, campionato_id: int, number: int, director_id: int
) -> Gara:
    """Create a gara attached to a campionato, then force its status to
    COMPLETED.

    Note: `GaraService.create_gara` rejects dates in the past, so we
    create with a future date and only afterwards mark the gara as
    COMPLETED (the model itself has no such validation post-creation).
    """
    gara = GaraService.create_gara(
        campionato_id=campionato_id,
        number=number,
        name=f"Gara {number}",
        date=date.today() + timedelta(days=number),
        location="Test Venue",
        description="completed",
        rounds_count=1,
        min_participants=2,
        max_participants=4,
        entry_fee=0.0,
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        director_id=director_id,
        matchmaking_strategy="amalfi",
    )
    gara.status = GaraStatus.COMPLETED.value
    db_session.commit()
    return gara


@pytest.mark.integration
class TestHomepageCompletedCampionato:
    """Regression for: completed campionato shown as Attivo on homepage."""

    def test_completed_campionato_does_not_count_as_active(
        self, db_session, isolated_director_user
    ):
        """A campionato with all gare COMPLETED must not increase
        `active_count`. It may still appear in `tournaments_data` as part
        of the "recent completed" tail."""
        campionato = _make_campionato("Old", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)

        # Sanity: derived status is COMPLETED, is_active is still True
        assert campionato.is_active is True
        assert campionato.get_status() == TournamentStatus.COMPLETED.value

        data = HomepageService.get_homepage_data()
        assert data is not None
        assert data["active_count"] == 0
        assert data["completed_total"] == 1
        assert data["completed_shown"] == 1
        # Tail: campionato is rendered, but the section header reads "0 attivi"
        assert any(
            d["campionato"].id == campionato.id for d in data["tournaments_data"]
        )

    def test_in_progress_campionato_counts_as_active(
        self, db_session, isolated_director_user
    ):
        """A campionato with at least one PLAYING gara counts as active."""
        campionato = _make_campionato("Live", isolated_director_user.id)
        gara = _add_completed_gara(
            db_session, campionato.id, 1, isolated_director_user.id
        )
        gara.status = GaraStatus.PLAYING.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        assert data["active_count"] == 1
        assert data["completed_total"] == 0

    def test_completed_tail_caps_at_homepage_limit(
        self, db_session, isolated_director_user
    ):
        """When there are more than HOMEPAGE_COMPLETED_LIMIT completed
        campionati, only the most recent are shown; the rest live behind
        the /campionatos page."""
        extra = HOMEPAGE_COMPLETED_LIMIT + 2
        for i in range(extra):
            c = _make_campionato(f"Done{i}", isolated_director_user.id)
            _add_completed_gara(db_session, c.id, 1, isolated_director_user.id)

        data = HomepageService.get_homepage_data()
        assert data is not None
        assert data["completed_total"] == extra
        assert data["completed_shown"] == HOMEPAGE_COMPLETED_LIMIT
        assert len(data["tournaments_data"]) == HOMEPAGE_COMPLETED_LIMIT

    def test_guest_homepage_renders_with_completed_only(
        self, app, db_session, isolated_director_user
    ):
        """Smoke: GET / works with only completed campionati and the
        section header shows 0 attivi, not 1.

        Regression 2026-05-14: header esplicito "0 attivi" (ngettext),
        non "Campionati (0)" da solo — l'utente segnalava l'ambiguità
        di vedere "Campionati (0)" con un campionato listato sotto.
        """
        campionato = _make_campionato("Past", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)

        response = _guest_render(app, "/")
        assert response.status_code == 200, response.data[:200]
        body = response.get_data(as_text=True)
        # New section header (count = 0 active, explicit "attivi")
        assert "0 attivi" in body
        # Campionato name still visible (in the "recent completed" tail)
        assert campionato.name in body

    def test_homepage_setup_with_future_date_visible_to_guest(
        self, app, db_session, isolated_director_user
    ):
        """ADR-030 rev 2026-05-14: SETUP con data futura/NULL è visibile
        al pubblico (homepage guest). SETUP con data passata è zombie e
        resta nascosta — solo il director/admin proprietario la vede
        nella sua dashboard.
        """
        # Gara SETUP con data futura
        future_gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Future Setup",
            date=date.today() + timedelta(days=10),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        future_gara.status = GaraStatus.SETUP.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        standalone_ids = [g.id for g in data["standalone_garas"]]
        assert future_gara.id in standalone_ids
        # Conta come "attiva" (non completata)
        assert data["standalone_active_count"] >= 1

    def test_homepage_setup_with_past_date_hidden_from_guest(
        self, app, db_session, isolated_director_user
    ):
        """SETUP con data passata = zombie/dimenticata: non deve apparire
        al guest in homepage."""
        zombie_gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Zombie Setup",
            date=date.today() + timedelta(days=5),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        # Forziamo SETUP + data passata
        zombie_gara.status = GaraStatus.SETUP.value
        zombie_gara.date = date.today() - timedelta(days=1)
        db_session.commit()

        data = HomepageService.get_homepage_data()
        # data può essere None se nessun campionato/gara visibile
        if data is not None:
            standalone_ids = [g.id for g in data["standalone_garas"]]
            assert zombie_gara.id not in standalone_ids

    def test_garas_list_setup_future_visible_setup_past_hidden(
        self, app, db_session, isolated_director_user
    ):
        """Stessa regola per /garas (route public_garas_list)."""
        future = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="GarasFuture",
            date=date.today() + timedelta(days=10),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        future.status = GaraStatus.SETUP.value

        zombie = GaraService.create_gara(
            campionato_id=None,
            number=2,
            name="GarasZombie",
            date=date.today() + timedelta(days=5),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        zombie.status = GaraStatus.SETUP.value
        zombie.date = date.today() - timedelta(days=1)
        db_session.commit()

        response = _guest_render(app, "/garas")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert future.name in body
        assert zombie.name not in body

    def test_homepage_standalone_active_count_excludes_completed(
        self, db_session, isolated_director_user
    ):
        """Regression 2026-05-14: `standalone_active_count` deve contare
        solo le gare standalone NON completate, non `len(standalone_garas)`
        che include la coda completati.
        """
        # Una gara standalone in stato INSCRIPTION (attiva)
        active_gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Active Standalone",
            date=date.today() + timedelta(days=1),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        active_gara.status = GaraStatus.INSCRIPTION.value

        # Una gara standalone completata
        completed_gara = GaraService.create_gara(
            campionato_id=None,
            number=2,
            name="Done Standalone",
            date=date.today() + timedelta(days=2),
            location="Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        completed_gara.status = GaraStatus.COMPLETED.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        # len(standalone_garas) sarebbe 2, ma active = 1
        assert data["standalone_active_count"] == 1
        assert len(data["standalone_garas"]) == 2


@pytest.mark.integration
class TestPublicCampionatosListFilters:
    """Tests for the new /campionatos filters and search."""

    def test_status_filter_completati_excludes_in_progress(
        self, app, db_session, isolated_director_user
    ):
        live = _make_campionato("LiveOne", isolated_director_user.id)
        live_gara = _add_completed_gara(
            db_session, live.id, 1, isolated_director_user.id
        )
        live_gara.status = GaraStatus.PLAYING.value
        db_session.commit()

        done = _make_campionato("DoneOne", isolated_director_user.id)
        _add_completed_gara(db_session, done.id, 1, isolated_director_user.id)

        response = _guest_render(app, "/campionatos", "status=completati")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert done.name in body
        assert live.name not in body

    def test_search_filters_by_name(
        self, app, db_session, isolated_director_user
    ):
        a = _make_campionato("AlphaSearch", isolated_director_user.id)
        b = _make_campionato("BetaSearch", isolated_director_user.id)

        response = _guest_render(app, "/campionatos", f"q={a.name[:5]}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert a.name in body
        assert b.name not in body

    def test_invalid_status_falls_back_to_all(
        self, app, db_session, isolated_director_user
    ):
        c = _make_campionato("AnyStatus", isolated_director_user.id)
        response = _guest_render(app, "/campionatos", "status=<script>")
        assert response.status_code == 200
        # All campionatos visible when filter is invalid
        body = response.get_data(as_text=True)
        assert c.name in body

    def test_terminated_campionato_visible_in_archive(
        self, app, db_session, isolated_director_user
    ):
        """Regression: un campionato terminato manualmente (`is_active=False`,
        `terminated_at IS NOT NULL`, `is_deleted=False`) deve restare
        visibile nell'archivio `/campionatos`. Prima del fix la query
        filtrava `is_active=True` e questi campionati sparivano sia
        dall'archivio sia dalla homepage.

        Nota: senza playoff config, un campionato manually-terminated
        ha status derivato COMPLETED (vedi `compute_campionato_status`),
        non TERMINATED. Per questo il filtro è `completati`.
        """
        from models.base import utc_now

        c = _make_campionato("ManualTerm", isolated_director_user.id)
        c.is_active = False
        c.terminated_at = utc_now()
        db_session.commit()

        assert c.is_active is False
        assert c.is_deleted is False
        assert c.terminated_at is not None

        # Verifica scope archivio
        response_all = _guest_render(app, "/campionatos", "")
        assert response_all.status_code == 200
        assert c.name in response_all.get_data(as_text=True)

        # Verifica filtro coerente
        response_filtered = _guest_render(app, "/campionatos", "status=completati")
        assert response_filtered.status_code == 200
        assert c.name in response_filtered.get_data(as_text=True)

    def test_soft_deleted_campionato_hidden_from_archive(
        self, app, db_session, isolated_director_user
    ):
        """Un campionato soft-deleted (`is_deleted=True`) NON appare
        nell'archivio pubblico (è amministrativo, solo admin può
        vederlo)."""
        c = _make_campionato("Trash", isolated_director_user.id)
        c.soft_delete("test")
        db_session.commit()

        assert c.is_deleted is True

        response = _guest_render(app, "/campionatos", "")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert c.name not in body
