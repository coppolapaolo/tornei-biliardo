"""Proposal CRUD and lifecycle routes for individual matches."""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
import logging

from flask_babel import gettext as _
from flask_login import current_user
from datetime import timedelta

from models.individual_match.services import MatchProposalService
from models.individual_match.models import MatchProposal, ProposalType
from models.match.break_rules import DEFAULT_BREAK_RULE, DEFAULT_START_RULE
from models.status_enum import Discipline
from models.user.permissions import RoleRequirement
from utils.local_time import parse_local_datetime
from utils.route_helpers import safe_json_error

from . import individual_match_bp

logger = logging.getLogger(__name__)


@individual_match_bp.route("/proposals")
@RoleRequirement.player_or_director_required
def proposal_list():
    """List match proposals for current user."""
    try:
        proposals_data = MatchProposalService.get_user_proposals(current_user.id)
        return render_template("individual_match/proposals.html", **proposals_data)
    except Exception as e:
        logger.error("Error loading proposals: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.route("/proposals/<int:proposal_id>")
@RoleRequirement.player_or_director_required
def proposal_detail(proposal_id):
    """View individual match proposal details."""
    try:
        proposal = MatchProposal.query.get_or_404(proposal_id)

        # Check if user has access to this proposal
        user_id = current_user.id
        has_access = (
            proposal.proposer_id == user_id
            or any(inv.invited_user_id == user_id for inv in proposal.invitations)
            or proposal.proposal_type.value == "open"
        )

        if not has_access:
            flash(_("Accesso negato a questa proposta."), "danger")
            return redirect(url_for("individual_match.proposal_list"))

        return render_template(
            "individual_match/proposal_detail.html", proposal=proposal
        )
    except Exception as e:
        logger.error("Error loading proposal: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
        return redirect(url_for("individual_match.proposal_list"))


@individual_match_bp.route("/players/search")
@RoleRequirement.player_or_director_required
def search_players():
    """Search for players by username for direct invitations.

    Query params:
        q: Search query (min 2 chars)
        limit: Max results (default 10)

    Returns JSON array of matching players who have unlocked individual matches.
    Excludes current user and uses can_access("create_match_direct") for consistency.
    """
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)

    if len(query) < 2:
        return jsonify([])

    from models.user.models import User

    # Search by username, exclude current user and soft-deleted users
    users = (
        User.query.filter(
            User.username.ilike(f"%{query}%"),
            User.id != current_user.id,
            User.deleted_at.is_(None),
        )
        .order_by(User.username)
        .all()
    )

    # Filter by feature access (consistent with menu visibility and opponent list)
    eligible_users = [u for u in users if u.can_access("create_match_direct")][:limit]

    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
                "avatar_url": u.avatar_url if hasattr(u, "avatar_url") else None,
            }
            for u in eligible_users
        ]
    )


@individual_match_bp.route("/players/opponents")
@RoleRequirement.player_or_director_required
def get_opponents():
    """Get all players the current user has played against.

    Includes opponents from individual matches, gare, and campionati.
    Filters by can_access("create_match_direct") for consistency with menu visibility.
    Returns players ordered alphabetically by username.

    Returns JSON array for use in TomSelect dropdown.
    """
    from models.individual_match.statistics_service import (
        IndividualMatchStatisticsService,
    )

    opponents = IndividualMatchStatisticsService.get_eligible_opponents(current_user.id)

    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
            }
            for u in opponents
        ]
    )


@individual_match_bp.route("/proposals/create", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def create_proposal():
    """Create new match proposal."""
    if request.method == "GET":
        from models.location.models import BilliardHall
        from models.user.models import User
        from models.base import db

        verified_venues = (
            BilliardHall.query.filter_by(is_active=True, verified=True)
            .order_by(BilliardHall.name)
            .all()
        )

        # Check for rematch parameters
        rematch_opponent = None
        rematch_params = {}

        if request.args.get("rematch") == "true":
            opponent_id = request.args.get("opponent_id", type=int)
            if opponent_id:
                rematch_opponent = db.session.get(User, opponent_id)

            rematch_params = {
                "billiard_hall_id": request.args.get("billiard_hall_id", ""),
                "location": request.args.get("location", ""),
                "discipline": request.args.get(
                    "discipline", Discipline.EIGHT_BALL.value
                ),
                "match_format": request.args.get("match_format", "single"),
                "set_distance": request.args.get("set_distance", "5"),
                "distance": request.args.get("distance", "5"),
                "is_race_to": request.args.get("is_race_to", "true"),
                "break_rule": request.args.get("break_rule", DEFAULT_BREAK_RULE.value),
                "start_rule": request.args.get("start_rule", DEFAULT_START_RULE.value),
                "is_multi_set": request.args.get("is_multi_set", "false"),
                "match_distance": request.args.get("match_distance", ""),
                "is_race_to_sets": request.args.get("is_race_to_sets", "true"),
                "scheduled_at": request.args.get("scheduled_at", ""),
                "expires_hours": request.args.get("expires_hours", "1"),
            }

        return render_template(
            "individual_match/create_proposal.html",
            verified_venues=verified_venues,
            rematch_opponent=rematch_opponent,
            rematch_params=rematch_params,
        )

    try:
        data = request.get_json() if request.is_json else request.form

        # Parse scheduled time. data.get + guard: l'indicizzazione diretta
        # sollevava KeyError (non coperto da except ValueError) → 500.
        #
        # `parse_local_datetime` e non `fromisoformat`: il campo è un
        # `<input type="datetime-local">`, quindi arriva in **ora italiana**,
        # mentre il DB tiene i naive come UTC e `|datetime_local` ci somma il
        # fuso in lettura. Salvandolo grezzo, una proposta per le 21:00 veniva
        # mostrata a entrambi i giocatori come le 23:00.
        scheduled_at_str = data.get("scheduled_at")
        if not scheduled_at_str:
            raise ValueError("Campo scheduled_at mancante")
        scheduled_at = parse_local_datetime(scheduled_at_str)
        if scheduled_at is None:
            raise ValueError("Campo scheduled_at non valido")

        # Calculate expiration (default 1 hour before match)
        expires_hours = int(data.get("expires_hours", 1))
        if expires_hours == 0:
            # "Never" expires (set to 1 year in future) for immediate matches
            expires_at = scheduled_at + timedelta(days=365)
        else:
            expires_at = scheduled_at - timedelta(hours=expires_hours)

        # Convert proposal_type string to enum
        proposal_type_str = data.get("proposal_type", "open")
        proposal_type = (
            ProposalType.DIRECT if proposal_type_str == "direct" else ProposalType.OPEN
        )

        # Look up BilliardHall FK from location string
        location = data["location"].strip() if data.get("location") else ""
        billiard_hall_id = None
        if location:
            from models.location.models import BilliardHall

            venue = BilliardHall.query.filter_by(name=location).first()
            if venue:
                billiard_hall_id = venue.id

        # Parse match format (single, multi, free)
        match_format = data.get("match_format", "single")

        # Determine distance and multi-set configuration based on format
        if match_format == "free":
            # Free format: no distance limit
            distance = None
            is_multi_set = False
            match_distance = None
            is_race_to = True  # Default, not used for free format
        elif match_format == "multi":
            # Multi-set format
            distance = int(data.get("set_distance", 5))  # Racks per set
            is_multi_set = True
            match_distance = int(data.get("match_distance", 3))  # Sets to win
            is_race_to = True  # Sets are always race-to
        else:
            # Single-set format (default)
            distance = int(data.get("distance", 5))
            is_multi_set = False
            match_distance = None
            is_race_to = data.get("is_race_to", "true").lower() == "true"

        proposal_data = {
            "proposer_id": current_user.id,
            "proposal_type": proposal_type,
            "location": location,
            "billiard_hall_id": billiard_hall_id,  # FK to BilliardHall (if found)
            "scheduled_at": scheduled_at,
            "expires_at": expires_at,
            "discipline": data.get("discipline", Discipline.EIGHT_BALL.value),
            "distance": distance,
            "is_race_to": is_race_to,
            "is_multi_set": is_multi_set,
            "match_distance": match_distance,
            "break_rule": data.get("break_rule", DEFAULT_BREAK_RULE.value),
            "start_rule": data.get("start_rule", DEFAULT_START_RULE.value),
            "description": data.get("description"),
            "invited_user_ids": (
                [int(uid) for uid in data.getlist("invited_user_ids")]
                if hasattr(data, "getlist")
                else data.get("invited_user_ids", [])
            ),
        }

        proposal = MatchProposalService.create_proposal(**proposal_data)

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "proposal_id": proposal.id,
                    "message": "Match proposal created successfully",
                }
            )
        else:
            flash(_("Proposta di match creata con successo!"), "success")
            return redirect(
                url_for("individual_match.proposal_detail", proposal_id=proposal.id)
            )

    except ValueError as e:
        error_msg = f"Error creating proposal: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template("individual_match/create_proposal.html")


@individual_match_bp.route("/proposals/<int:proposal_id>/accept", methods=["POST"])
@RoleRequirement.player_or_director_required
def accept_proposal(proposal_id):
    """Accept a match proposal."""
    try:
        individual_match = MatchProposalService.accept_proposal(
            proposal_id, current_user.id
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "match_id": individual_match.id,
                    "message": "Proposal accepted successfully",
                }
            )
        else:
            flash(_("Proposta accettata con successo!"), "success")
            return redirect(
                url_for("individual_match.match_detail", match_id=individual_match.id)
            )

    except ValueError as e:
        error_msg = f"Error accepting proposal: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(
                url_for("individual_match.proposal_detail", proposal_id=proposal_id)
            )


@individual_match_bp.route("/proposals/<int:proposal_id>/cancel", methods=["POST"])
@RoleRequirement.player_or_director_required
def cancel_proposal(proposal_id):
    """Cancel a match proposal (proposer only)."""
    try:
        MatchProposalService.cancel_proposal(proposal_id, current_user.id)

        if request.is_json:
            return jsonify(
                {"success": True, "message": "Proposal cancelled successfully"}
            )
        else:
            flash(_("Proposta annullata con successo!"), "success")
            return redirect(url_for("individual_match.proposal_list"))

    except ValueError as e:
        error_msg = f"Error cancelling proposal: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(
                url_for("individual_match.proposal_detail", proposal_id=proposal_id)
            )


@individual_match_bp.route("/proposals/<int:proposal_id>/delete", methods=["POST"])
@RoleRequirement.player_or_director_required
def delete_proposal(proposal_id):
    """Cancella davvero la proposta: la riga sparisce (solo il proponente).

    Distinta da `cancel_proposal`, che la lascia dov'è marcandola annullata.
    """
    from models.exceptions import DomainError, http_status_for_exception

    try:
        MatchProposalService.delete_proposal(proposal_id, current_user.id)
    except (DomainError, ValueError) as exc:
        stato = http_status_for_exception(exc) if isinstance(exc, DomainError) else 400
        if request.is_json:
            return jsonify({"success": False, "error": str(exc)}), stato
        flash(str(exc), "danger")
        return redirect(
            url_for("individual_match.proposal_detail", proposal_id=proposal_id)
        )

    if request.is_json:
        return jsonify({"success": True})

    flash(_("Proposta cancellata."), "success")
    return redirect(url_for("individual_match.proposal_list"))


@individual_match_bp.route("/proposals/<int:proposal_id>/decline", methods=["POST"])
@RoleRequirement.player_or_director_required
def decline_proposal(proposal_id):
    """Decline a direct match proposal invitation."""
    try:
        # NB: reject_proposal(proposal_id, user_id) — gestisce sia il rifiuto di
        # un invito pendente sia la "dis-accettazione". (Era erroneamente
        # MatchProposalService.reject_invitation, inesistente → 500.)
        MatchProposalService.reject_proposal(proposal_id, current_user.id)

        if request.is_json:
            return jsonify({"success": True, "message": "Proposta rifiutata"})
        else:
            flash(_("Proposta rifiutata."), "info")
            return redirect(url_for("individual_match.proposal_list"))

    except Exception as e:
        if request.is_json:
            return safe_json_error(e, "declining proposal")
        else:
            flash(_("Errore interno del server"), "danger")
            return redirect(
                url_for("individual_match.proposal_detail", proposal_id=proposal_id)
            )
