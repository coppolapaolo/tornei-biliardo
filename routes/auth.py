# routes/auth.py - Route di autenticazione
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from markupsafe import Markup, escape
from flask_login import login_user, logout_user, login_required
from flask_babel import gettext as _
from models.user.services import UserService
from models.user.profile_service import UserProfileService
from utils.analytics import AnalyticsEvent, track_event
from utils.rate_limiter import limiter

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute", methods=["POST"])
def login():
    """Pagina di login"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Use service layer for authentication
        user = UserService.authenticate_user(username, password)

        if user:
            login_user(user)

            # Gamification: Welcome message
            try:
                from models.gamification.frontend_bridge import (
                    flash_gamification_event,
                    GamificationEventType,
                )

                flash_gamification_event(
                    GamificationEventType.WELCOME,
                    {
                        "username": user.username,
                        "title": _("Che piacere rivederti!"),
                        "subtitle": _("Tutto pronto per giocare?"),
                    },
                )

                # Check for feature nudges (unused unlocked features)
                from models.gamification.nudge_service import NudgeService

                NudgeService.check_login_nudges(user.id)

            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Gamification welcome flash failed: {e}"
                )

            if not user.is_verified:
                # B11: explain real consequence (password recovery) + link to
                # the profile page where the resend form already lives. The
                # /verify-email route is POST-only (CSRF-protected), so we do
                # NOT link to it directly from a flash anchor.
                # NB: `Markup + str` re-escapes the str — keep every HTML chunk
                # wrapped in Markup() and rely on escape() for user-derived data.
                profile_url = url_for("player.edit_profile") + "#email"
                msg = (
                    escape(
                        _(
                            "Il tuo account non è ancora verificato. Senza "
                            "email confermata non potrai recuperare la "
                            "password se la dimentichi."
                        )
                    )
                    + Markup(' <a href="')
                    + escape(profile_url)
                    + Markup('" class="alert-link">')
                    + escape(_("Vai al profilo per verificare l'email"))
                    + Markup("</a>")
                )
                flash(msg, "warning")

            return redirect(url_for("dashboard.dashboard"))
        else:
            flash(_("Username o password errati."), "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5/minute", methods=["POST"])
def register():
    """Pagina di registrazione"""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        phone = request.form.get("phone", "")

        # Use service layer for user creation
        try:
            UserService.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone if phone else None,
            )

            # Analytics: tracciato qui e non con un onclick sul bottone, così
            # nel conteggio finiscono solo le registrazioni davvero riuscite
            # (nessun dato personale viene inviato a Google).
            track_event(AnalyticsEvent.USER_REGISTERED)

            # Standard practice: don't auto-login on register; flash and send to
            # login page so the user goes through the verify-email flow first.

            flash(
                _(
                    "Registrazione completata! Controlla la tua email per "
                    "verificare l'account."
                ),
                "success",
            )

            # Show welcome gamification event on the login page
            welcome_payload = {
                "type": "welcome",
                "data": {
                    "username": username,
                    "title": _("Ti diamo il benvenuto!"),
                    "subtitle": _("Registrazione completata con successo."),
                },
            }
            flash(json.dumps(welcome_payload), category="gamification_event")

            return redirect(url_for("auth.login"))

        except ValueError as e:
            flash(str(e))
            return render_template("register.html")

    return render_template("register.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Logout utente"""
    logout_user()
    return redirect(url_for("main.index"))


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    """Verifica email tramite token"""
    if UserProfileService.verify_email(token):
        flash("Email verificata con successo! Ora puoi effettuare il login.", "success")
    else:
        flash("Link di verifica non valido o scaduto.", "error")

    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3/minute", methods=["POST"])
def forgot_password():
    """Richiesta reset password"""
    if request.method == "POST":
        email = request.form["email"]
        if UserProfileService.request_password_reset(email):
            flash(
                "Se l'email esiste, riceverai un link per resettare la password.",
                "info",
            )
            return redirect(url_for("auth.login"))
        else:
            flash("Errore nell'invio della richiesta.", "error")

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Pagina di reset password"""
    # Validate token on GET to avoid showing form for expired/used tokens
    if request.method == "GET":
        from models.user.tokens import UserToken

        token_obj = UserToken.query.filter_by(
            token=token, token_type="password_reset"
        ).first()
        if not token_obj or not token_obj.is_valid():
            flash("Token non valido o scaduto.", "error")
            return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Le password non coincidono.", "error")
            return render_template("auth/reset_password.html", token=token)

        try:
            if UserProfileService.reset_password_with_token(token, password):
                flash(
                    "Password aggiornata con successo! Ora puoi effettuare il login.",
                    "success",
                )
                return redirect(url_for("auth.login"))
            else:
                flash("Token non valido o scaduto.", "error")
                return redirect(url_for("auth.login"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("auth/reset_password.html", token=token)

    return render_template("auth/reset_password.html", token=token)
