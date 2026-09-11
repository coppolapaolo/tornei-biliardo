"""Regression: campionati COMPLETED non sotto un header "attivi" nelle
dashboard player/director (allineamento con ADR-030 per la homepage guest).

Pattern atteso:
- `vm.campionati_active_items` contiene SOLO campionati con status derivato
  non terminale (SETUP, REGISTRATION_OPEN, IN_PROGRESS).
- `vm.campionati_completed_shown_items` ne contiene al più
  `DASHBOARD_COMPLETED_LIMIT` (= 2 al momento).
- `vm.campionati_completed_total` riporta il totale dei completati nello
  scope dell'utente — usato dal template per decidere se mostrare
  "Vedi tutti" verso /campionatos.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara
from models.base import utc_now
from models.campionato.services import TournamentService
from models.competition.services import GaraService
from models.dashboard.dashboard_service import (
    DashboardService,
    DASHBOARD_COMPLETED_LIMIT,
)
from models.status_enum import GaraStatus, TournamentStatus


def _make_standalone_gara(director_id: int, number: int, status: str) -> Gara:
    """Crea una gara standalone (no campionato) e forza lo status."""
    gara = GaraService.create_gara(
        campionato_id=None,
        number=number,
        name=f"Standalone {number}",
        date=date.today() + timedelta(days=number),
        location="Test",
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
    gara.status = status
    return gara


def _make_campionato(
    name_prefix: str, director_id: int, planned_gare_count: int = 1
) -> Campionato:
    """Campionato di test con UNA gara pianificata.

    Il default del modello è 10: con quello, un campionato le cui gare
    esistenti sono tutte COMPLETED resta IN_PROGRESS perché ne mancano
    ancora 9 da creare (issue #60). Qui interessa la partizione per stato
    derivato, non la pianificazione, quindi pianifichiamo esattamente le
    gare che i test creano.
    """
    suffix = uuid.uuid4().hex[:6]
    return TournamentService().create_campionato_with_director(
        name=f"{name_prefix}_{suffix}",
        creator_user_id=director_id,
        campionato_type="Amalfi",
        is_active=True,
        planned_gare_count=planned_gare_count,
    )


def _chiudi(db_session, campionato: Campionato) -> Campionato:
    """Chiude il campionato come fa il direttore col pulsante «Termina».

    Dalla #242 completare le gare non basta a renderlo "concluso": senza
    `terminated_at` lo stato è AWAITING_CLOSURE — la classifica generale non è
    consolidata — e resta di proposito fra gli **attivi**, che è dove il
    direttore deve ritrovarlo. Questi test parlano del secchiello dei conclusi,
    quindi devono chiuderlo davvero.
    """
    campionato.terminated_at = utc_now()
    db_session.flush()
    return campionato


def _add_completed_gara(
    db_session, campionato_id: int, number: int, director_id: int
) -> Gara:
    """Crea una gara, poi forza COMPLETED. Necessario perché
    GaraService rifiuta date passate alla creazione, ma non c'è
    validazione successiva sullo status."""
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
class TestPlayerDashboardCampionatiPartition:
    """Player dashboard: stesso pattern guest (cap 2 completati + Vedi tutti)."""

    def test_completed_campionato_not_in_active_items(
        self, db_session, isolated_director_user, isolated_players
    ):
        campionato = _make_campionato("Done", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)
        _chiudi(db_session, campionato)

        # Sanity
        assert campionato.get_status() == TournamentStatus.COMPLETED.value
        assert campionato.is_active is True

        vm = DashboardService.for_player(isolated_players[0].id)

        active_ids = [it.id for it in (vm.campionati_active_items or [])]
        completed_ids = [it.id for it in (vm.campionati_completed_shown_items or [])]
        assert campionato.id not in active_ids
        assert campionato.id in completed_ids
        assert vm.campionati_completed_total == 1

    def test_setup_campionato_counts_as_active(
        self, db_session, isolated_director_user, isolated_players
    ):
        """SETUP (in preparazione, no gare) deve risultare ATTIVO."""
        campionato = _make_campionato("Prep", isolated_director_user.id)
        # Nessuna gara → status SETUP
        assert campionato.get_status() == TournamentStatus.SETUP.value

        vm = DashboardService.for_player(isolated_players[0].id)

        active_ids = [it.id for it in (vm.campionati_active_items or [])]
        assert campionato.id in active_ids

    def test_completed_tail_caps_at_dashboard_limit(
        self, db_session, isolated_director_user, isolated_players
    ):
        extra = DASHBOARD_COMPLETED_LIMIT + 2
        for i in range(extra):
            c = _make_campionato(f"Past{i}", isolated_director_user.id)
            _add_completed_gara(db_session, c.id, 1, isolated_director_user.id)
            _chiudi(db_session, c)

        vm = DashboardService.for_player(isolated_players[0].id)

        assert vm.campionati_completed_total == extra
        assert (
            len(vm.campionati_completed_shown_items or []) == DASHBOARD_COMPLETED_LIMIT
        )


@pytest.mark.integration
class TestDirectorDashboardCampionatiPartition:
    """Director dashboard: stesso pattern, includendo SETUP fra gli attivi
    (anche campionati appena creati dal director)."""

    def test_completed_campionato_not_in_active_items(
        self, db_session, isolated_director_user
    ):
        campionato = _make_campionato("Old", isolated_director_user.id)
        _add_completed_gara(db_session, campionato.id, 1, isolated_director_user.id)
        _chiudi(db_session, campionato)

        vm = DashboardService.for_director(isolated_director_user.id)

        active_ids = [it.id for it in (vm.campionati_active_items or [])]
        completed_ids = [it.id for it in (vm.campionati_completed_shown_items or [])]
        assert campionato.id not in active_ids
        assert campionato.id in completed_ids

    def test_setup_campionato_director_created_is_active(
        self, db_session, isolated_director_user
    ):
        """Un campionato in preparazione creato dal director compare fra
        gli attivi (richiesta esplicita dell'utente)."""
        campionato = _make_campionato("Prep", isolated_director_user.id)
        assert campionato.get_status() == TournamentStatus.SETUP.value

        vm = DashboardService.for_director(isolated_director_user.id)

        active_ids = [it.id for it in (vm.campionati_active_items or [])]
        assert campionato.id in active_ids


@pytest.mark.integration
class TestDashboardStandaloneCompletedTail:
    """Regression 2026-05-14: la sezione Gare in dashboard player/director
    deve mostrare una coda recente di standalone COMPLETED (cap = 2) +
    pulsante "Vedi tutte" → /garas. Le gare-di-campionato completate
    restano accessibili tramite il campionato, non sono duplicate qui.
    """

    def test_active_standalone_not_in_completed_tail(
        self, db_session, isolated_director_user, isolated_players
    ):
        active = _make_standalone_gara(
            isolated_director_user.id, 1, GaraStatus.INSCRIPTION.value
        )
        db_session.commit()

        vm = DashboardService.for_player(isolated_players[0].id)
        # La coda delle standalone concluse non esiste più: le concluse sono
        # un elenco di `gara_cards`, di tutti, con la finestra di un mese.
        ids = [c.id for c in (vm.gare.concluse if vm.gare else [])]
        assert active.id not in ids
        assert (vm.gare.concluse_totali if vm.gare else 0) == 0


@pytest.mark.integration
class TestDashboardSetupVisibility:
    """ADR-030 rev 2026-05-14: gare SETUP con data passata = zombie,
    visibili SOLO al director/admin proprietario. SETUP con data
    futura/NULL restano visibili a tutti.
    """

    def test_player_does_not_see_zombie_setup(
        self, db_session, isolated_director_user, isolated_players
    ):
        zombie = _make_standalone_gara(
            isolated_director_user.id, 1, GaraStatus.SETUP.value
        )
        zombie.date = date.today() - timedelta(days=1)
        db_session.commit()

        vm = DashboardService.for_player(isolated_players[0].id)
        gara_ids = [it.id for it in (vm.unified_items or []) if it.type == "gara"]
        assert zombie.id not in gara_ids

    def test_player_sees_future_setup(
        self, db_session, isolated_director_user, isolated_players
    ):
        future = _make_standalone_gara(
            isolated_director_user.id, 1, GaraStatus.SETUP.value
        )
        # Date already in the future (number=1 → today+1 day)
        db_session.commit()

        vm = DashboardService.for_player(isolated_players[0].id)
        gara_ids = [it.id for it in (vm.unified_items or []) if it.type == "gara"]
        assert future.id in gara_ids

    def test_director_owner_sees_zombie_setup(self, db_session, isolated_director_user):
        """Il director proprietario vede la sua zombie SETUP per poterla
        gestire (cancellarla o aggiornare la data)."""
        zombie = _make_standalone_gara(
            isolated_director_user.id, 1, GaraStatus.SETUP.value
        )
        zombie.date = date.today() - timedelta(days=1)
        db_session.commit()

        vm = DashboardService.for_director(isolated_director_user.id)
        gara_ids = [it.id for it in (vm.unified_items or []) if it.type == "gara"]
        assert zombie.id in gara_ids

    def test_director_non_owner_does_not_see_zombie_setup(
        self, db_session, isolated_director_user, isolated_players
    ):
        """Un director non-proprietario è equivalente a un player per
        visibilità — non vede la zombie SETUP altrui."""
        zombie = _make_standalone_gara(
            isolated_director_user.id, 1, GaraStatus.SETUP.value
        )
        zombie.date = date.today() - timedelta(days=1)
        db_session.commit()

        # Promuovi il player a director (non proprietario della gara)
        other = isolated_players[0]
        other.role = "director"
        db_session.commit()

        vm = DashboardService.for_director(other.id)
        gara_ids = [it.id for it in (vm.unified_items or []) if it.type == "gara"]
        assert zombie.id not in gara_ids
