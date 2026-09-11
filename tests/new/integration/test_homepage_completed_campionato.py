"""La home dell'ospite: chi finisce in quale sezione.

Regressione storica: un campionato con tutte le gare COMPLETED restava
`is_active=True` e finiva fra gli «attivi» col badge «Completato». La
partizione segue lo stato derivato (`compute_campionato_status`).

Dal 2026-09-10 la home dell'ospite è la sua dashboard: `DashboardService.
for_guest()` produce gli stessi elenchi di chi è entrato (`ElenchiGare`,
`ElenchiCampionati`) e le sezioni sono le stesse. Le concluse seguono la
regola 2 — l'ultima più l'ultimo mese — non un taglio fisso.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara
from models.base import utc_now
from models.campionato.services import TournamentService
from models.dashboard.dashboard_service import DashboardService
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
        active campionati. It belongs to the «conclusi» section instead."""
        campionato = _make_campionato("Old", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)
        _chiudi(db_session, campionato)

        # Sanity: derived status is COMPLETED, is_active is still True
        assert campionato.is_active is True
        assert campionato.get_status() == TournamentStatus.COMPLETED.value

        tessere = DashboardService.for_guest().campionati_tessere
        assert tessere is not None
        assert not any(c.id == campionato.id for c in tessere.attivi)
        assert tessere.conclusi_totali == 1
        assert any(c.id == campionato.id for c in tessere.conclusi)

    def test_in_progress_campionato_counts_as_active(
        self, db_session, isolated_director_user
    ):
        """A campionato with at least one PLAYING gara counts as active and
        its gara surfaces in «In diretta ora»."""
        campionato = _make_campionato("Live", isolated_director_user.id)
        gara = _add_completed_gara(
            db_session, campionato.id, 1, isolated_director_user.id
        )
        gara.status = GaraStatus.PLAYING.value
        db_session.commit()

        vm = DashboardService.for_guest()
        assert vm.campionati_tessere is not None and vm.gare is not None
        assert any(c.id == campionato.id for c in vm.campionati_tessere.attivi)
        assert vm.campionati_tessere.conclusi_totali == 0
        assert any(c.id == gara.id for c in vm.gare.in_diretta)

    def test_i_conclusi_dell_ultimo_mese_ci_sono_tutti_gli_altri_no(
        self, db_session, isolated_director_user
    ):
        """Regola 2 del 2026-09-10: l'ultimo più quelli dell'ultimo mese.

        Prima era un taglio fisso (quattro): ora è una finestra di tempo,
        misurata sulla data dell'ultima gara.
        """
        recenti = []
        for i in range(3):
            c = _make_campionato(f"Done{i}", isolated_director_user.id)
            _add_completed_gara(db_session, c.id, 1, isolated_director_user.id)
            recenti.append(_chiudi(db_session, c))
        vecchio = _make_campionato("Vecchio", isolated_director_user.id)
        gara = _add_completed_gara(db_session, vecchio.id, 1, isolated_director_user.id)
        gara.date = date.today() - timedelta(days=90)
        _chiudi(db_session, vecchio)
        db_session.commit()

        tessere = DashboardService.for_guest().campionati_tessere
        assert tessere is not None
        assert tessere.conclusi_totali == 4
        ids = {c.id for c in tessere.conclusi}
        assert ids == {c.id for c in recenti}
        assert vecchio.id not in ids

    def test_guest_homepage_renders_with_completed_only(
        self, app, db_session, isolated_director_user
    ):
        """Smoke: GET / works with only completed campionati, and the
        campionato stands under «Campionati conclusi», not among the active."""
        campionato = _make_campionato("Past", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)
        _chiudi(db_session, campionato)

        response = _guest_render(app, "/")
        assert response.status_code == 200, response.data[:200]
        body = response.get_data(as_text=True)
        assert "Campionati conclusi" in body
        assert campionato.name in body.split("Campionati conclusi", 1)[1]

    def test_homepage_setup_with_future_date_visible_to_guest(
        self, app, db_session, isolated_director_user
    ):
        """ADR-030 rev 2026-05-14: SETUP con data futura/NULL è visibile
        al pubblico (homepage guest). SETUP con data passata è zombie e
        resta nascosta — solo il director/admin proprietario la vede
        nella sua dashboard.
        """
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

        gare = DashboardService.for_guest().gare
        assert gare is not None
        # SETUP con data futura → sezione «In arrivo»
        assert future_gara.id in [c.id for c in gare.in_arrivo]

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
        zombie_gara.status = GaraStatus.SETUP.value
        zombie_gara.date = date.today() - timedelta(days=1)
        db_session.commit()

        gare = DashboardService.for_guest().gare
        assert gare is not None
        tutte = (
            gare.mie + gare.in_diretta + gare.aperte + gare.in_arrivo + gare.concluse
        )
        assert zombie_gara.id not in [c.id for c in tutte]

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
        """Una gara standalone con iscrizioni aperte va nelle «aperte»; una
        completata nelle «concluse». Non si mescolano."""
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

        gare = DashboardService.for_guest().gare
        assert gare is not None
        open_ids = [c.id for c in gare.aperte]
        concluse_ids = [c.id for c in gare.concluse]
        assert active_gara.id in open_ids
        assert completed_gara.id in concluse_ids
        assert active_gara.id not in concluse_ids
        assert completed_gara.id not in open_ids


@pytest.mark.integration
class TestHomepageActionableSections:
    """La home guest mostra subito le info azionabili: posti/scadenza nelle
    tessere delle iscrizioni e le partite ai tavoli in «In diretta ora»."""

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
        e scadenza iscrizioni direttamente sulla tessera."""
        from models.base import utc_now
        from models.competition.models import Inscription

        deadline = utc_now() + timedelta(days=3)
        gara = self._standalone_gara(
            isolated_director_user.id, name="Coppa Aperta", max_participants=4
        )
        gara.status = GaraStatus.INSCRIPTION.value
        gara.inscription_end = deadline
        for player in isolated_players[:2]:
            db_session.add(Inscription(user_id=player.id, gara_id=gara.id))
        db_session.commit()

        gare = DashboardService.for_guest().gare
        assert gare is not None
        card = next(c for c in gare.aperte if c.id == gara.id)
        assert not card.ha_un_fatto_mio

        body = _guest_render(app, "/").get_data(as_text=True)
        assert "Coppa Aperta" in body
        assert "Iscrizioni aperte" in body
        tessera = body.split("Coppa Aperta", 1)[1].split("</article>", 1)[0]
        assert "2/4" in tessera
        assert "2</span> liberi" in tessera or "2 liberi" in tessera
        assert "Chiudono il" in tessera
        # La stessa tessera di chi è entrato: l'ospite ha «Iscriviti» che
        # porta al login e torna qui, e sa che l'account è gratuito.
        assert "Iscriviti" in tessera
        assert "account gratuito" in tessera
        assert "btn-sm" not in tessera

    def test_live_section_shows_match_at_table(
        self, app, db_session, isolated_director_user, isolated_players
    ):
        """La sezione live mostra le partite ai tavoli con nomi e punteggio,
        sulla tessera scura, con «Segui la diretta» verso la pagina pubblica."""
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

        gare = DashboardService.for_guest().gare
        assert gare is not None
        card = next(c for c in gare.in_diretta if c.id == gara.id)
        assert [m.id for m in card.altre_partite] == [match.id]

        body = _guest_render(app, "/").get_data(as_text=True)
        assert "In diretta ora" in body
        tessera = body.split("Gara Live", 1)[0].rsplit("<article", 1)[1]
        tessera += body.split("Gara Live", 1)[1].split("</article>", 1)[0]
        assert "c7-card--accent" in tessera
        assert "Ai tavoli adesso" in tessera
        assert p1.username in tessera and p2.username in tessera
        assert "3–2" in tessera
        assert "Segui la diretta" in tessera
        assert "/gara/" in tessera and "/public" in tessera


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
