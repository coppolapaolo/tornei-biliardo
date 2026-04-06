"""Player playoff routes — confirm/decline playoff qualification."""

from flask import render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from flask_babel import _

from models.base import db
from models.playoff.models import PlayoffQualification, QualificationStatus
from . import player_bp


@player_bp.route("/playoff/invitation/<int:qualification_id>")
@login_required
def playoff_invitation(qualification_id):
    """View playoff qualification invitation."""
    qual = db.session.get(PlayoffQualification, qualification_id)
    if not qual or qual.user_id != current_user.id:
        abort(404)

    return render_template(
        "player/playoff_invitation.html",
        qualification=qual,
        config=qual.configuration,
        campionato=qual.configuration.campionato,
    )


@player_bp.route("/playoff/confirm/<int:qualification_id>", methods=["POST"])
@login_required
def playoff_confirm(qualification_id):
    """Confirm playoff participation."""
    from models.playoff.services import PlayoffService

    qual = db.session.get(PlayoffQualification, qualification_id)
    if not qual or qual.user_id != current_user.id:
        abort(404)

    if qual.status != QualificationStatus.PENDING:
        flash(_("Questa qualificazione non è più in attesa di risposta."), "info")
        return redirect(url_for("player.playoff_invitation", qualification_id=qualification_id))

    try:
        PlayoffService.confirm_qualification(qualification_id, current_user.id)
        flash(_("Partecipazione ai playoff confermata!"), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("player.playoff_invitation", qualification_id=qualification_id))


@player_bp.route("/playoff/decline/<int:qualification_id>", methods=["POST"])
@login_required
def playoff_decline(qualification_id):
    """Decline playoff participation."""
    from models.playoff.services import PlayoffService

    qual = db.session.get(PlayoffQualification, qualification_id)
    if not qual or qual.user_id != current_user.id:
        abort(404)

    if qual.status != QualificationStatus.PENDING:
        flash(_("Questa qualificazione non è più in attesa di risposta."), "info")
        return redirect(url_for("player.playoff_invitation", qualification_id=qualification_id))

    try:
        PlayoffService.decline_qualification(qualification_id, current_user.id)
        flash(_("Hai rifiutato la partecipazione ai playoff."), "info")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("dashboard.dashboard"))
