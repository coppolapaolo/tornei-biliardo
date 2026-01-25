# routes/auth.py - Route di autenticazione
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from flask_babel import gettext as _
from models.user.services import UserService
from models.user.profile_service import UserProfileService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
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
                from models.gamification.frontend_bridge import flash_gamification_event, GamificationEventType
                flash_gamification_event(GamificationEventType.WELCOME, {
                    "username": user.username,
                    "title": _("Che piacere rivederti!"),
                    "subtitle": _("Tutto pronto per giocare?")
                })
            except ImportError:
                pass  # Gamification module might be disabled

            if not user.is_verified:
                flash("Attenzione: il tuo account non è ancora verificato. Controlla la tua email.", "warning")

            return redirect(url_for("dashboard.dashboard"))
        else:
            flash("Username o password errati. Error.", "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Pagina di registrazione"""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        phone = request.form.get("phone", "")

        # Use service layer for user creation
        try:
            user = UserService.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone if phone else None,
            )

            # login_user(user) # Don't login automatically if verification is required? 
            # The prompt says "email venisse verificata", usually this means verify first then login.
            # But earlier I planned to login but warn. 
            # However, standard practice: Redirect to login or "check email" page.
            # Let's flash message and redirect to login.
            
            flash("Registrazione completata! Controlla la tua email per verificare l'account.", "success")
            
            # Show welcome gamification event on the login page
            welcome_payload = {
                "type": "welcome",
                "data": {
                    "username": username,
                    "title": _("Ti diamo il benvenuto!"),
                    "subtitle": _("Registrazione completata con successo.")
                }
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
def forgot_password():
    """Richiesta reset password"""
    if request.method == "POST":
        email = request.form["email"]
        if UserProfileService.request_password_reset(email):
            flash("Se l'email esiste, riceverai un link per resettare la password.", "info")
            return redirect(url_for("auth.login"))
        else:
            flash("Errore nell'invio della richiesta.", "error")

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Pagina di reset password"""
    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Le password non coincidono.", "error")
            return render_template("auth/reset_password.html", token=token)

        try:
            if UserProfileService.reset_password_with_token(token, password):
                flash("Password aggiornata con successo! Ora puoi effettuare il login.", "success")
                return redirect(url_for("auth.login"))
            else:
                flash("Token non valido o scaduto.", "error")
                return redirect(url_for("auth.login"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("auth/reset_password.html", token=token)

    return render_template("auth/reset_password.html", token=token)
