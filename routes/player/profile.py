# routes/player/profile.py
"""User profile display and editing routes.

Privacy, account deletion, and export routes have been split into:
- privacy.py: Privacy settings and hide/show routes
- account.py: Account deletion
- exports.py: CSV and GDPR data export
"""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user
from flask_babel import gettext as _

from models import db, Gara, Inscription, Match
from models.status_enum import MatchStatus
from models.campionato.models import Campionato
from models.user.services import UserService
from models.user.permission_service import UserPermissionService
from utils import player_only
from utils.route_helpers import handle_service_action

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
    # Order by Match.created_at first so standalone and campionato matches
    # appear together in chronological order (B25).
    matches = (
        Match.query.filter(
            db.or_(
                Match.player1_id == current_user.id, Match.player2_id == current_user.id
            )
        )
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(
            Match.created_at.desc(),
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
        from models.competition.gara_challenge import (
            GaraChallenge,
            GaraChallengeAttempt,
        )
        from models.challenge import Challenge

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

    user = db.get_or_404(User, user_id)

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
    """Modifica username, email e telefono dell'utente corrente."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None

        try:
            user = UserService.update_user(
                current_user.id, username=username, email=email, phone=phone
            )
            # If the email changed, update_user revoked is_verified and queued
            # a verification token. Send the email AFTER the transaction commits
            # (i.e. now, post-@transactional return) to avoid I/O under DB lock.
            if hasattr(user, "_pending_verification_email"):
                from models.user.profile_service import UserProfileService

                UserProfileService.send_pending_verification_email(user)
                flash(
                    _(
                        "Informazioni aggiornate. Abbiamo inviato una "
                        "nuova email di verifica al nuovo indirizzo."
                    ),
                    "success",
                )
            else:
                flash(_("Informazioni aggiornate correttamente."), "success")
            return redirect(url_for("player.profile"))
        except ValueError as e:
            flash(str(e), "error")
        except Exception:
            flash(_("Si è verificato un errore durante l'aggiornamento."), "error")

    # GET o POST fallito → ripresenta il form
    return render_template("player/profile_edit.html", user=current_user)


@player_bp.route("/profile/verify-email", methods=["POST"])
@login_required
@player_only
def request_verification_email():
    """Richiede l'invio di una nuova email di verifica."""
    if current_user.is_verified:
        flash(_("La tua email è già verificata."), "info")
        return redirect(url_for("player.edit_profile"))

    from models.user.profile_service import UserProfileService

    try:
        # Use existing service method to generate token and send email
        if UserProfileService.request_verification_email(current_user):
            flash(
                _("Email di verifica inviata. Controlla la tua casella di posta."),
                "success",
            )
        else:
            flash(_("Impossibile inviare l'email. Riprova più tardi."), "error")
    except Exception as e:
        flash(_("Errore durante l'invio: %(detail)s", detail=str(e)), "error")

    return redirect(url_for("player.edit_profile"))


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
    return handle_service_action(
        action=lambda: UserPermissionService.request_director_promotion(
            user_id=current_user.id
        ),
        redirect_url=url_for("player.profile"),
        success_message="Richiesta inviata. Sarai contattato dall'amministratore.",
    )
