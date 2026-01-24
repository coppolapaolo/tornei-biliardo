# routes/player/profile.py
"""User profile, privacy settings, and account management routes."""

import csv
import io
import json
import os
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, cast

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
    current_app,
    send_file,
)
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


# ============ GDPR EXPORT ============

# Directory for temporary export files
GDPR_EXPORT_DIR = "instance/gdpr_exports"
GDPR_EXPORT_MAX_AGE_HOURS = 24


def _get_export_dir() -> Path:
    """Get the GDPR export directory, creating it if needed."""
    export_path = Path(current_app.instance_path) / "gdpr_exports"
    export_path.mkdir(parents=True, exist_ok=True)
    return export_path


def _cleanup_old_exports(export_dir: Path) -> None:
    """Remove export files older than GDPR_EXPORT_MAX_AGE_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=GDPR_EXPORT_MAX_AGE_HOURS)
    for file in export_dir.glob("*.zip"):
        try:
            # Extract timestamp from filename: {user_id}_{timestamp}.zip
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if mtime < cutoff:
                file.unlink()
        except (ValueError, OSError):
            pass


def _collect_user_data(user_id: int) -> Dict[str, Any]:
    """Collect all user data for GDPR export."""
    from models.user.models import User
    from models.competition.models import Inscription
    from models.match.models import Match
    from models.classification.models import Classification
    from models.challenge.models import ChallengeAttempt
    from models.gamification.models import (
        UserLevel,
        UserAchievement,
        StreakTracker,
        XPTransaction,
    )
    from models.user.privacy_service import PrivacyService

    user = db.session.get(User, user_id)
    if not user:
        return {}

    def serialize_date(obj: Any) -> Any:
        """JSON serializer for dates."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)

    # 1. Account data
    account_data = {
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "fargo_rating": user.fargo_rating,
        "elo_rating": user.elo_rating,
        "created_at": serialize_date(user.created_at) if user.created_at else None,
    }

    # 2. Privacy settings
    privacy = PrivacyService.get_privacy_settings(user_id)
    privacy_data = {
        "show_email": privacy.show_email,
        "show_phone": privacy.show_phone,
        "show_statistics": privacy.show_statistics,
        "show_recent_matches": privacy.show_recent_matches,
        "show_classifications": privacy.show_classifications,
        "show_challenge_stats": privacy.show_challenge_stats,
    }

    # 3. Inscriptions
    inscriptions = Inscription.query.filter_by(user_id=user_id).all()
    inscriptions_data = [
        {
            "gara_id": insc.gara_id,
            "gara_name": insc.gara.name if insc.gara else None,
            "campionato_name": (
                insc.gara.campionato.name
                if insc.gara and insc.gara.campionato
                else None
            ),
            "date": serialize_date(insc.gara.date) if insc.gara and insc.gara.date else None,
            "is_withdrawn": insc.is_withdrawn,
            "is_waitlist": insc.is_waitlist,
            "created_at": serialize_date(insc.created_at) if insc.created_at else None,
        }
        for insc in inscriptions
    ]

    # 4. Matches
    matches = Match.query.filter(
        db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
    ).all()
    matches_data = [
        {
            "match_id": match.id,
            "gara_name": match.gara.name if match.gara else None,
            "campionato_name": (
                match.gara.campionato.name
                if match.gara and match.gara.campionato
                else None
            ),
            "date": serialize_date(match.gara.date) if match.gara and match.gara.date else None,
            "opponent": (
                match.player2.username
                if match.player1_id == user_id and match.player2
                else (match.player1.username if match.player1 else None)
            ),
            "my_score": (
                match.player1_score if match.player1_id == user_id else match.player2_score
            ),
            "opponent_score": (
                match.player2_score if match.player1_id == user_id else match.player1_score
            ),
            "result": (
                "win" if match.winner_id == user_id else "loss" if match.winner_id else "pending"
            ),
            "round_number": match.round_number,
            "status": match.status,
        }
        for match in matches
    ]

    # 5. Classifications
    classifications = Classification.query.filter_by(user_id=user_id).all()
    classifications_data = [
        {
            "campionato_name": (
                classif.campionato.name if classif.campionato else None
            ),
            "position": classif.position,
            "points": classif.points,
            "wins": classif.wins,
            "losses": classif.losses,
        }
        for classif in classifications
    ]

    # 6. Challenge attempts
    challenge_attempts = ChallengeAttempt.query.filter_by(
        user_id=user_id, completed=True
    ).all()
    challenges_data = [
        {
            "challenge_name": (
                attempt.challenge.description if attempt.challenge else None
            ),
            "score": attempt.score,
            "passed": attempt.passed,
            "attempted_at": serialize_date(attempt.created_at) if attempt.created_at else None,
        }
        for attempt in challenge_attempts
    ]

    # 7. Gamification - Level & XP
    user_level = db.session.get(UserLevel, user_id)
    gamification_data: Dict[str, Any] = {
        "level": {
            "current_level": user_level.current_level if user_level else 1,
            "total_xp": user_level.total_xp if user_level else 0,
            "current_xp": user_level.current_xp if user_level else 0,
        },
        "achievements": [],
        "streaks": [],
        "xp_transactions": [],
    }

    # Achievements
    achievements = UserAchievement.query.filter_by(
        user_id=user_id, is_unlocked=True
    ).all()
    gamification_data["achievements"] = [
        {
            "achievement_slug": ach.achievement.slug if ach.achievement else None,
            "achievement_name": ach.achievement.name if ach.achievement else None,
            "unlocked_at": serialize_date(ach.unlocked_at) if ach.unlocked_at else None,
        }
        for ach in achievements
    ]

    # Streaks
    streaks = StreakTracker.query.filter_by(user_id=user_id).all()
    gamification_data["streaks"] = [
        {
            "streak_type": streak.streak_type.value if streak.streak_type else None,
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "freeze_count": streak.freeze_count,
        }
        for streak in streaks
    ]

    # XP Transactions (last 100)
    xp_transactions = (
        XPTransaction.query.filter_by(user_id=user_id)
        .order_by(XPTransaction.created_at.desc())
        .limit(100)
        .all()
    )
    gamification_data["xp_transactions"] = [
        {
            "transaction_type": tx.transaction_type.value if tx.transaction_type else None,
            "xp_amount": tx.xp_amount,
            "reason": tx.reason,
            "level_before": tx.level_before,
            "level_after": tx.level_after,
            "created_at": serialize_date(tx.created_at) if tx.created_at else None,
        }
        for tx in xp_transactions
    ]

    return {
        "export_date": serialize_date(datetime.utcnow()),
        "export_version": "1.0",
        "account": account_data,
        "privacy_settings": privacy_data,
        "inscriptions": inscriptions_data,
        "matches": matches_data,
        "classifications": classifications_data,
        "challenges": challenges_data,
        "gamification": gamification_data,
    }


def _generate_gdpr_export(app, user_id: int, username: str) -> None:
    """Background task to generate GDPR export."""
    with app.app_context():
        try:
            # Collect data
            data = _collect_user_data(user_id)

            # Create export directory
            export_dir = Path(app.instance_path) / "gdpr_exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            # Cleanup old exports
            _cleanup_old_exports(export_dir)

            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{user_id}_{timestamp}.zip"
            filepath = export_dir / filename

            # Create ZIP with JSON
            json_content = json.dumps(data, ensure_ascii=False, indent=2)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    f"{username}_gdpr_export_{timestamp}.json",
                    json_content.encode("utf-8"),
                )

            # Send notification
            from models.notification.services import NotificationService
            from models.notification.models import NotificationType, NotificationPriority

            NotificationService.create_notification(
                user_id=user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=_("Export GDPR Pronto"),
                message=_("Il tuo archivio dati è pronto per il download. Il link scadrà tra 24 ore."),
                priority=NotificationPriority.NORMAL,
                action_url=f"/player/gdpr-export/download/{filename}",
                action_text=_("Scarica"),
            )

            # Emit SSE event for real-time notification
            from routes.sse import emit_user_event

            emit_user_event(
                user_id,
                "gdpr_export_ready",
                {"filename": filename, "download_url": f"/player/gdpr-export/download/{filename}"},
            )

        except Exception as e:
            # Log error and notify user of failure
            current_app.logger.error(f"GDPR export failed for user {user_id}: {e}")
            try:
                from models.notification.services import NotificationService
                from models.notification.models import NotificationType, NotificationPriority

                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.ACCOUNT_UPDATE,
                    title=_("Errore Export GDPR"),
                    message=_("Si è verificato un errore durante la generazione dell'archivio. Riprova più tardi."),
                    priority=NotificationPriority.HIGH,
                )
            except Exception:
                pass


@player_bp.route("/gdpr-export/request", methods=["POST"])
@login_required
@player_only
def request_gdpr_export():
    """Request a GDPR data export (runs in background)."""
    user = cast(User, current_user)

    # Check if there's already a recent export pending
    export_dir = _get_export_dir()
    for file in export_dir.glob(f"{user.id}_*.zip"):
        # If export created in last 5 minutes, don't allow another
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if datetime.utcnow() - mtime < timedelta(minutes=5):
            flash(
                _("Un export è già in corso o è stato generato di recente. Controlla le notifiche."),
                "warning",
            )
            return redirect(url_for("player.privacy_settings"))

    # Start background export
    app = current_app._get_current_object()  # Get actual app object for thread
    thread = threading.Thread(
        target=_generate_gdpr_export,
        args=(app, user.id, user.username),
        daemon=True,
    )
    thread.start()

    flash(
        _("Export avviato. Riceverai una notifica quando sarà pronto per il download."),
        "info",
    )
    return redirect(url_for("player.privacy_settings"))


@player_bp.route("/gdpr-export/download/<filename>")
@login_required
@player_only
def download_gdpr_export(filename: str):
    """Download a GDPR export file."""
    user = cast(User, current_user)

    # Security: ensure filename belongs to current user
    if not filename.startswith(f"{user.id}_"):
        abort(403)

    # Validate filename format to prevent path traversal
    if not filename.endswith(".zip") or "/" in filename or "\\" in filename:
        abort(400)

    export_dir = _get_export_dir()
    filepath = export_dir / filename

    if not filepath.exists():
        flash(_("Il file di export non esiste o è scaduto."), "warning")
        return redirect(url_for("player.privacy_settings"))

    # Check if file is expired
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    if datetime.utcnow() - mtime > timedelta(hours=GDPR_EXPORT_MAX_AGE_HOURS):
        filepath.unlink()  # Delete expired file
        flash(_("Il file di export è scaduto. Richiedi un nuovo export."), "warning")
        return redirect(url_for("player.privacy_settings"))

    # Cleanup old exports while we're here
    _cleanup_old_exports(export_dir)

    return send_file(
        filepath,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{user.username}_gdpr_export.zip",
    )
