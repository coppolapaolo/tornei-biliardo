"""
Module: models/individual_match/services.py
Purpose: Facade services for backward compatibility
Sprint 13: Refactored to delegate to specialized services

This module now acts as a FACADE, delegating to:
- ProposalService: Match proposal creation and management
- MatchLifecycleService: Match state management
- IndividualRackService: Rack operations
- IndividualMatchStatisticsService: Statistics and queries
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, date

from ..base import db
from ..transaction.manager import transactional
from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    ProposalType,
    ProposalStatus,
)
from ..match.break_rules import DEFAULT_BREAK_RULE, DEFAULT_START_RULE
from ..status_enum import Discipline, MatchStatus

# Import specialized services
from .proposal_service import ProposalService
from .match_lifecycle_service import MatchLifecycleService
from .individual_rack_service import IndividualRackService
from .statistics_service import IndividualMatchStatisticsService


class MatchProposalService:
    """Service for match proposal specific operations.

    Note: This is a convenience facade that delegates to IndividualMatchService.
    """

    @staticmethod
    def create_proposal(
        proposer_id: int,
        proposal_type: ProposalType,
        location: str,
        scheduled_at: datetime,
        expires_at: datetime,
        discipline: str = Discipline.EIGHT_BALL.value,
        distance: Optional[int] = 5,
        is_race_to: bool = True,
        break_rule: str = DEFAULT_BREAK_RULE.value,
        start_rule: str = DEFAULT_START_RULE.value,
        description: Optional[str] = None,
        invited_user_ids: Optional[List[int]] = None,
        billiard_hall_id: Optional[int] = None,
        is_multi_set: bool = False,
        match_distance: Optional[int] = None,
    ) -> MatchProposal:
        """Create a match proposal with invitations if needed.

        Args:
            distance: Racks per set (or None for free format)
            is_multi_set: Whether match is multi-set
            match_distance: Number of sets to win (only for multi-set)
        """
        if proposal_type == ProposalType.DIRECT:
            return ProposalService.create_direct_proposal(
                proposer_id=proposer_id,
                invited_user_ids=invited_user_ids or [],
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                is_race_to=is_race_to,
                break_rule=break_rule,
                start_rule=start_rule,
                description=description,
                billiard_hall_id=billiard_hall_id,
                is_multi_set=is_multi_set,
                match_distance=match_distance,
            )
        else:
            return ProposalService.create_open_proposal(
                proposer_id=proposer_id,
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                is_race_to=is_race_to,
                break_rule=break_rule,
                start_rule=start_rule,
                description=description,
                billiard_hall_id=billiard_hall_id,
                is_multi_set=is_multi_set,
                match_distance=match_distance,
            )

    @staticmethod
    def get_user_proposals(user_id: int) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""
        return ProposalService.get_user_proposals(user_id)

    @staticmethod
    def accept_proposal(proposal_id: int, user_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        return ProposalService.accept_proposal(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def reject_proposal(proposal_id: int, user_id: int) -> None:
        """Reject a match proposal invitation.

        Handles both simple rejection (pending invitation) and un-acceptance
        (already accepted invitation). If the user was the acceptor, reverts
        the proposal to pending and deletes any created match.
        """
        from .models import InvitationStatus

        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=user_id
        ).first()

        if not invitation:
            raise ValueError("Invito non trovato")

        if invitation.status == InvitationStatus.REJECTED:
            return  # Already rejected, idempotent

        from ..base import utc_now

        invitation.status = InvitationStatus.REJECTED
        invitation.responded_at = utc_now()

        # If this was the accepted user, un-accept the proposal
        proposal = invitation.proposal
        if (
            proposal.status == ProposalStatus.ACCEPTED
            and proposal.accepted_by_id == user_id
        ):
            proposal.status = ProposalStatus.PENDING
            proposal.accepted_by_id = None
            proposal.accepted_at = None

            # Delete any existing match created from this proposal
            existing_match = IndividualMatch.query.filter_by(
                proposal_id=proposal_id
            ).first()
            if existing_match and existing_match.status == MatchStatus.SCHEDULED.value:
                db.session.delete(existing_match)

        # Chi ha proposto merita la risposta. Accettare avvisa, scadere
        # avvisa, essere scartati per l'accettazione di un altro avvisa:
        # rifiutare no, e chi aveva proposto restava ad aspettare qualcosa che
        # era già successo.
        #
        # Solo sulle proposte **dirette**, cioè quelle rivolte a qualcuno in
        # particolare. Una proposta aperta la vedono in molti e non è rivolta a
        # nessuno: un avviso per ogni rifiuto sarebbe rumore.
        if proposal.proposal_type == ProposalType.DIRECT:
            MatchProposalService._notify_rejection(proposal, user_id)

    @staticmethod
    def _notify_rejection(proposal: MatchProposal, rejecter_id: int) -> None:
        """Avvisa chi ha proposto che l'invito è stato rifiutato.

        Un errore qui non deve annullare il rifiuto: la notifica è un di più,
        la risposta è il fatto. Stessa scelta di ``accept_proposal``.
        """
        from flask_babel import gettext as _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationPriority, NotificationType
        from ..user.models import User

        from flask_babel import lazy_gettext as _l

        try:
            rejecter = db.session.get(User, rejecter_id)
            nome = rejecter.username if rejecter else None
            luogo = proposal.location_display or ""

            def messaggio() -> str:
                # Composto nella lingua di chi ha proposto (ADR-062).
                dove = " " + _("a %(loc)s", loc=luogo) if luogo else ""
                return _(
                    "%(player)s ha rifiutato la tua proposta di sfida%(location)s",
                    player=nome or _("Un giocatore"),
                    location=dove,
                )

            NotificationFactory.create_bulk_notification(
                user_ids=[proposal.proposer_id],
                notification_type=NotificationType.MATCH_DECLINED,
                title=_l("Proposta rifiutata"),
                message=messaggio,
                priority=NotificationPriority.NORMAL,
                action_url=f"/match/proposals/{proposal.id}",
                action_text=_l("Vedi la proposta"),
            )
        except Exception:  # pragma: no cover - la notifica non blocca il rifiuto
            pass

    @staticmethod
    def cancel_proposal(proposal_id: int, user_id: int) -> None:
        """Cancel a proposal."""
        return ProposalService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    def delete_proposal(proposal_id: int, user_id: int) -> None:
        """Cancella davvero la proposta (la riga sparisce)."""
        return ProposalService.delete_proposal(user_id, proposal_id)

    @staticmethod
    def expire_proposals() -> int:
        """Mark expired proposals as expired. Returns count of expired proposals."""
        return ProposalService.expire_old_proposals()


class IndividualMatchService:
    """Facade for individual match management - delegates to specialized services.

    This class maintains backward compatibility by delegating to:
    - ProposalService: Proposal-related methods
    - MatchLifecycleService: Match state methods
    - IndividualRackService: Rack operations
    - IndividualMatchStatisticsService: Statistics and queries
    """

    # ========== Proposal Methods (delegate to ProposalService) ==========

    @staticmethod
    def create_direct_proposal(
        proposer_id: int,
        invited_user_ids: List[int],
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        billiard_hall_id: Optional[int] = None,
    ) -> MatchProposal:
        """Create a direct match proposal to specific players."""
        return ProposalService.create_direct_proposal(
            proposer_id=proposer_id,
            invited_user_ids=invited_user_ids,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            billiard_hall_id=billiard_hall_id,
        )

    @staticmethod
    def create_open_proposal(
        proposer_id: int,
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        billiard_hall_id: Optional[int] = None,
    ) -> MatchProposal:
        """Create an open match proposal for all eligible players."""
        return ProposalService.create_open_proposal(
            proposer_id=proposer_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            billiard_hall_id=billiard_hall_id,
        )

    @staticmethod
    def create_match_proposal(
        proposer_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        proposed_date: Optional[date] = None,
        proposed_time: Optional[str] = None,
        location: Optional[str] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        max_participants: Optional[int] = None,
        is_open_invitation: bool = False,
        **kwargs,
    ) -> MatchProposal:
        """Create a match proposal - unified method supporting both types."""
        return ProposalService.create_match_proposal(
            proposer_id=proposer_id,
            title=title,
            description=description,
            proposed_date=proposed_date,
            proposed_time=proposed_time,
            location=location,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            max_participants=max_participants,
            is_open_invitation=is_open_invitation,
            **kwargs,
        )

    @staticmethod
    def invite_player_to_match(
        proposal_id: int, inviter_id: int, invitee_id: int
    ) -> ProposalInvitation:
        """Create an invitation for a specific player to join a match proposal."""
        return ProposalService.invite_player_to_match(
            proposal_id, inviter_id, invitee_id
        )

    @staticmethod
    def respond_to_invitation(
        invitation_id: int, invitee_id: int, response: str
    ) -> bool:
        """Respond to a match invitation."""
        return ProposalService.respond_to_invitation(
            invitation_id, invitee_id, response
        )

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = False
    ) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""
        return ProposalService.get_user_proposals(user_id, include_expired)

    @staticmethod
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        return ProposalService.accept_proposal(user_id, proposal_id)

    @staticmethod
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a direct invitation."""
        return ProposalService.reject_invitation(user_id, proposal_id)

    @staticmethod
    def cancel_proposal(user_id: int, proposal_id: int) -> None:
        """Cancel a match proposal."""
        return ProposalService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    def delete_proposal(user_id: int, proposal_id: int) -> None:
        """Cancella davvero la proposta (la riga sparisce)."""
        return ProposalService.delete_proposal(user_id, proposal_id)

    @staticmethod
    def expire_old_proposals() -> int:
        """Expire proposals that have passed their expiration time."""
        return ProposalService.expire_old_proposals()

    @staticmethod
    def _expire_pending_proposals() -> int:
        """Mark expired pending proposals as expired."""
        return ProposalService._expire_pending_proposals()

    @staticmethod
    def express_interest_in_open_invitation(
        proposal_id: int, interested_player_id: int, message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Express interest in an open invitation."""
        return ProposalService.express_interest_in_open_invitation(
            proposal_id, interested_player_id, message
        )

    @staticmethod
    def accept_interest_for_open_invitation(
        proposal_id: int, proposer_id: int, accepted_player_id: int
    ) -> Dict[str, Any]:
        """Accept an interest expressed for an open invitation."""
        return ProposalService.accept_interest_for_open_invitation(
            proposal_id, proposer_id, accepted_player_id
        )

    @staticmethod
    def create_individual_match_from_accepted_invitation(
        invitation_id: int,
    ) -> IndividualMatch:
        """Create individual match from an accepted invitation."""
        return ProposalService.create_individual_match_from_accepted_invitation(
            invitation_id
        )

    # ========== Match Time Methods ==========

    @staticmethod
    @transactional(domain="individual_match")
    def update_times(
        match_id: int,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        user_id: Optional[int] = None,
    ) -> IndividualMatch:
        """Update individual match start and end times.

        Permesso: **i due giocatori**, e la domanda la fa la partita
        (`IndividualMatch.is_player`), non la proposta.

        Prima chiedeva «sei il proponente?» passando da `match.proposal`, che
        è un oggetto di un altro concetto — il modo in cui la partita è nata —
        e che una partita da avvio rapido non ha: lì il pannello «Orari» non
        compariva a nessuno dei due. Punteggio e orari sono proprietà della
        partita e si comportano allo stesso modo comunque sia nata, come già
        fa il segnapunti.

        Args:
            match_id: ID of the individual match
            started_at: New start datetime (if provided)
            ended_at: New end datetime (if provided)
            user_id: User making the change (for permission check)

        Returns:
            Updated IndividualMatch

        Raises:
            ValueError: If match not found or user lacks permission
        """
        match = db.session.get(IndividualMatch, match_id)
        if not match:
            raise ValueError(f"IndividualMatch {match_id} not found")

        if user_id is not None and not match.is_player(user_id):
            raise ValueError("Gli orari li correggono i due giocatori")

        # Coerenza temporale: end non può precedere start (considerando i
        # valori già presenti quando se ne aggiorna uno solo).
        new_started = started_at if started_at is not None else match.started_at
        new_ended = ended_at if ended_at is not None else match.ended_at
        if new_started and new_ended and new_ended < new_started:
            raise ValueError("L'orario di fine non può precedere quello di inizio")

        if started_at is not None:
            match.started_at = started_at

        if ended_at is not None:
            match.ended_at = ended_at

        return match

    #: I campi che una sfida già creata si lascia ancora cambiare. Non è
    #: l'elenco delle colonne: è l'elenco di **come si gioca**, cioè quello che
    #: l'avvio rapido decide per conto tuo pescandolo dall'ultima partita
    #: (`QuickMatchService._resolve_config`) e che quindi è anche quello che si
    #: ritrova sbagliato. Punteggio, stato, giocatori e orari non sono qui: i
    #: primi tre non si correggono, gli orari hanno già `update_times`.
    EDITABLE_SETTINGS = (
        "discipline",
        "distance",
        "is_race_to",
        "break_rule",
        "start_rule",
        "is_multi_set",
        "match_distance",
        "is_race_to_sets",
        "billiard_hall_id",
        "location",
        "scheduled_at",
    )

    @staticmethod
    @transactional(domain="individual_match")
    def update_settings(match_id: int, user_id: int, **fields: Any) -> IndividualMatch:
        """Corregge come si gioca una sfida, finché non è stato segnato niente.

        La finestra è la stessa dell'annullamento — `can_be_revised()` — e per
        la stessa ragione: cambiare la distanza a metà partita riscriverebbe
        il significato dei triangoli già segnati, e chi ha vinto un «al 5»
        scoprirebbe di aver giocato un «al 7».

        Con l'avvio rapido (ADR-051) questa è la sola via d'uscita da una
        precompilazione sbagliata: la partita nasce già in corso, quindi il
        momento in cui si sarebbe potuto rileggere il modulo non esiste.
        """
        match = db.session.get(IndividualMatch, match_id)
        if not match:
            raise ValueError(f"IndividualMatch {match_id} not found")

        if not match.is_player(user_id):
            raise ValueError("La sfida la correggono i due giocatori")

        if not match.can_be_revised():
            raise ValueError(
                "La sfida è cominciata: come si gioca si decide "
                "prima del primo triangolo"
            )

        sconosciuti = set(fields) - set(IndividualMatchService.EDITABLE_SETTINGS)
        if sconosciuti:
            raise ValueError(
                f"Campi non modificabili: {', '.join(sorted(sconosciuti))}"
            )

        for nome, valore in fields.items():
            setattr(match, nome, valore)

        # Un match a set senza set aperto non è giocabile, e uno che smette di
        # essere a set si porta dietro un set fantasma. Siccome qui non è stato
        # ancora segnato niente, il primo set si può rifare da zero senza
        # perdere nulla.
        if match.status == MatchStatus.IN_PROGRESS:
            for vecchio_set in list(match.sets or []):
                db.session.delete(vecchio_set)
            match.sets = []
            if match.is_multi_set:
                match.start_first_set()

        return match

    # ========== Match Lifecycle Methods (delegate to MatchLifecycleService) ==========

    @staticmethod
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        return MatchLifecycleService.start_match(match_id, user_id)

    @staticmethod
    def start_next_set(match_id: int, user_id: int):
        return MatchLifecycleService.start_next_set(match_id, user_id)

    @staticmethod
    def confirm_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Confirm match result by a player (new UX)."""
        return MatchLifecycleService.confirm_match_result(match_id, user_id)

    @staticmethod
    def reject_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Reject match result - removes last rack (new UX)."""
        return MatchLifecycleService.reject_match_result(match_id, user_id)

    @staticmethod
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match - legacy method for backward compatibility."""
        return MatchLifecycleService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Complete an individual match - alias for complete_match."""
        return MatchLifecycleService.complete_individual_match(
            match_id, winner_id, user_id
        )

    @staticmethod
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        return MatchLifecycleService.cancel_match(match_id, user_id, reason)

    @staticmethod
    def forfeit_match(match_id: int, user_id: int) -> IndividualMatch:
        """Forfeit a match - user loses, opponent wins.

        The forfeiting player keeps their current score (racks already won).
        The opponent receives the winning score (distance).

        Args:
            match_id: ID of the match
            user_id: ID of player forfeiting

        Returns:
            The updated IndividualMatch object
        """
        # No @transactional here - MatchLifecycleService.forfeit_match has it
        return MatchLifecycleService.forfeit_match(match_id, user_id)

    # ========== Rack Methods (delegate to IndividualRackService) ==========

    @staticmethod
    def add_rack_for_player(
        match_id: int,
        user_id: int,
        winner_id: int,
    ) -> IndividualRack:
        """Add a rack won by specified player (new simplified UX)."""
        # No @transactional here - IndividualRackService.add_rack_for_player has it
        return IndividualRackService.add_rack_for_player(match_id, user_id, winner_id)

    @staticmethod
    def remove_rack_for_player(
        match_id: int,
        user_id: int,
        player_id: int,
    ) -> None:
        """Remove last rack won by specified player (new simplified UX)."""
        # No @transactional here - IndividualRackService.remove_rack_for_player has it
        return IndividualRackService.remove_rack_for_player(
            match_id, user_id, player_id
        )

    @staticmethod
    def register_lag(
        match_id: int, lag_winner_id: int, first_break_player_id: int
    ) -> None:
        """Esito dell'acchito (delegates to IndividualRackService)."""
        return IndividualRackService.register_lag(
            match_id, lag_winner_id, first_break_player_id
        )

    @staticmethod
    def toggle_run_out(match_id: int, rack_id: int) -> dict:
        """Marca/smarca un triangolo come runout (delegates)."""
        return IndividualRackService.toggle_run_out(match_id, rack_id)

    @staticmethod
    def submit_rack_result(
        match_id: int,
        user_id: int,
        winner_id: int,
        rack_number: int,
        notes: Optional[str] = None,
    ) -> IndividualRack:
        """Submit result for a rack - legacy method for backward compatibility.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService.submit_rack_result(
            match_id, user_id, winner_id, rack_number, notes
        )

    @staticmethod
    def add_rack_result(
        match_id: int,
        rack_number: Optional[int] = None,
        winner_id: Optional[int] = None,
        reported_by_id: Optional[int] = None,
        break_player_id: Optional[int] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> IndividualRack:
        """Add a rack result with flexible parameters for test compatibility.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService.add_rack_result(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            break_player_id=break_player_id,
            notes=notes,
            **kwargs,
        )

    @staticmethod
    def _add_rack_result_original(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualRack:
        """Original add_rack_result implementation.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService._add_rack_result_original(
            match_id, winner_id, user_id
        )

    @staticmethod
    def confirm_rack_result(rack_id: int, confirming_player_id: int) -> Dict[str, Any]:
        """Confirm a rack result.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService.confirm_rack_result(rack_id, confirming_player_id)

    @staticmethod
    def dispute_rack_result(
        rack_id: int, disputing_player_id: int, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispute a rack result.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService.dispute_rack_result(
            rack_id, disputing_player_id, reason
        )

    @staticmethod
    def resolve_rack_dispute(
        rack_id: int, admin_user_id: int, resolution: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a rack result dispute.

        No @transactional: IndividualRackService owns the transaction.
        """
        return IndividualRackService.resolve_rack_dispute(
            rack_id, admin_user_id, resolution, reason
        )

    # ========== Statistics Methods (delegate to statistics service) ==========

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user."""
        return IndividualMatchStatisticsService.get_user_dashboard_data(user_id)

    @staticmethod
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Get user's availability settings and schedule."""
        return IndividualMatchStatisticsService.get_user_availability(user_id)

    @staticmethod
    def get_admin_overview() -> Dict[str, Any]:
        """Get admin overview of all individual matches."""
        return IndividualMatchStatisticsService.get_admin_overview()

    @staticmethod
    def get_user_matches(
        user_id: int, status_filter: Optional[MatchStatus] = None
    ) -> List[IndividualMatch]:
        """Get individual matches for a user."""
        return IndividualMatchStatisticsService.get_user_matches(user_id, status_filter)

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        return IndividualMatchStatisticsService.get_user_statistics(user_id)

    # ========== Availability Methods ==========
    #
    # Availability (location string + venue FK) and player discovery are owned
    # by AvailabilityService (models/individual_match/availability_service.py),
    # the single source of truth also consumed by ProposalService. The legacy
    # write-side duplicates that used to live here were removed when the
    # availability surface was consolidated into the individual_match blueprint
    # (see docs/adr/ADR-032-availability-surface-consolidation.md).
