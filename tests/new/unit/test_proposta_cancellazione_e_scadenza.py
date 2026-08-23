"""Le proposte di sfida che restavano lì per sempre.

Due guasti distinti, e ripararne uno solo avrebbe lasciato il sintomo:

* `expires_at` veniva scritto a ogni proposta e non lo leggeva **nessuno** —
  `expire_old_proposals` esisteva, con la sua notifica «Proposta scaduta» già
  pronta, e la chiamavano solo i test. Una proposta pendente restava pendente
  per sempre;
* e una proposta non più pendente non aveva alcun comando accanto: annullare
  vale solo da `PENDING`, quindi accettate e scadute erano definitive.
"""

import pytest
from datetime import timedelta

from models.base import db, utc_now
from models.exceptions import ConflictError, PermissionDeniedError
from models.individual_match.models import (
    IndividualMatch,
    MatchProposal,
    ProposalStatus,
    ProposalType,
)
from models.individual_match.services import MatchProposalService
from models.status_enum import Discipline, MatchStatus


def _proposta(db_session, proposer, **campi):
    valori = dict(
        proposer_id=proposer.id,
        proposal_type=ProposalType.OPEN,
        status=ProposalStatus.PENDING,
        location="Sala di prova",
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(hours=12),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
    )
    valori.update(campi)
    proposal = MatchProposal(**valori)
    db_session.add(proposal)
    db_session.commit()
    return proposal


class TestCancellazioneVera:
    def test_la_riga_sparisce(self, app, db_session, isolated_players):
        proposer = isolated_players[0]
        proposal = _proposta(db_session, proposer)
        proposal_id = proposal.id

        MatchProposalService.delete_proposal(proposal_id, proposer.id)

        assert db.session.get(MatchProposal, proposal_id) is None

    def test_la_cancella_solo_chi_l_ha_fatta(self, app, db_session, isolated_players):
        proposer, estraneo = isolated_players[0], isolated_players[1]
        proposal = _proposta(db_session, proposer)

        with pytest.raises(PermissionDeniedError):
            MatchProposalService.delete_proposal(proposal.id, estraneo.id)

        assert db.session.get(MatchProposal, proposal.id) is not None

    def test_scaduta_o_annullata_si_cancella(self, app, db_session, isolated_players):
        """È il caso per cui serve: `cancel_proposal` vale solo da PENDING."""
        proposer = isolated_players[0]
        proposal = _proposta(db_session, proposer, status=ProposalStatus.EXPIRED)

        MatchProposalService.delete_proposal(proposal.id, proposer.id)

        assert db.session.get(MatchProposal, proposal.id) is None

    def test_con_una_partita_viva_appesa_si_rifiuta(
        self, app, db_session, isolated_players
    ):
        """La partita è il fatto; la proposta, il modo in cui ci si è arrivati."""
        proposer, avversario = isolated_players[0], isolated_players[1]
        proposal = _proposta(db_session, proposer, status=ProposalStatus.ACCEPTED)
        db_session.add(
            IndividualMatch(
                proposal_id=proposal.id,
                player1_id=proposer.id,
                player2_id=avversario.id,
                scheduled_at=utc_now(),
                status=MatchStatus.IN_PROGRESS,
                distance=5,
            )
        )
        db_session.commit()

        with pytest.raises(ConflictError, match="annulla prima"):
            MatchProposalService.delete_proposal(proposal.id, proposer.id)

    def test_se_la_partita_e_annullata_se_ne_vanno_insieme(
        self, app, db_session, isolated_players
    ):
        proposer, avversario = isolated_players[0], isolated_players[1]
        proposal = _proposta(db_session, proposer, status=ProposalStatus.ACCEPTED)
        match = IndividualMatch(
            proposal_id=proposal.id,
            player1_id=proposer.id,
            player2_id=avversario.id,
            scheduled_at=utc_now(),
            status=MatchStatus.CANCELLED,
            distance=5,
        )
        db_session.add(match)
        db_session.commit()

        MatchProposalService.delete_proposal(proposal.id, proposer.id)

        assert db.session.get(MatchProposal, proposal.id) is None
        # La partita resta, ma non punta più a una riga che non c'è: la FK non
        # ha `ondelete`, quindi il distacco lo fa il servizio.
        assert match.proposal_id is None


class TestScadenza:
    def test_una_proposta_oltre_il_termine_scade(
        self, app, db_session, isolated_players
    ):
        proposer = isolated_players[0]
        proposal = _proposta(
            db_session, proposer, expires_at=utc_now() - timedelta(minutes=1)
        )

        assert MatchProposalService.expire_proposals() >= 1
        assert proposal.status == ProposalStatus.EXPIRED

    def test_la_scadenza_e_agganciata_al_task_giornaliero(self):
        """Il guasto vero non era il codice: era che non lo chiamava nessuno.

        Un test sul solo servizio sarebbe passato anche prima, con le proposte
        che in produzione non scadevano comunque mai.
        """
        import importlib.util
        import pathlib

        percorso = (
            pathlib.Path(__file__).resolve().parents[3] / "scripts" / "daily_jobs.py"
        )
        spec = importlib.util.spec_from_file_location("daily_jobs", percorso)
        assert spec and spec.loader
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        assert "match_proposals" in modulo.JOBS
