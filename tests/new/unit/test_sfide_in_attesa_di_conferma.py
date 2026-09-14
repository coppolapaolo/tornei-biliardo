"""Sfide a due in attesa di conferma (richiesta del 2026-09-14).

Una sfida a due si chiude con la doppia conferma dei giocatori (ADR-051). Quando
si raggiunge la distanza chi vince firma d'ufficio, e la partita resta ad
aspettare la firma dell'altro. Tre regole nuove:

1. dopo **un giorno** dalla firma dell'avversario la partita non compare più
   nella dashboard — di nessuno dei due — ma resta nelle sfide;
2. chi deve confermare non può lanciare né accettare altre sfide individuali;
3. il blocco cade quando conferma o rifiuta l'ultima partita che lo aspetta.

L'avversario che aspetta non è mai bloccato per questo.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.dashboard.section_builders import DashboardSectionBuilder
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.match_models import IndividualMatch
from models.individual_match.pending_confirmation import (
    DASHBOARD_GRACE,
    PendingConfirmationError,
    PendingConfirmationService,
)
from models.individual_match.proposal_service import ProposalService
from models.individual_match.quick_match_service import QuickMatchService
from models.status_enum import Discipline, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _giocatore() -> User:
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"att_{uid}",
        email=f"att_{uid}@test.com",
        role=UserRole.PLAYER.value,
        # Le sfide individuali sono dietro uno sblocco della gamification.
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _sfida_firmata_da(vincitore: User, perdente: User, ore_fa: float, **kw):
    """Partita al 3 finita 3-1: il vincitore ha firmato ``ore_fa`` ore fa."""
    valori = dict(
        player1_id=vincitore.id,
        player2_id=perdente.id,
        location="Sala Test",
        scheduled_at=utc_now() - timedelta(hours=ore_fa + 1),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        player1_score=3,
        player2_score=1,
        player1_confirmed=True,
        player1_confirmed_at=utc_now() - timedelta(hours=ore_fa),
    )
    valori.update(kw)
    match = IndividualMatch(**valori)
    db.session.add(match)
    db.session.commit()
    return match


@pytest.fixture
def coppia(app, db_session):
    with app.app_context():
        yield _giocatore(), _giocatore()


class TestChiDeveConfermare:
    def test_aspetta_la_firma_di_chi_non_ha_ancora_confermato(self, coppia):
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        assert match.awaiting_confirmation_from_id == perdente.id
        assert match.awaiting_confirmation_since == match.player1_confirmed_at

    def test_nessuno_ha_firmato_nessuno_e_in_attesa(self, coppia):
        """Senza la prima firma non c'è nessuno che aspetta: vale soprattutto
        per il formato libero, dove la partita è «pronta» dal primo triangolo
        mentre i due stanno ancora giocando."""
        a, b = coppia
        match = _sfida_firmata_da(
            a,
            b,
            ore_fa=2,
            distance=None,
            player1_confirmed=False,
            player1_confirmed_at=None,
        )

        assert match.awaiting_confirmation_from_id is None
        assert PendingConfirmationService.pending_for(a.id) == []
        assert PendingConfirmationService.pending_for(b.id) == []

    def test_partita_non_arrivata_alla_distanza_non_aspetta(self, coppia):
        a, b = coppia
        match = _sfida_firmata_da(a, b, ore_fa=2, player1_score=2)

        assert match.awaiting_confirmation_from_id is None

    def test_partita_conclusa_non_aspetta(self, coppia):
        a, b = coppia
        match = _sfida_firmata_da(
            a,
            b,
            ore_fa=2,
            status=MatchStatus.CONFIRMED_BY_BOTH,
            player2_confirmed=True,
            player2_confirmed_at=utc_now(),
        )

        assert match.awaiting_confirmation_from_id is None

    def test_elenco_delle_pendenti_solo_per_chi_deve_firmare(self, coppia):
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        assert [m.id for m in PendingConfirmationService.pending_for(perdente.id)] == [
            match.id
        ]
        assert PendingConfirmationService.pending_for(vincitore.id) == []

    def test_anche_da_secondo_giocatore(self, coppia):
        """La firma può mancare a player1: il vincitore è player2."""
        perdente, vincitore = coppia
        match = _sfida_firmata_da(
            perdente,
            vincitore,
            ore_fa=2,
            player1_score=1,
            player2_score=3,
            player1_confirmed=False,
            player1_confirmed_at=None,
            player2_confirmed=True,
            player2_confirmed_at=utc_now() - timedelta(hours=2),
        )

        assert match.awaiting_confirmation_from_id == perdente.id
        assert [m.id for m in PendingConfirmationService.pending_for(perdente.id)] == [
            match.id
        ]


class TestDashboard:
    def _in_dashboard(self, user_id: int) -> list[int]:
        sezioni = DashboardSectionBuilder.build_individual_match_sections(user_id)
        return [m.id for m in sezioni["sfide_in_corso"]]

    def test_il_giorno_vale_ventiquattro_ore(self):
        assert DASHBOARD_GRACE == timedelta(hours=24)

    def test_prima_di_un_giorno_si_vede_ancora(self, coppia):
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=23)

        assert match.id in self._in_dashboard(perdente.id)
        assert match.id in self._in_dashboard(vincitore.id)

    def test_dopo_un_giorno_sparisce_per_chi_deve_confermare(self, coppia):
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=25)

        assert match.id not in self._in_dashboard(perdente.id)

    def test_dopo_un_giorno_sparisce_anche_per_chi_aspetta(self, coppia):
        """Per chi ha già firmato non c'è niente da fare: la partita non è
        un'attività in corso nemmeno per lui, e resta nelle sfide."""
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=25)

        assert match.id not in self._in_dashboard(vincitore.id)

    def test_resta_fra_le_sfide(self, coppia):
        from models.individual_match.statistics_service import (
            IndividualMatchStatisticsService,
        )

        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=25)

        for user in (vincitore, perdente):
            ids = [
                m.id for m in IndividualMatchStatisticsService.get_user_matches(user.id)
            ]
            assert match.id in ids

    def test_una_partita_in_corso_da_giorni_senza_firme_resta(self, coppia):
        """Il giorno si conta dalla firma, non dall'inizio: una partita ancora
        da finire non è «in attesa di conferma»."""
        a, b = coppia
        match = _sfida_firmata_da(
            a,
            b,
            ore_fa=72,
            player1_score=1,
            player1_confirmed=False,
            player1_confirmed_at=None,
        )

        assert match.id in self._in_dashboard(a.id)


class TestBlocco:
    def test_chi_deve_confermare_non_avvia_una_sfida_rapida(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        with pytest.raises(PendingConfirmationError) as exc:
            QuickMatchService.start(perdente.id, terzo.id)

        assert exc.value.match_ids == [match.id]
        assert (
            IndividualMatch.query.filter_by(
                player1_id=perdente.id, player2_id=terzo.id
            ).count()
            == 0
        )

    def test_e_un_conflitto(self):
        from models.exceptions import ConflictError, http_status_for_exception

        exc = PendingConfirmationError([1])
        assert isinstance(exc, ConflictError)
        assert http_status_for_exception(exc) == 409

    def test_chi_deve_confermare_non_propone_una_sfida(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        with pytest.raises(PendingConfirmationError):
            ProposalService.create_direct_proposal(
                proposer_id=perdente.id,
                invited_user_ids=[terzo.id],
                location="Sala Test",
                scheduled_at=utc_now() + timedelta(days=2),
            )
        with pytest.raises(PendingConfirmationError):
            ProposalService.create_open_proposal(
                proposer_id=perdente.id,
                location="Sala Test",
                scheduled_at=utc_now() + timedelta(days=2),
            )

    def test_chi_deve_confermare_non_accetta_una_sfida(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        _sfida_firmata_da(vincitore, perdente, ore_fa=2)
        proposta = ProposalService.create_direct_proposal(
            proposer_id=terzo.id,
            invited_user_ids=[perdente.id],
            location="Sala Test",
            scheduled_at=utc_now() + timedelta(days=2),
        )

        with pytest.raises(PendingConfirmationError):
            ProposalService.accept_proposal(perdente.id, proposta.id)

        assert db.session.get(type(proposta), proposta.id).individual_match is None

    def test_il_blocco_non_aspetta_un_giorno(self, coppia):
        """Il giorno riguarda solo la dashboard: chi deve firmare è bloccato
        da subito."""
        vincitore, perdente = coppia
        terzo = _giocatore()
        _sfida_firmata_da(vincitore, perdente, ore_fa=0.1)

        with pytest.raises(PendingConfirmationError):
            QuickMatchService.start(perdente.id, terzo.id)

    def test_chi_aspetta_non_e_bloccato(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        _sfida_firmata_da(vincitore, perdente, ore_fa=30)

        nuova = QuickMatchService.start(vincitore.id, terzo.id)

        assert nuova.id is not None

    def test_confermata_l_ultima_il_blocco_cade(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        prima = _sfida_firmata_da(vincitore, perdente, ore_fa=30)
        seconda = _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        MatchLifecycleService.confirm_match_result(prima.id, perdente.id)
        with pytest.raises(PendingConfirmationError) as exc:
            QuickMatchService.start(perdente.id, terzo.id)
        assert exc.value.match_ids == [seconda.id]

        MatchLifecycleService.confirm_match_result(seconda.id, perdente.id)
        nuova = QuickMatchService.start(perdente.id, terzo.id)

        assert nuova.id is not None

    def test_rifiutata_il_blocco_cade(self, coppia):
        vincitore, perdente = coppia
        terzo = _giocatore()
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=30)

        MatchLifecycleService.reject_match_result(match.id, perdente.id)

        assert PendingConfirmationService.pending_for(perdente.id) == []
        assert QuickMatchService.start(perdente.id, terzo.id).id is not None

    def test_la_sfida_rapida_contro_lo_stesso_avversario_riporta_a_quella(self, coppia):
        """L'avvio rapido contro chi hai già davanti riapre la partita in corso
        (ADR-051): è proprio quella da chiudere, non una nuova sfida."""
        vincitore, perdente = coppia
        match = _sfida_firmata_da(vincitore, perdente, ore_fa=2)

        assert QuickMatchService.start(perdente.id, vincitore.id).id == match.id
