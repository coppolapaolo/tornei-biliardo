# routes/player/exports.py
"""CSV and GDPR data export routes for player profiles."""

import csv
import io
import json
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, cast

from flask import (
    redirect,
    url_for,
    flash,
    Response,
    current_app,
    send_file,
)
from flask_login import login_required, current_user
from flask_babel import _
from werkzeug.exceptions import abort

from models import db, Match, User
from models.status_enum import MatchStatus
from models.base import utc_now
from utils import player_only

from . import player_bp


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
    cutoff = utc_now() - timedelta(hours=GDPR_EXPORT_MAX_AGE_HOURS)
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
    try:
        privacy = PrivacyService.get_privacy_settings(user_id)
        # Ensure it's not detached/expired
        db.session.refresh(privacy)
        privacy_data = {
            "show_email": privacy.show_email,
            "show_phone": privacy.show_phone,
            "show_statistics": privacy.show_statistics,
            "show_recent_matches": privacy.show_recent_matches,
            "show_classifications": privacy.show_classifications,
            "show_challenge_stats": privacy.show_challenge_stats,
        }
    except Exception as e:
        current_app.logger.warning(f"Could not fetch privacy settings for user {user_id}, using defaults: {e}")
        privacy_data = {
            "show_email": False,
            "show_phone": False,
            "show_statistics": False,
            "show_recent_matches": False,
            "show_classifications": False,
            "show_challenge_stats": False,
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
            "total_matches_won": classif.total_matches_won,
            "total_racks_won": classif.total_racks_won,
            "total_point_difference": classif.total_point_difference,
            "gare_played": classif.gare_played,
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
        "export_date": serialize_date(utc_now()),
        "export_version": "1.0",
        "account": account_data,
        "privacy_settings": privacy_data,
        "inscriptions": inscriptions_data,
        "matches": matches_data,
        "classifications": classifications_data,
        "challenges": challenges_data,
        "gamification": gamification_data,
    }


def _generate_gdpr_export(
    app, user_id: int, username: str, i18n_strings: dict[str, str]
) -> None:
    """Background task to generate GDPR export.

    Args:
        app: Flask application instance
        user_id: User ID to export data for
        username: Username for filename
        i18n_strings: Pre-translated strings (translated before thread spawn
            because Flask-Babel requires request context which is unavailable in threads)
    """
    with app.app_context():
        try:
            # Collect data
            data = _collect_user_data(user_id)
            if not data:
                raise ValueError(f"No data found for user {user_id}")

            # Create export directory
            export_dir = Path(app.instance_path) / "gdpr_exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            # Cleanup old exports
            _cleanup_old_exports(export_dir)

            # Generate filename
            timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
            filename = f"{user_id}_{timestamp}.zip"
            filepath = export_dir / filename

            # Create ZIP with JSON
            json_content = json.dumps(data, ensure_ascii=False, indent=2)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    f"{username}_gdpr_export_{timestamp}.json",
                    json_content.encode("utf-8"),
                )

            # Send notification (using pre-translated strings)
            from models.notification.services import NotificationService
            from models.notification.models import NotificationType, NotificationPriority

            NotificationService.create_notification(
                user_id=user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=i18n_strings["success_title"],
                message=i18n_strings["success_message"],
                priority=NotificationPriority.NORMAL,
                action_url=f"/player/gdpr-export/download/{filename}",
                action_text=i18n_strings["success_action"],
            )

            # Emit SSE event for real-time notification
            from routes.sse import emit_user_event

            emit_user_event(
                user_id,
                "gdpr_export_ready",
                {"filename": filename, "download_url": f"/player/gdpr-export/download/{filename}"},
            )

        except Exception as e:
            db.session.rollback()  # Ensure session is clean after failure
            # Log error and notify user of failure
            current_app.logger.error(f"GDPR export failed for user {user_id}: {e}", exc_info=True)
            try:
                from models.notification.services import NotificationService
                from models.notification.models import NotificationType, NotificationPriority

                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.ACCOUNT_UPDATE,
                    title=i18n_strings["error_title"],
                    message=i18n_strings["error_message"],
                    priority=NotificationPriority.HIGH,
                )
            except Exception as notify_error:
                current_app.logger.error(
                    f"Failed to send error notification for user {user_id}: {notify_error}",
                    exc_info=True,
                )


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
        if utc_now() - mtime < timedelta(minutes=5):
            flash(
                _("Un export è già in corso o è stato generato di recente. Controlla le notifiche."),
                "warning",
            )
            return redirect(url_for("player.privacy_settings"))

    # Pre-translate strings while we still have request context
    # (Flask-Babel requires request context, unavailable in background threads)
    i18n_strings = {
        "success_title": _("Export GDPR Pronto"),
        "success_message": _("Il tuo archivio dati è pronto per il download. Il link scadrà tra 24 ore."),
        "success_action": _("Scarica"),
        "error_title": _("Errore Export GDPR"),
        "error_message": _("Si è verificato un errore durante la generazione dell'archivio. Riprova più tardi."),
    }

    # Start background export
    app = current_app._get_current_object()  # Get actual app object for thread
    thread = threading.Thread(
        target=_generate_gdpr_export,
        args=(app, user.id, user.username, i18n_strings),
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
    if utc_now() - mtime > timedelta(hours=GDPR_EXPORT_MAX_AGE_HOURS):
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
