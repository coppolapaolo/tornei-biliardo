# routes/player/profile.py
"""User profile, privacy settings, and account management routes."""

import csv
import io
from typing import cast

from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user, logout_user
from flask_babel import _
from werkzeug.exceptions import abort

from models import db, Gara, Inscription, Match, User
from models.status_enum import MatchStatus
from models.campionato.models import Campionato
from models.user.services import UserDeletionService, UserService
from models.user.permission_service import UserPermissionService
from utils import player_only

from . import player_bp


# ============ PROFILO UTENTE E GESTIONE ACCOUNT ============


@player_bp.route("/profile")
@login_required
@player_only
def profile():
    """Profilo personale del giocatore"""
    from models.classification.models import Classification

    # Iscrizioni dell'utente (incluse gare standalone)
    inscriptions = (
        Inscription.query.filter_by(user_id=current_user.id)
        .join(Gara)
        .outerjoin(Campionato)  # LEFT JOIN per includere gare standalone
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Partite giocate (incluse gare standalone)
    matches = (
        Match.query.filter(
            db.or_(
                Match.player1_id == current_user.id, Match.player2_id == current_user.id
            )
        )
        .join(Gara)
        .outerjoin(Campionato)  # LEFT JOIN per includere gare standalone
        .order_by(
            Campionato.created_at.desc().nullslast(),
            Gara.date.desc(),
            Match.round_number.desc(),
        )
        .all()
    )

    # Statistiche generali
    total_matches = len([m for m in matches if m.status == MatchStatus.COMPLETED.value])
    won_matches = len(
        [
            m
            for m in matches
            if m.status == MatchStatus.COMPLETED.value
            and m.winner_id == current_user.id
        ]
    )
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Classifiche per campionato
    classifications = (
        Classification.query.filter_by(user_id=current_user.id)
        .join(Campionato)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    # Partite recenti (ultime 10)
    recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
        :10
    ]

    # Conta solo i campionati con gare completate dove l'utente ha partecipato
    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in inscriptions
            if insc.gara.campionato_id is not None and insc.gara.status == "completed"
        ]
    )

    # Conta solo le gare completate
    completed_provas = len(
        [insc for insc in inscriptions if insc.gara.status == "completed"]
    )

    # Challenge statistics
    challenge_stats = None
    challenge_history = []
    try:
        from models.challenge import GaraChallengeAttempt, GaraChallenge, Challenge

        # Get all challenge attempts by this user
        user_attempts = (
            GaraChallengeAttempt.query.filter_by(
                user_id=current_user.id, completed=True
            )
            .join(GaraChallenge)
            .join(Challenge)
            .order_by(
                GaraChallengeAttempt.attempted_at.desc()  # type: ignore[attr-defined]
            )
            .all()
        )

        if user_attempts:
            # Calculate overall challenge statistics
            total_attempts = len(user_attempts)
            unique_challenges = len(
                set(attempt.gara_challenge.challenge_id for attempt in user_attempts)
            )
            unique_garas = len(
                set(attempt.gara_challenge.gara_id for attempt in user_attempts)
            )

            # Calculate average score (only for numeric challenges)
            numeric_attempts = [
                attempt
                for attempt in user_attempts
                if attempt.score is not None
                and not attempt.gara_challenge.challenge.pass_fail_only
            ]
            avg_score = (
                sum(attempt.score for attempt in numeric_attempts)
                / len(numeric_attempts)
                if numeric_attempts
                else 0
            )

            # Calculate pass rate (for pass/fail challenges)
            pass_fail_attempts = [
                attempt
                for attempt in user_attempts
                if attempt.gara_challenge.challenge.pass_fail_only
            ]
            pass_rate = (
                (
                    sum(1 for attempt in pass_fail_attempts if attempt.passed)
                    / len(pass_fail_attempts)
                    * 100
                )
                if pass_fail_attempts
                else 0
            )

            challenge_stats = {
                "total_attempts": total_attempts,
                "unique_challenges": unique_challenges,
                "unique_garas": unique_garas,
                "avg_score": round(avg_score, 1),
                "pass_rate": round(pass_rate, 1),
            }

            # Build challenge history (last 20 attempts)
            for attempt in user_attempts[:20]:
                challenge_history.append(
                    {
                        "challenge_name": (
                            attempt.gara_challenge.challenge.get_display_name()
                        ),
                        "gara_name": attempt.gara_challenge.gara.name,
                        "score": attempt.score,
                        "passed": attempt.passed,
                        "attempted_at": attempt.attempted_at,
                        "is_pass_fail": attempt.gara_challenge.challenge.pass_fail_only,
                        "max_score": attempt.gara_challenge.challenge.max_score,
                    }
                )

    except Exception:
        # If challenge module is not available or there's an error, just skip
        pass

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(completed_tournaments),
        "provas_played": completed_provas,
    }

    # Privacy context for template consistency (own profile always has full access)
    from models.user.privacy_service import PrivacyService

    privacy = PrivacyService.get_privacy_settings(current_user.id)

    return render_template(
        "player/profile.html",
        user=current_user,
        inscriptions=inscriptions,
        matches=recent_matches,
        classifications=classifications,
        stats=stats,
        challenge_stats=challenge_stats,
        challenge_history=challenge_history,
        # Privacy context for template
        privacy=privacy,
        is_admin=current_user.is_admin,
        is_own_profile=True,
    )


@player_bp.route("/profile/<int:user_id>")
def view_profile(user_id):
    """View another player's public profile with privacy controls."""
    from models.user.models import User
    from models.competition.models import Gara, Inscription
    from models.match.models import Match
    from models.status_enum import MatchStatus
    from models.campionato.models import Campionato
    from models.challenge.models import Challenge, ChallengeAttempt
    from models.user.privacy_service import PrivacyService

    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    # Privacy context
    viewer_id = current_user.id if current_user.is_authenticated else None
    is_admin = current_user.is_authenticated and current_user.is_admin
    is_own_profile = viewer_id == user_id

    # Get privacy settings
    privacy = PrivacyService.get_privacy_settings(user_id)

    # Inscriptions (always loaded for statistics)
    inscriptions = (
        Inscription.query.filter_by(user_id=user.id)
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Matches played
    all_matches = (
        Match.query.filter(
            db.or_(Match.player1_id == user.id, Match.player2_id == user.id)
        )
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(
            Campionato.created_at.desc().nullslast(),
            Gara.date.desc(),
            Match.round_number.desc(),
        )
        .all()
    )

    # Filter matches based on privacy (hidden matches)
    matches = PrivacyService.filter_visible_matches(
        user_id=user_id,
        viewer_id=viewer_id,
        matches=all_matches,
        is_admin=is_admin,
    )

    # Public statistics (calculated from visible matches only for non-owners)
    completed_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value]
    total_matches = len(completed_matches)
    won_matches = len([m for m in completed_matches if m.winner_id == user.id])
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Recent matches (last 10 visible)
    recent_matches = completed_matches[:10]

    # Completed tournaments count
    visible_inscriptions = PrivacyService.filter_visible_inscriptions(
        user_id=user_id,
        viewer_id=viewer_id,
        inscriptions=inscriptions,
        is_admin=is_admin,
    )

    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in visible_inscriptions
            if insc.gara.campionato_id is not None and insc.gara.status == "completed"
        ]
    )

    completed_provas = len(
        [insc for insc in visible_inscriptions if insc.gara.status == "completed"]
    )

    stats = {
        "total_inscriptions": len(visible_inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(completed_tournaments),
        "provas_played": completed_provas,
    }

    # Challenge data
    challenge_attempts = (
        ChallengeAttempt.query.filter_by(user_id=user.id, completed=True)
        .join(Challenge)
        .order_by(ChallengeAttempt.created_at.desc())
        .all()
    )

    challenge_stats = None
    if challenge_attempts:
        total_attempts = len(challenge_attempts)
        unique_challenges = len(
            set(attempt.challenge_id for attempt in challenge_attempts)
        )
        avg_score = (
            sum(attempt.score for attempt in challenge_attempts) / total_attempts
        )
        pass_count = sum(1 for attempt in challenge_attempts if attempt.passed)
        pass_rate = (pass_count / total_attempts * 100) if total_attempts > 0 else 0

        challenge_stats = {
            "total_attempts": total_attempts,
            "unique_challenges": unique_challenges,
            "avg_score": round(avg_score, 1),
            "pass_rate": round(pass_rate, 1),
        }

    return render_template(
        "player/profile.html",
        user=user,
        inscriptions=visible_inscriptions,
        matches=recent_matches,
        stats=stats,
        challenge_stats=challenge_stats,
        challenge_history=challenge_attempts,
        classifications=[],
        # Privacy context for template
        privacy=privacy,
        is_admin=is_admin,
        is_own_profile=is_own_profile,
    )


@player_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@player_only
def edit_profile():
    """Modifica email e telefono dell'utente corrente."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None

        try:
            UserService.update_user(current_user.id, email=email, phone=phone)
            flash("Informazioni aggiornate correttamente.", "success")
            return redirect(url_for("player.profile"))
        except ValueError as e:
            flash(str(e), "error")
        except Exception:
            flash("Si è verificato un errore durante l'aggiornamento.", "error")

    # GET o POST fallito → ripresenta il form
    return render_template("player/profile_edit.html", user=current_user)


@player_bp.route("/profile/change_password", methods=["POST"])
@login_required
@player_only
def change_password():
    """Cambia la password dell'utente corrente."""
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if new != confirm:
        flash("La nuova password e la conferma non coincidono.", "error")
        return redirect(url_for("player.profile"))

    ok = UserService.change_password(current_user.id, current, new)
    if ok:
        flash("Password aggiornata correttamente.", "success")
    else:
        flash("Password attuale errata o nuova password non valida.", "error")

    return redirect(url_for("player.profile"))


@player_bp.route("/request_director", methods=["POST"])
@login_required
@player_only
def request_director():
    """Richiede la promozione a direttore di gara"""
    try:
        UserPermissionService.request_director_promotion(user_id=current_user.id)

        # Notification sent via event system (DirectorRequestCreatedEvent)
        flash("Richiesta inviata. Sarai contattato dall'amministratore.")

    except ValueError as e:
        flash(f"Errore: {str(e)}", "error")
    except Exception as e:
        flash(f"Errore inaspettato: {str(e)}", "error")

    return redirect(url_for("player.profile"))


# ============ PRIVACY SETTINGS ============


@player_bp.route("/privacy-settings", methods=["GET", "POST"])
@login_required
@player_only
def privacy_settings():
    """Gestione impostazioni privacy del profilo."""
    from models.user.privacy_service import PrivacyService

    if request.method == "POST":
        PrivacyService.update_privacy_settings(
            user_id=current_user.id,
            show_email="show_email" in request.form,
            show_phone="show_phone" in request.form,
            show_statistics="show_statistics" in request.form,
            show_recent_matches="show_recent_matches" in request.form,
            show_classifications="show_classifications" in request.form,
            show_challenge_stats="show_challenge_stats" in request.form,
        )
        flash(_("Impostazioni privacy aggiornate con successo."), "success")
        return redirect(url_for("player.privacy_settings"))

    settings = PrivacyService.get_privacy_settings(current_user.id)
    return render_template("player/privacy_settings.html", settings=settings)


# ========== Hide/Show AJAX Routes ==========


@player_bp.route("/hide/match/<int:match_id>", methods=["POST"])
@login_required
@player_only
def hide_match(match_id):
    """Hide a match from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_match(current_user.id, match_id)
        return jsonify({"success": True, "message": _("Match nascosto")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/match/<int:match_id>", methods=["POST"])
@login_required
@player_only
def show_match(match_id):
    """Show a previously hidden match (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_match(current_user.id, match_id):
        return jsonify({"success": True, "message": _("Match visibile")})
    return jsonify({"success": False, "error": _("Match non era nascosto")}), 400


@player_bp.route("/hide/inscription/<int:inscription_id>", methods=["POST"])
@login_required
@player_only
def hide_inscription(inscription_id):
    """Hide an inscription from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_inscription(current_user.id, inscription_id)
        return jsonify({"success": True, "message": _("Gara nascosta")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/inscription/<int:inscription_id>", methods=["POST"])
@login_required
@player_only
def show_inscription(inscription_id):
    """Show a previously hidden inscription (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_inscription(current_user.id, inscription_id):
        return jsonify({"success": True, "message": _("Gara visibile")})
    return jsonify({"success": False, "error": _("Gara non era nascosta")}), 400


@player_bp.route("/hide/campionato/<int:campionato_id>", methods=["POST"])
@login_required
@player_only
def hide_campionato(campionato_id):
    """Hide a campionato from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_campionato(current_user.id, campionato_id)
        return jsonify({"success": True, "message": _("Campionato nascosto")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/campionato/<int:campionato_id>", methods=["POST"])
@login_required
@player_only
def show_campionato(campionato_id):
    """Show a previously hidden campionato (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_campionato(current_user.id, campionato_id):
        return jsonify({"success": True, "message": _("Campionato visibile")})
    return jsonify({"success": False, "error": _("Campionato non era nascosto")}), 400


# ============ ACCOUNT DELETION ============


@player_bp.route("/delete_account", methods=["GET", "POST"])
@login_required
@player_only
def delete_account():
    """Cancellazione account utente (self-service).
    Conserva lo storico tramite soft delete."""
    if request.method == "GET":
        return render_template("player/delete_account.html")

    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "").strip()

    # Verifica password
    if not current_user.check_password(password):
        flash("Password errata!", "danger")
        return render_template("player/delete_account.html")

    # Verifica conferma
    if confirmation != "ELIMINA IL MIO ACCOUNT":
        flash("Conferma non corretta!", "warning")
        return render_template("player/delete_account.html")

    try:
        # Ensure current_user is properly typed as User
        user_to_delete = db.session.get(User, current_user.id)
        if not user_to_delete:
            flash("Errore: utente non trovato.", "danger")
            return render_template("player/delete_account.html")

        UserDeletionService.delete_user(user_to_delete)
        logout_user()  # Disconnette l'utente dopo la cancellazione
        flash(
            "Account eliminato. I tuoi dati restano anonimizzati nei registri.",
            "success",
        )
        return redirect(url_for("main.index"))
    except Exception:
        db.session.rollback()
        flash("Errore durante l'eliminazione dell'account.", "danger")
        raise


# ============ PROFILE EXPORT ============


@player_bp.route("/profile/<int:user_id>/export/csv")
@login_required
def export_profile_csv(user_id):
    """Export player profile and match history to CSV"""
    # Check permissions - can only export own profile
    user = cast(User, current_user)
    if user.id != user_id:
        abort(403)

    target_user = db.session.get(User, user_id)
    if not target_user:
        abort(404)

    # Get all completed matches for the user
    matches = Match.query.filter(
        (Match.player1_id == user_id) | (Match.player2_id == user_id),
        Match.status == MatchStatus.COMPLETED.value,
    ).all()

    # Get challenge attempts
    from models.challenge.models import ChallengeAttempt

    challenges = ChallengeAttempt.query.filter_by(user_id=user_id, completed=True).all()

    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(
        [
            "tipo",
            "data",
            "competizione",
            "avversario",
            "risultato",
            "punteggio",
            "turno",
            "challenge",
            "valore",
            "superato",
        ]
    )

    # Write match data
    for match in matches:
        opponent = ""
        result = ""
        if match.player1_id == user_id:
            opponent = match.player2.username if match.player2 else "Bye"
            result = "Win" if match.winner_id == user_id else "Loss"
        else:
            opponent = match.player1.username
            result = "Win" if match.winner_id == user_id else "Loss"

        competition_name = ""
        if match.gara.campionato:
            competition_name = (
                f"{match.gara.campionato.name} - Gara {match.gara.number}"
            )
        else:
            competition_name = match.gara.name

        writer.writerow(
            [
                "Tournament Match",
                match.gara.date.strftime("%Y-%m-%d") if match.gara.date else "",
                competition_name,
                opponent,
                result,
                f"{match.player1_score}-{match.player2_score}",
                match.round_number,
                "",
                "",
                "",
            ]
        )

    # Write challenge data
    for attempt in challenges:
        challenge_name = ""
        if hasattr(attempt, "challenge") and attempt.challenge:
            challenge_name = attempt.challenge.description
        elif hasattr(attempt, "gara_challenge") and attempt.gara_challenge:
            challenge_name = attempt.gara_challenge.challenge.description

        writer.writerow(
            [
                "Challenge",
                attempt.created_at.strftime("%Y-%m-%d") if attempt.created_at else "",
                "",
                "",
                "",
                "",
                "",
                challenge_name,
                attempt.score,
                "Yes" if attempt.passed else "No",
            ]
        )

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=player_{target_user.username}_history.csv"
            )
        },
    )
