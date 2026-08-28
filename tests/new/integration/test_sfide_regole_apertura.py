"""Le sfide individuali possono scegliere le regole di apertura (issue #249).

L'ADR-056 ha insegnato al modello delle sfide le due regole — `break_rule` con
quattro valori e `start_rule` come **radice**, perché una sfida non ha una gara
sopra da cui ereditare — ma le tre schermate che le impostano erano rimaste
indietro: tre opzioni scritte a mano con etichette diverse da quelle dell'enum,
e nessun modo di accendere l'acchito.

Qui si difende il giro completo: dal modulo al database, e ritorno.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.individual_match.match_models import IndividualMatch
from models.individual_match.quick_match_service import QuickMatchService
from models.match.break_rules import BreakRule, StartRule
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


def _giocatori(db_session, quanti=2):
    from models.user.models import User

    batch = str(uuid.uuid4())[:8]
    utenti = []
    for i in range(quanti):
        u = User(
            username=f"sf{i}_{batch}",
            email=f"sf{i}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("test123")
        # Le sfide individuali sono dietro uno sblocco della gamification:
        # senza, `QuickMatchService.start` rifiuta l'avversario e il test
        # fallirebbe per una ragione che non c'entra con le regole di apertura.
        u.gamification_override = True
        utenti.append(u)
    db_session.add_all(utenti)
    db_session.commit()
    return utenti


def _login(client, utente):
    return client.post(
        "/auth/login",
        data={"username": utente.username, "password": "test123"},
        follow_redirects=True,
    )


class TestLeTendineOffronoTuttiIValori:
    """Le opzioni le detta l'enum: se le riscrivesse il template, il giorno in
    cui l'enum cresce la schermata resterebbe indietro in silenzio."""

    @pytest.mark.parametrize("percorso", ["/match/quick", "/match/proposals/create"])
    def test_tutte_e_quattro_le_regole_di_apertura(self, app, db_session, percorso):
        gioc = _giocatori(db_session)
        client = app.test_client()
        _login(client, gioc[0])

        pagina = client.get(percorso).get_data(as_text=True)

        for regola in BreakRule:
            assert f'value="{regola.value}"' in pagina, regola.value
        # «a turno ogni due» è quella che prima non c'era proprio.
        assert BreakRule.ALTERNATE_TWO.value in pagina

    @pytest.mark.parametrize("percorso", ["/match/quick", "/match/proposals/create"])
    def test_si_puo_scegliere_l_acchito(self, app, db_session, percorso):
        gioc = _giocatori(db_session)
        client = app.test_client()
        _login(client, gioc[0])

        pagina = client.get(percorso).get_data(as_text=True)

        assert 'name="start_rule"' in pagina
        for regola in StartRule:
            assert f'value="{regola.value}"' in pagina, regola.value


class TestDalModuloAlDatabase:
    def test_l_avvio_rapido_porta_le_due_regole(self, db_session):
        gioc = _giocatori(db_session)

        match = QuickMatchService.start(
            user_id=gioc[0].id,
            opponent_id=gioc[1].id,
            config={
                "start_rule": StartRule.LAG.value,
                "break_rule": BreakRule.ALTERNATE_TWO.value,
            },
        )
        db_session.commit()

        assert match.effective_start_rule is StartRule.LAG
        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO
        # E il tabellone farà le due domande, perché l'acchito non è registrato.
        assert match.needs_lag is True

    def test_un_valore_ignoto_ricade_sul_default_invece_di_finire_in_colonna(
        self, db_session
    ):
        """Un modulo vecchio o una chiamata a mano non devono poter scrivere
        una regola che poi nessuno sa interpretare."""
        gioc = _giocatori(db_session)

        match = QuickMatchService.start(
            user_id=gioc[0].id,
            opponent_id=gioc[1].id,
            config={"start_rule": "boh", "break_rule": "non_esiste"},
        )
        db_session.commit()

        assert match.start_rule == StartRule.FIRST_PLAYER.value
        assert match.break_rule == BreakRule.ALTERNATE.value

    def test_senza_scelta_valgono_i_default_storici(self, db_session):
        gioc = _giocatori(db_session)

        match = QuickMatchService.start(user_id=gioc[0].id, opponent_id=gioc[1].id)
        db_session.commit()

        assert match.effective_start_rule is StartRule.FIRST_PLAYER
        assert match.effective_break_rule is BreakRule.ALTERNATE
        assert match.needs_lag is False

    def test_la_sfida_successiva_ripropone_le_stesse_regole(self, db_session):
        """`get_defaults` legge l'ultima sfida: se non leggesse `start_rule`,
        chi gioca sempre con l'acchito dovrebbe riselezionarlo ogni volta."""
        gioc = _giocatori(db_session)

        QuickMatchService.start(
            user_id=gioc[0].id,
            opponent_id=gioc[1].id,
            config={
                "start_rule": StartRule.LAG.value,
                "break_rule": BreakRule.LOSER_BREAKS.value,
            },
        )
        db_session.commit()

        defaults = QuickMatchService.get_defaults(gioc[0].id)
        assert defaults["start_rule"] == StartRule.LAG.value
        assert defaults["break_rule"] == BreakRule.LOSER_BREAKS.value


class TestLaProposta:
    """Le regole viaggiano con la proposta: chi accetta deve sapere a cosa sta
    dicendo di sì."""

    def test_la_proposta_le_copia_sul_match_quando_viene_accettata(self, db_session):
        from models.individual_match.models import MatchProposal, ProposalType

        gioc = _giocatori(db_session)
        proposta = MatchProposal(
            proposer_id=gioc[0].id,
            proposal_type=ProposalType.OPEN,
            location="Sala prova",
            scheduled_at=utc_now() + timedelta(days=1),
            expires_at=utc_now() + timedelta(hours=2),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            break_rule=BreakRule.WINNER_BREAKS.value,
            start_rule=StartRule.LAG.value,
        )
        db_session.add(proposta)
        db_session.commit()

        match = proposta.accept(gioc[1].id)
        db_session.commit()

        assert match.break_rule == BreakRule.WINNER_BREAKS.value
        assert match.start_rule == StartRule.LAG.value

    def test_una_proposta_senza_regola_di_inizio_non_rompe_l_accettazione(
        self, db_session
    ):
        """Le proposte scritte prima della migration hanno `start_rule` NULL."""
        from models.individual_match.models import MatchProposal, ProposalType

        gioc = _giocatori(db_session)
        proposta = MatchProposal(
            proposer_id=gioc[0].id,
            proposal_type=ProposalType.OPEN,
            location="Sala prova",
            scheduled_at=utc_now() + timedelta(days=1),
            expires_at=utc_now() + timedelta(hours=2),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
        )
        proposta.start_rule = None
        db_session.add(proposta)
        db_session.commit()

        match = proposta.accept(gioc[1].id)
        db_session.commit()

        assert match.start_rule == StartRule.FIRST_PLAYER.value


class TestLaCorrezione:
    def test_si_possono_correggere_su_una_sfida_gia_aperta(self, db_session):
        gioc = _giocatori(db_session)
        match = QuickMatchService.start(user_id=gioc[0].id, opponent_id=gioc[1].id)
        db_session.commit()
        match_id = match.id

        base = QuickMatchService.settings_of(match)
        assert base["start_rule"] == StartRule.FIRST_PLAYER.value

        risolte = QuickMatchService.resolve_settings(
            base, {"start_rule": StartRule.LAG.value}
        )
        assert risolte["start_rule"] == StartRule.LAG.value
        # E il resto della configurazione non si muove.
        assert risolte["break_rule"] == base["break_rule"]
        assert risolte["discipline"] == base["discipline"]

        aggiornato = db.session.get(IndividualMatch, match_id)
        assert aggiornato.status in (
            MatchStatus.SCHEDULED,
            MatchStatus.IN_PROGRESS,
        )
