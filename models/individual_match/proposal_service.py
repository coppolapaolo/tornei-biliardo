"""
Module: models/individual_match/proposal_service.py
Purpose: Match proposal management service (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date, time as time_obj

from sqlalchemy.exc import IntegrityError

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    ProposalType,
    ProposalStatus,
    InvitationStatus,
)
from ..location.models import UserLocationAvailability


def _reconcile_user_achievements(user_id: int) -> None:
    """Riconcilia gli achievement dell'utente dopo un'azione sulle proposte.

    Mirror del pattern di privacy_service: chiamata cross-dominio verso la
    gamification con errori isolati — un fallimento gamification non deve mai
    bloccare la creazione/accettazione di una proposta. Metric-driven: una sola
    riconciliazione copre social_butterfly/popular_player (e qualunque futuro
    achievement basato su dati reali).
    """
    try:
        from models.gamification.achievement_service import AchievementService

        AchievementService.reconcile_achievements(user_id)
    except Exception:
        pass


class ProposalService:
    """Service for match proposal creation and management."""

    @staticmethod
    @transactional(domain="individual_match")
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
        start_rule: Optional[str] = None,
        description: Optional[str] = None,
        billiard_hall_id: Optional[int] = None,
        is_multi_set: bool = False,
        match_distance: Optional[int] = None,
    ) -> MatchProposal:
        """Create a direct match proposal to specific players.

        Args:
            distance: Racks per set (or None for free format)
            is_multi_set: Whether match is multi-set
            match_distance: Number of sets to win (only for multi-set)
        """
        from models.base import utc_now

        if scheduled_at < utc_now():
            raise ValueError("Non è possibile programmare un match nel passato")

        if expires_at is None:
            expires_at = scheduled_at - timedelta(hours=2)

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.DIRECT,
            billiard_hall_id=billiard_hall_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            start_rule=start_rule,
            description=description,
            is_multi_set=is_multi_set,
            match_distance=match_distance,
        )

        db.session.add(proposal)
        db.session.flush()

        from ..user.models import User
        from ..notification.factory import NotificationFactory

        proposer = User.query.get(proposer_id)

        for user_id in invited_user_ids:
            if user_id != proposer_id:
                invitation = ProposalInvitation(
                    proposal_id=proposal.id, invited_user_id=user_id
                )
                db.session.add(invitation)

                try:
                    proposer_name = proposer.username if proposer else "Un giocatore"
                    scheduled_time_str = (
                        scheduled_at.strftime("%d/%m/%Y alle %H:%M")
                        if scheduled_at
                        else None
                    )

                    NotificationFactory.create_match_notification(
                        user_id=user_id,
                        match_type="proposal",
                        player_names=[proposer_name],
                        location_name=location,
                        scheduled_time=scheduled_time_str,
                        proposal_id=proposal.id,
                    )
                except Exception:
                    pass  # Notification failure shouldn't block proposal creation

        # Gamification: il proponente può aver sbloccato "social_butterfly".
        _reconcile_user_achievements(proposer_id)

        return proposal

    @staticmethod
    @transactional(domain="individual_match")
    def create_open_proposal(
        proposer_id: int,
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        break_rule: Optional[str] = None,
        start_rule: Optional[str] = None,
        description: Optional[str] = None,
        billiard_hall_id: Optional[int] = None,
        is_multi_set: bool = False,
        match_distance: Optional[int] = None,
    ) -> MatchProposal:
        """Create an open match proposal for all eligible players.

        Args:
            distance: Racks per set (or None for free format)
            is_multi_set: Whether match is multi-set
            match_distance: Number of sets to win (only for multi-set)
        """
        from flask_babel import _
        from ..user.models import User
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority
        from .availability_service import AvailabilityService
        from models.base import utc_now

        if scheduled_at < utc_now():
            raise ValueError("Non è possibile programmare un match nel passato")

        if expires_at is None:
            expires_at = scheduled_at - timedelta(hours=2)

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.OPEN,
            billiard_hall_id=billiard_hall_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            start_rule=start_rule,
            description=description,
            is_multi_set=is_multi_set,
            match_distance=match_distance,
        )

        db.session.add(proposal)
        db.session.flush()  # Get proposal.id for action_url

        # Notify eligible players about the open proposal
        try:
            proposer = db.session.get(User, proposer_id)
            proposer_name = proposer.username if proposer else _("Un giocatore")
            location_text = location or ""

            # Find eligible players based on venue or location
            eligible_user_ids: List[int] = []

            if billiard_hall_id:
                # Venue-based: find players available at this venue
                venue_players = AvailabilityService.get_available_players_at_venue(
                    billiard_hall_id=billiard_hall_id, exclude_user_id=proposer_id
                )
                eligible_user_ids = [p["user_id"] for p in venue_players]
            elif location:
                # Free-text location (no venue FK): notify players who have
                # already played there (ADR-033 — no more location availability).
                eligible_user_ids = (
                    AvailabilityService.get_players_who_played_at_location(
                        location=location, exclude_user_id=proposer_id
                    )
                )

            if eligible_user_ids:
                scheduled_str = scheduled_at.strftime("%d/%m/%Y alle %H:%M")
                # Suffisso località tradotto a parte: pybabel non estrae le
                # chiamate _() annidate negli argomenti di un altro _().
                loc_suffix = (
                    " " + _("a %(loc)s", loc=location_text) if location_text else ""
                )
                NotificationFactory.create_bulk_notification(
                    user_ids=eligible_user_ids,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    title=_("Nuova proposta di match"),
                    message=_(
                        "%(username)s propone un match aperto%(location)s il %(date)s",
                        username=proposer_name,
                        location=loc_suffix,
                        date=scheduled_str,
                    ),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
        except Exception:
            pass  # Notification failure shouldn't block proposal creation

        # Gamification: il proponente può aver sbloccato "social_butterfly".
        _reconcile_user_achievements(proposer_id)

        return proposal

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
        # Silence unused parameter warnings (kept for API compatibility)
        _ = title, max_participants, is_open_invitation

        if proposed_date and proposed_time:
            if isinstance(proposed_time, str):
                hour, minute = map(int, proposed_time.split(":"))
                proposed_time_obj = time_obj(hour, minute)
            else:
                proposed_time_obj = proposed_time
            scheduled_at = datetime.combine(proposed_date, proposed_time_obj)
        else:
            scheduled_at = kwargs.get("scheduled_at", utc_now())

        if not location:
            location = "TBD"

        return ProposalService.create_open_proposal(
            proposer_id=proposer_id,
            location=location,
            scheduled_at=scheduled_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            description=description,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def invite_player_to_match(
        proposal_id: int, inviter_id: int, invitee_id: int
    ) -> ProposalInvitation:
        """Create an invitation for a specific player to join a match proposal."""

        invitation = ProposalInvitation(
            proposal_id=proposal_id,
            invited_user_id=invitee_id,
            status=InvitationStatus.PENDING,
        )

        # Savepoint forces the UNIQUE violation to surface at flush time so
        # we can translate IntegrityError into a user-friendly ValueError.
        # (The outer @transactional will still roll back, which is correct —
        # we don't want a partial invitation row.)
        from flask_babel import _

        try:
            with db.session.begin_nested():
                db.session.add(invitation)
                db.session.flush()
        except IntegrityError as exc:
            raise ValueError(_("Giocatore già invitato a questa proposta")) from exc

        return invitation

    @staticmethod
    @transactional(domain="individual_match")
    def respond_to_invitation(
        invitation_id: int, invitee_id: int, response: str
    ) -> bool:
        """Respond to a match invitation."""

        invitation = ProposalInvitation.query.get(invitation_id)
        if not invitation or invitation.invited_user_id != invitee_id:
            return False

        if response.lower() == "accepted":
            invitation.status = InvitationStatus.ACCEPTED
            ProposalService.accept_proposal(
                user_id=invitee_id, proposal_id=invitation.proposal_id
            )
        else:
            invitation.status = InvitationStatus.REJECTED

        return True

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = True
    ) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship.

        Args:
            user_id: The user to get proposals for
            include_expired: Whether to include expired proposals in sent/received
                           (default True to show full history)

        Returns:
            Dict with keys matching template expectations:
            - sent_proposals: Proposals created by this user
            - received_proposals: Direct invitations to this user
            - open_proposals: Open proposals from others (only PENDING, not expired)
        """
        ProposalService._expire_pending_proposals()

        # For sent and received: show all proposals (including expired) for history
        # User wants to see their full proposal history
        if include_expired:
            sent_proposals = (
                MatchProposal.query.filter_by(proposer_id=user_id)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

            received_proposals = (
                MatchProposal.query.join(
                    ProposalInvitation,
                    MatchProposal.id == ProposalInvitation.proposal_id,
                )
                .filter(ProposalInvitation.invited_user_id == user_id)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )
        else:
            # Filter to only active proposals
            active_filter = db.or_(
                db.and_(
                    MatchProposal.status == ProposalStatus.PENDING,
                    MatchProposal.expires_at > utc_now(),
                ),
                MatchProposal.status == ProposalStatus.ACCEPTED,
                MatchProposal.status == ProposalStatus.CANCELLED,
            )

            sent_proposals = (
                MatchProposal.query.filter_by(proposer_id=user_id)
                .filter(active_filter)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

            received_proposals = (
                MatchProposal.query.join(
                    ProposalInvitation,
                    MatchProposal.id == ProposalInvitation.proposal_id,
                )
                .filter(ProposalInvitation.invited_user_id == user_id)
                .filter(active_filter)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

        # For open proposals: always show only PENDING and not expired
        # (users can't accept expired proposals)
        open_proposals = (
            MatchProposal.query.filter(
                MatchProposal.proposal_type == ProposalType.OPEN,
                MatchProposal.proposer_id != user_id,
                MatchProposal.status == ProposalStatus.PENDING,
                MatchProposal.expires_at > utc_now(),
            )
            .order_by(MatchProposal.created_at.desc())
            .all()
        )

        # Filter open proposals by the user's eligible venues/locations.
        # Eligibility (ADR-033): venues the user is available at, plus the
        # venues/locations where the user has already played.
        eligible_venue_ids = {
            av.billiard_hall_id
            for av in UserLocationAvailability.query.filter_by(
                user_id=user_id, is_available=True
            ).all()
        }

        played_matches = IndividualMatch.query.filter(
            db.or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            )
        ).all()
        eligible_locations = {m.location for m in played_matches if m.location}
        eligible_venue_ids |= {
            m.billiard_hall_id for m in played_matches if m.billiard_hall_id
        }

        if eligible_venue_ids or eligible_locations:
            open_proposals = [
                p
                for p in open_proposals
                if (p.billiard_hall_id and p.billiard_hall_id in eligible_venue_ids)
                or (p.location and p.location in eligible_locations)
            ]

        return {
            "sent_proposals": sent_proposals,
            "received_proposals": received_proposals,
            "open_proposals": open_proposals,
        }

    @staticmethod
    @transactional(domain="individual_match")
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority
        from ..user.models import User

        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            raise ValueError("Proposta non trovata")

        if not proposal.can_be_accepted_by(user_id):
            raise ValueError("User cannot accept this proposal")

        # Chi resta fuori, letto PRIMA dell'accettazione: proposal.accept()
        # porta questi inviti a REJECTED, e dopo non si distinguerebbero più
        # da quelli rifiutati dall'invitato stesso.
        discarded_ids = [
            invitation.invited_user_id
            for invitation in proposal.invitations
            if invitation.status == InvitationStatus.PENDING
            and invitation.invited_user_id != user_id
        ]

        # Savepoint forces the UNIQUE(proposal_id) violation to surface at
        # flush time so we can translate it to ValueError. Fires only if
        # another transaction accepted first (TOCTOU). Outer @transactional
        # still rolls back — correct, the partial acceptance must not persist.
        try:
            with db.session.begin_nested():
                individual_match = proposal.accept(user_id)
                db.session.flush()
        except IntegrityError as exc:
            raise ValueError(_("Proposta già accettata")) from exc

        location_text = proposal.location_display or ""
        loc_suffix = " " + _("a %(loc)s", loc=location_text) if location_text else ""

        # Notify proposer that their proposal was accepted
        try:
            accepter = db.session.get(User, user_id)
            accepter_name = accepter.username if accepter else _("Un giocatore")

            NotificationFactory.create_bulk_notification(
                user_ids=[proposal.proposer_id],
                notification_type=NotificationType.MATCH_ACCEPTED,
                title=_("Proposta accettata!"),
                message=_(
                    "%(player)s ha accettato la tua proposta di match%(location)s",
                    player=accepter_name,
                    location=loc_suffix,
                ),
                priority=NotificationPriority.HIGH,
                action_url=f"/match/matches/{individual_match.id}",
                action_text=_("Vai al match"),
            )
        except Exception:
            pass  # Notification failure shouldn't block acceptance

        # Gli altri invitati: proposal.accept() li ha messi a REJECTED, e senza
        # questo avviso la proposta sparirebbe dai loro elenchi in silenzio.
        # Solo il percorso diretto: sulle proposte aperte avvisa già
        # accept_interest_for_open_invitation, e notificare anche qui
        # significherebbe mandare due volte la stessa cosa.
        if discarded_ids and proposal.proposal_type == ProposalType.DIRECT:
            try:
                NotificationFactory.create_bulk_notification(
                    user_ids=discarded_ids,
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta di match chiusa"),
                    message=_(
                        "La proposta di match%(location)s è stata accettata "
                        "da un altro giocatore.",
                        location=loc_suffix,
                    ),
                    priority=NotificationPriority.NORMAL,
                    continue_on_error=True,
                )
            except Exception:
                pass  # Notification failure shouldn't block acceptance

        # Gamification: chi accetta può aver sbloccato "popular_player".
        _reconcile_user_achievements(user_id)

        return individual_match

    @staticmethod
    @transactional(domain="individual_match")
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a direct invitation."""
        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=user_id
        ).first_or_404()

        invitation.reject()

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_proposal(user_id: int, proposal_id: int) -> None:
        """Cancel a match proposal."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            raise ValueError("Proposta non trovata")

        if proposal.proposer_id != user_id:
            raise ValueError("Only the proposer can cancel the proposal")

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("Proposal cannot be cancelled - it's not pending")

        proposal.cancel()

    @staticmethod
    @transactional(domain="individual_match")
    def delete_proposal(user_id: int, proposal_id: int) -> None:
        """Cancella davvero la proposta: la riga sparisce.

        Diversa da `cancel_proposal`, che la lascia dov'è cambiandole stato.
        Le due servono a due cose diverse e vanno tenute distinte: annullare
        dice «non si gioca più» e resta scritto — la persona invitata, che ha
        ricevuto la notifica, deve poter capire cos'è successo. Cancellare dice
        «questa non doveva esistere», e vale per la proposta aperta per sbaglio,
        o rimasta lì a ingombrare l'elenco per mesi.

        Non si cancella una proposta da cui è nata una partita ancora viva: la
        partita è il fatto, la proposta è solo il modo in cui ci si è arrivati,
        e toglierle il presupposto sotto lascerebbe una FK appesa. Se la
        partita è stata a sua volta annullata, allora non resta niente da
        proteggere e la proposta se ne va con lei.
        """
        from flask_babel import _
        from ..exceptions import ConflictError, NotFoundError, PermissionDeniedError
        from ..notification.models import Notification
        from ..status_enum import MatchStatus

        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            raise NotFoundError(_("Proposta non trovata"))

        if proposal.proposer_id != user_id:
            raise PermissionDeniedError(_("La proposta la cancella chi l'ha fatta."))

        match = proposal.individual_match
        if match is not None:
            stato = (
                match.status.value if hasattr(match.status, "value") else match.status
            )
            if stato != MatchStatus.CANCELLED.value:
                raise ConflictError(
                    _(
                        "Da questa proposta è nata una partita: "
                        "per farla sparire annulla prima quella."
                    )
                )
            # La partita annullata resta, ma smette di puntare a una riga che
            # non esisterà più: la FK non ha `ondelete`, quindi il distacco va
            # fatto qui e non lasciato al database.
            match.proposal_id = None

        # Le notifiche già spedite puntano a `/match/proposals/<id>`: senza la
        # riga, quel link è un 404 nella posta di qualcun altro.
        Notification.query.filter_by(
            action_url=f"/match/proposals/{proposal.id}"
        ).delete(synchronize_session=False)

        # Gli inviti se ne vanno da soli: `cascade="all, delete-orphan"`.
        db.session.delete(proposal)

    @staticmethod
    @transactional(domain="individual_match")
    def expire_old_proposals() -> int:
        """Expire proposals that have passed their expiration time."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= utc_now(),
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

            # Notify proposer that their proposal expired
            try:
                location_text = proposal.location or ""
                loc_suffix = (
                    " " + _("a %(loc)s", loc=location_text) if location_text else ""
                )
                NotificationFactory.create_bulk_notification(
                    user_ids=[proposal.proposer_id],
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta scaduta"),
                    message=_(
                        "La tua proposta di match%(location)s è scaduta "
                        "senza accettazioni.",
                        location=loc_suffix,
                    ),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
            except Exception:
                pass  # Notification failure shouldn't block expiration

        return count

    @staticmethod
    @transactional(domain="individual_match")
    def _expire_pending_proposals() -> int:
        """Mark expired pending proposals as expired."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        now = utc_now()

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

            # Notify proposer that their proposal expired
            try:
                location_text = proposal.location or ""
                loc_suffix = (
                    " " + _("a %(loc)s", loc=location_text) if location_text else ""
                )
                NotificationFactory.create_bulk_notification(
                    user_ids=[proposal.proposer_id],
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta scaduta"),
                    message=_(
                        "La tua proposta di match%(location)s è scaduta "
                        "senza accettazioni.",
                        location=loc_suffix,
                    ),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
            except Exception:
                pass  # Notification failure shouldn't block expiration

        return count

    @staticmethod
    @transactional(domain="individual_match")
    def express_interest_in_open_invitation(
        proposal_id: int, interested_player_id: int, message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Express interest in an open invitation."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposal_type != ProposalType.OPEN:
            raise ValueError("Can only express interest in open proposals")

        existing = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=interested_player_id
        ).first()
        if existing:
            raise ValueError("Interest already expressed")

        invitation = ProposalInvitation(
            proposal_id=proposal_id, invited_user_id=interested_player_id
        )
        db.session.add(invitation)
        # flush per assegnare la PK: senza, invitation.id e' None nel return
        # (accedere a .id su un oggetto pending non scatena autoflush).
        db.session.flush()

        return {
            "success": True,
            "invitation_id": invitation.id,
            "message": "Interest expressed successfully",
        }

    @staticmethod
    @transactional(domain="individual_match")
    def accept_interest_for_open_invitation(
        proposal_id: int, proposer_id: int, accepted_player_id: int
    ) -> Dict[str, Any]:
        """Accept an interest expressed for an open invitation."""
        from flask_babel import _

        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposer_id != proposer_id:
            raise ValueError("Only the proposer can accept interests")

        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=accepted_player_id
        ).first()
        if not invitation:
            raise ValueError("No interest found for selected user")

        match = ProposalService.accept_proposal(accepted_player_id, proposal_id)

        other_invitations = (
            ProposalInvitation.query.filter_by(proposal_id=proposal_id)
            .filter(ProposalInvitation.invited_user_id != accepted_player_id)
            .all()
        )

        if other_invitations:
            from ..notification.factory import NotificationFactory
            from ..notification.models import NotificationPriority, NotificationType

            proposal_title = getattr(proposal, "title", "Open match proposal")
            invited_user_ids = [inv.invited_user_id for inv in other_invitations]

            try:
                NotificationFactory.create_bulk_notification(
                    user_ids=invited_user_ids,
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta Match Conclusa"),
                    message=_(
                        "La proposta di match '%(title)s' è stata accettata "
                        "da un altro giocatore.",
                        title=proposal_title,
                    ),
                    priority=NotificationPriority.NORMAL,
                    continue_on_error=True,
                )
            except Exception:
                pass

        return {
            "success": True,
            "match_id": match.id,
            "message": "Interest accepted successfully",
        }

    @staticmethod
    @transactional(domain="individual_match")
    def create_individual_match_from_accepted_invitation(
        invitation_id: int,
    ) -> IndividualMatch:
        """Create individual match from an accepted invitation."""
        invitation = db.session.get(ProposalInvitation, invitation_id)
        if not invitation:
            raise ValueError(f"Invitation {invitation_id} not found")

        return ProposalService.accept_proposal(
            invitation.invited_user_id, invitation.proposal_id
        )
