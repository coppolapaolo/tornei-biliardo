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
from models.base import utc_now
from models.campionato.homepage_service import (
    HomepageService,
    HOMEPAGE_ARCHIVE_LIMIT,
)
from models.campionato.services import TournamentService
from models.competition.services import GaraService
from models.status_enum import GaraStatus, MatchStatus, TournamentStatus


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


def _make_campionato(
    name_prefix: str, director_id: int, planned_gare_count: int = 1
) -> Campionato:
    """Helper to build a campionato with a unique name.

    Pianifica UNA sola gara: col default del modello (10) un campionato le
    cui gare esistenti sono tutte COMPLETED resta IN_PROGRESS, perché ne
    mancano ancora da creare (issue #60). Questi test verificano la
    partizione per stato derivato, non la pianificazione.
    """
    suffix = uuid.uuid4().hex[:6]
    return TournamentService().create_campionato_with_director(
        name=f"{name_prefix}_{suffix}",
        creator_user_id=director_id,
        campionato_type="Amalfi",
        is_active=True,
        planned_gare_count=planned_gare_count,
    )


def _chiudi(db_session, campionato):
    """Chiude il campionato come fa il direttore col pulsante «Termina».

    Dalla #242 completare le gare non basta: senza `terminated_at` lo stato è
    AWAITING_CLOSURE, che di proposito **non** è terminale — il campionato resta
    fra gli attivi e fuori dall'archivio. Questi test parlano dell'archivio e
    del filtro "completati", quindi devono chiuderlo davvero.
    """
    campionato.terminated_at = utc_now()
    db_session.flush()
    return campionato


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
        discipline="9_ball",
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
        """A campionato with all gare COMPLETED must not appear among the
        active campionati. It belongs to the archive section instead."""
        campionato = _make_campionato("Old", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)
        _chiudi(db_session, campionato)

        # Sanity: derived status is COMPLETED, is_active is still True
        assert campionato.is_active is True
        assert campionato.get_status() == TournamentStatus.COMPLETED.value

        data = HomepageService.get_homepage_data()
        assert data is not None
        # Not active...
        assert data["active_campionati_count"] == 0
        assert not any(
            d["campionato"].id == campionato.id for d in data["active_campionati"]
        )
        # ...but present in the archive tail.
        assert data["archive_campionati_total"] == 1
        assert any(c.id == campionato.id for c in data["archive_campionati"])

    def test_in_progress_campionato_counts_as_active(
        self, db_session, isolated_director_user
    ):
        """A campionato with at least one PLAYING gara counts as active and
        its gara surfaces in the live section."""
        campionato = _make_campionato("Live", isolated_director_user.id)
        gara = _add_completed_gara(
            db_session, campionato.id, 1, isolated_director_user.id
        )
        gara.status = GaraStatus.PLAYING.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        assert data["active_campionati_count"] == 1
        assert data["archive_campionati_total"] == 0
        # The PLAYING gara is shown as live.
        assert any(c["gara"].id == gara.id for c in data["live_garas"])

    def test_completed_tail_caps_at_archive_limit(
        self, db_session, isolated_director_user
    ):
        """When there are more than HOMEPAGE_ARCHIVE_LIMIT completed
        campionati, only the most recent are shown; the rest live behind
        the /campionatos page."""
        extra = HOMEPAGE_ARCHIVE_LIMIT + 2
        for i in range(extra):
            c = _make_campionato(f"Done{i}", isolated_director_user.id)
            _add_completed_gara(db_session, c.id, 1, isolated_director_user.id)
            _chiudi(db_session, c)

        data = HomepageService.get_homepage_data()
        assert data is not None
        assert data["archive_campionati_total"] == extra
        assert len(data["archive_campionati"]) == HOMEPAGE_ARCHIVE_LIMIT

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
        # Completed campionato shown under the archive section, not as active.
        assert "Archivio" in body
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
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        future_gara.status = GaraStatus.SETUP.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        # SETUP con data futura → sezione "In arrivo"
        upcoming_ids = [g.id for g in data["upcoming_garas"]]
        assert future_gara.id in upcoming_ids

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
            discipline="9_ball",
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
            all_gara_ids = (
                [g.id for g in data["upcoming_garas"]]
                + [c["gara"].id for c in data["live_garas"]]
                + [c["gara"].id for c in data["open_garas"]]
                + [g.id for g in data["archive_garas"]]
            )
            assert zombie_gara.id not in all_gara_ids

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
            discipline="9_ball",
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
            discipline="9_ball",
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

    def test_homepage_open_and_completed_garas_partitioned(
        self, db_session, isolated_director_user
    ):
        """Una gara standalone con iscrizioni aperte va nella sezione
        "Iscrizioni aperte"; una completata va in archivio. Non si mescolano.
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
            discipline="9_ball",
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
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        completed_gara.status = GaraStatus.COMPLETED.value
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        open_ids = [c["gara"].id for c in data["open_garas"]]
        archive_ids = [g.id for g in data["archive_garas"]]
        assert active_gara.id in open_ids
        assert completed_gara.id in archive_ids
        # Niente sovrapposizione tra le due sezioni
        assert active_gara.id not in archive_ids
        assert completed_gara.id not in open_ids


@pytest.mark.integration
class TestHomepageActionableSections:
    """La home guest mostra subito le info azionabili: posti/scadenza nelle
    card iscrizioni e i match ai tavoli nella sezione "In diretta ora"."""

    def _standalone_gara(self, director_id, **overrides):
        params = dict(
            campionato_id=None,
            number=1,
            name="Open Gara",
            date=date.today() + timedelta(days=2),
            location="Sala Test",
            description="",
            rounds_count=1,
            min_participants=2,
            max_participants=4,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_id,
            matchmaking_strategy="amalfi",
        )
        params.update(overrides)
        return GaraService.create_gara(**params)

    def test_open_card_shows_inscriptions_count_and_deadline(
        self, app, db_session, isolated_director_user, isolated_players
    ):
        """Senza entrare nel dettaglio, il guest vede iscritti, posti rimasti
        e scadenza iscrizioni direttamente sulla card."""
        from models.base import utc_now
        from models.competition.models import Inscription

        deadline = utc_now() + timedelta(days=3)
        gara = self._standalone_gara(
            isolated_director_user.id, name="Coppa Aperta", max_participants=4
        )
        gara.status = GaraStatus.INSCRIPTION.value
        gara.inscription_end = deadline
        # Iscrivo 2 giocatori → 2/4, 2 posti rimasti
        for player in isolated_players[:2]:
            db_session.add(Inscription(user_id=player.id, gara_id=gara.id))
        db_session.commit()

        # Dati del service
        data = HomepageService.get_homepage_data()
        assert data is not None
        card = next(c for c in data["open_garas"] if c["gara"].id == gara.id)
        assert card["active_count"] == 2
        assert card["max_participants"] == 4
        assert card["spots_remaining"] == 2
        assert card["inscription_end"] is not None

        # Rendering: le info compaiono in pagina
        body = _guest_render(app, "/").get_data(as_text=True)
        assert "Coppa Aperta" in body
        assert "Iscrizioni aperte" in body
        assert "2/4" in body
        # "Chiudono il <data>" dopo il redesign 7c: stessa informazione,
        # detta come la direbbe una persona.
        assert "Chiudono il" in body

    def test_live_section_shows_match_at_table(
        self, app, db_session, isolated_director_user, isolated_players
    ):
        """La sezione live mostra i match attualmente ai tavoli con nomi e
        punteggio."""
        from models.match.models import Match

        gara = self._standalone_gara(isolated_director_user.id, name="Gara Live")
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        p1, p2 = isolated_players[0], isolated_players[1]
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            status=MatchStatus.PLAYING.value,
            table_assignment="A",
            player1_score=3,
            player2_score=2,
        )
        db_session.add(match)
        db_session.commit()

        data = HomepageService.get_homepage_data()
        assert data is not None
        card = next(c for c in data["live_garas"] if c["gara"].id == gara.id)
        assert len(card["live_matches"]) == 1
        lm = card["live_matches"][0]
        assert lm["table"] == "A"
        assert lm["player1"] == p1.username
        assert lm["player1_score"] == 3

        body = _guest_render(app, "/").get_data(as_text=True)
        assert "In diretta ora" in body
        assert p1.username in body
        assert p2.username in body


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
        _chiudi(db_session, done)

        response = _guest_render(app, "/campionatos", "status=completati")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert done.name in body
        assert live.name not in body

    def test_search_filters_by_name(self, app, db_session, isolated_director_user):
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
