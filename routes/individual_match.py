"""
Module: routes/individual_match.py
Purpose: Individual Match domain HTTP routes for player-to-player match proposals
Requirements: Individual match proposals between players with scheduling and
    result tracking
"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_login import current_user
from datetime import datetime, timedelta

from models import (
    IndividualMatch,
)
from utils import (
    admin_required,
)
from models.individual_match.services import (
    IndividualMatchService,
    MatchProposalService,
)
from models.individual_match.models import MatchProposal
from models.user.permissions import RoleRequirement


# Blueprint initialization
individual_match_bp = Blueprint("individual_match", __name__)


@individual_match_bp.route("/")
@RoleRequirement.player_or_director_required
def dashboard():
    """Individual match dashboard for current user."""
    try:
        user_data = IndividualMatchService.get_user_dashboard_data(current_user.id)
        return render_template("individual_match/dashboard.html", **user_data)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


@individual_match_bp.route("/proposals")
@RoleRequirement.player_or_director_required
def proposal_list():
    """List match proposals for current user."""
    try:
        proposals_data = MatchProposalService.get_user_proposals(current_user.id)
        return render_template("individual_match/proposals.html", **proposals_data)
    except Exception as e:
        flash(f"Error loading proposals: {str(e)}", "danger")
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
            flash("Access denied to this proposal.", "danger")
            return redirect(url_for("individual_match.proposal_list"))

        return render_template(
            "individual_match/proposal_detail.html", proposal=proposal
        )
    except Exception as e:
        flash(f"Error loading proposal: {str(e)}", "danger")
        return redirect(url_for("individual_match.proposal_list"))


@individual_match_bp.route("/proposals/create", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def create_proposal():
    """Create new match proposal."""
    if request.method == "GET":
        return render_template("individual_match/create_proposal.html")

    try:
        data = request.get_json() if request.is_json else request.form

        # Parse scheduled time
        scheduled_at = datetime.fromisoformat(
            data["scheduled_at"].replace("Z", "+00:00")
        )

        # Calculate expiration (default 24 hours before match)
        expires_at = scheduled_at - timedelta(hours=int(data.get("expires_hours", 24)))

        proposal_data = {
            "proposer_id": current_user.id,
            "proposal_type": data["proposal_type"],
            "location": data["location"],
            "scheduled_at": scheduled_at,
            "expires_at": expires_at,
            "discipline": data.get("discipline", "palla_8"),
            "distance": int(data.get("distance", 5)),
            "best_of": data.get("best_of", "true").lower() == "true",
            "break_rule": data.get("break_rule", "alternate"),
            "description": data.get("description"),
            "entry_fee": float(data["entry_fee"]) if data.get("entry_fee") else None,
            "invited_user_ids": (
                data.getlist("invited_user_ids") if data.get("invited_user_ids") else []
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
            flash("Match proposal created successfully!", "success")
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
            flash("Proposal accepted successfully!", "success")
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
            flash("Proposal cancelled successfully!", "success")
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


@individual_match_bp.route("/matches")
@RoleRequirement.player_or_director_required
def match_list():
    """List individual matches for current user."""
    try:
        matches = IndividualMatchService.get_user_matches(current_user.id)
        return render_template("individual_match/matches.html", matches=matches)
    except Exception as e:
        flash(f"Error loading matches: {str(e)}", "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.route("/matches/<int:match_id>")
@RoleRequirement.player_or_director_required
def match_detail(match_id):
    """View individual match details and submit results."""
    try:
        match = IndividualMatch.query.get_or_404(match_id)

        # Verify user is part of this match
        if current_user.id not in (match.player1_id, match.player2_id):
            flash("Access denied to this match.", "danger")
            return redirect(url_for("individual_match.match_list"))

        return render_template("individual_match/match_detail.html", match=match)

    except Exception as e:
        flash(f"Error loading match: {str(e)}", "danger")
        return redirect(url_for("individual_match.match_list"))


@individual_match_bp.route("/matches/<int:match_id>/start", methods=["POST"])
@RoleRequirement.player_or_director_required
def start_match(match_id):
    """Start an individual match."""
    try:
        IndividualMatchService.start_match(match_id, current_user.id)

        if request.is_json:
            return jsonify({"success": True, "message": "Match started successfully"})
        else:
            flash("Match started successfully!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Error starting match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/racks/add", methods=["POST"])
@RoleRequirement.player_or_director_required
def add_rack(match_id):
    """Add a rack for a player (new simplified UX)."""
    try:
        data = request.get_json() if request.is_json else request.form

        rack = IndividualMatchService.add_rack_for_player(
            match_id=match_id,
            user_id=current_user.id,
            winner_id=int(data["winner_id"]),
        )

        if request.is_json:
            match = IndividualMatch.query.get(match_id)
            return jsonify(
                {
                    "success": True,
                    "rack_number": rack.rack_number,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "is_ready_for_validation": match.is_ready_for_validation(),
                }
            )
        else:
            flash("Rack aggiunto!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/racks/remove", methods=["POST"])
@RoleRequirement.player_or_director_required
def remove_rack(match_id):
    """Remove last rack for a player (new simplified UX)."""
    try:
        data = request.get_json() if request.is_json else request.form

        IndividualMatchService.remove_rack_for_player(
            match_id=match_id,
            user_id=current_user.id,
            player_id=int(data["player_id"]),
        )

        if request.is_json:
            match = IndividualMatch.query.get(match_id)
            return jsonify(
                {
                    "success": True,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "is_ready_for_validation": match.is_ready_for_validation(),
                }
            )
        else:
            flash("Rack rimosso!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/confirm", methods=["POST"])
@RoleRequirement.player_or_director_required
def confirm_result(match_id):
    """Confirm match result (new simplified UX)."""
    try:
        match = IndividualMatchService.confirm_match_result(
            match_id=match_id, user_id=current_user.id
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "completed": match.status.value == "completed",
                    "player1_confirmed": match.player1_confirmed,
                    "player2_confirmed": match.player2_confirmed,
                    "message": (
                        "Match completato!"
                        if match.status.value == "completed"
                        else "Risultato confermato!"
                    ),
                }
            )
        else:
            if match.status.value == "completed":
                flash("Match completato con successo!", "success")
            else:
                flash("Risultato confermato! In attesa dell'altro giocatore.", "info")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/reject", methods=["POST"])
@RoleRequirement.player_or_director_required
def reject_result(match_id):
    """Reject match result - removes last rack (new simplified UX)."""
    try:
        match = IndividualMatchService.reject_match_result(
            match_id=match_id, user_id=current_user.id
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "message": "Ultimo rack rimosso. Continua a giocare.",
                }
            )
        else:
            flash("Risultato rifiutato. Ultimo rack rimosso.", "warning")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/complete", methods=["POST"])
@RoleRequirement.player_or_director_required
def complete_match(match_id):
    """Complete an individual match - legacy route for backward compatibility."""
    try:
        data = request.get_json() if request.is_json else request.form

        match = IndividualMatchService.complete_match(
            match_id=match_id,
            user_id=current_user.id,
            winner_id=int(data["winner_id"]),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "winner_id": match.winner_id,
                    "final_score": f"{match.player1_score}-{match.player2_score}",
                    "message": "Match completed successfully",
                }
            )
        else:
            flash("Match completed successfully!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Error completing match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/cancel", methods=["POST"])
@RoleRequirement.player_or_director_required
def cancel_match(match_id):
    """Cancel an individual match."""
    try:
        IndividualMatchService.cancel_match(match_id, current_user.id)

        if request.is_json:
            return jsonify({"success": True, "message": "Match cancelled successfully"})
        else:
            flash("Match cancelled successfully!", "success")
            return redirect(url_for("individual_match.match_list"))

    except ValueError as e:
        error_msg = f"Error cancelling match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/availability", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def manage_availability():
    """Manage player availability for match proposals."""
    if request.method == "GET":
        availability_data = IndividualMatchService.get_user_availability(
            current_user.id
        )
        return render_template(
            "individual_match/availability.html", **availability_data
        )

    try:
        data = request.get_json() if request.is_json else request.form

        availability_data = data.get("availability", [])
        if not isinstance(availability_data, list):
            raise ValueError("Availability data must be a list")

        IndividualMatchService.update_user_availability(
            user_id=current_user.id, availability_data=availability_data
        )

        if request.is_json:
            return jsonify(
                {"success": True, "message": "Availability updated successfully"}
            )
        else:
            flash("Availability updated successfully!", "success")
            return redirect(url_for("individual_match.manage_availability"))

    except ValueError as e:
        error_msg = f"Error updating availability: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template("individual_match/availability.html")


@individual_match_bp.route("/statistics")
@RoleRequirement.player_or_director_required
def user_statistics():
    """View user's individual match statistics."""
    try:
        stats = IndividualMatchService.get_user_statistics(current_user.id)

        if request.is_json:
            return jsonify({"success": True, "statistics": stats})
        else:
            return render_template("individual_match/statistics.html", statistics=stats)

    except Exception as e:
        error_msg = f"Error loading statistics: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.dashboard"))


# Admin routes
@individual_match_bp.route("/admin/overview")
@admin_required
def admin_overview():
    """Admin overview of all individual matches."""
    try:
        overview_data = IndividualMatchService.get_admin_overview()
        return render_template("individual_match/admin_overview.html", **overview_data)
    except Exception as e:
        flash(f"Error loading admin overview: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


# Error handlers
@individual_match_bp.errorhandler(404)
def individual_match_not_found(error):
    """Handle 404 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Resource not found"}), 404
    else:
        flash("Resource not found.", "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.errorhandler(403)
def individual_match_access_denied(error):
    """Handle 403 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash("Access denied.", "danger")
        return redirect(url_for("individual_match.dashboard"))
