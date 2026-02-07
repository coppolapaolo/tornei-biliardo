# routes/player/account.py
"""Account deletion route for player profiles."""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user, logout_user

from models import db, User
from models.user.services import UserDeletionService
from utils import player_only

from . import player_bp


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
        flash("Errore durante l'eliminazione dell'account.", "danger")
        raise
