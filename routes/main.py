# routes/main.py - AGGIORNATO per correggere import path
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, logout_user
from datetime import date
from models import db, Tournament, Prova, Classification, User
from config import Config


def _role_truthy(user, attr_name: str) -> bool:
    val = getattr(user, attr_name, None)
    if val is None:
        return False
    try:
        return bool(val() if callable(val) else val)
    except TypeError:
        return bool(val)


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Homepage pubblica; se autenticato → dashboard utente"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    # Mostra TUTTI i tornei attivi
    active_tournaments = (
        Tournament.query.filter_by(is_active=True)
        .order_by(Tournament.created_at.desc())
        .all()
    )

    if not active_tournaments:
        return render_template("no_tournament.html")

    # Raccogli dati per TUTTI i tornei attivi
    tournaments_data = []
    for tournament in active_tournaments:
        # Prossime prove per questo torneo
        upcoming_provas = (
            Prova.query.filter(
                Prova.tournament_id == tournament.id, Prova.date >= date.today()
            )
            .order_by(Prova.date)
            .limit(3)
            .all()
        )

        # Classifica generale per questo torneo (top 5)
        top_classifications = (
            Classification.query.filter(Classification.tournament_id == tournament.id)
            .order_by(Classification.position)
            .limit(5)
            .all()
        )

        tournaments_data.append(
            {
                "tournament": tournament,
                "upcoming_provas": upcoming_provas,
                "top_classifications": top_classifications,
            }
        )

    return render_template(
        "index.html",
        tournaments_data=tournaments_data,
        active_tournaments=active_tournaments,
    )


@main_bp.route("/reset")
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    return render_template("reset.html")


@main_bp.route("/reset/confirm", methods=["POST"])
def reset_database_confirm():
    """Conferma reset database"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    password = request.form.get("password", "")
    if password != "RESET_DB_CONFIRM":
        flash("Password di conferma errata!")
        return redirect(url_for("main.reset_database"))

    try:
        # LOGOUT dell'utente corrente prima del reset
        if current_user.is_authenticated:
            logout_user()

        # Elimina tutte le tabelle
        db.drop_all()

        # Ricrea tutte le tabelle
        db.create_all()

        # Import enhanced reset functionality - CORREZIONE PATH
        from utils.reset_data import reset_database_enhanced

        # Create enhanced reset data
        reset_database_enhanced()

        flash(
            "Database resettato con successo! "
            "Enhanced data created with rich user examples."
        )
        flash("Sei stato disconnesso automaticamente. Rieffettua il login.", "info")
        return redirect(url_for("main.index"))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}")
        return redirect(url_for("main.reset_database"))


@main_bp.route("/debug/login/<username>")
def quick_login(username):
    """Quick login per debug - SOLO in modalità debug"""
    from config import Config
    from flask_login import login_user

    if not Config.DEBUG_MODE:
        return "Quick login non disponibile in produzione", 403

    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f"Utente {username} non trovato!")
        return redirect(url_for("main.index"))

    login_user(user)
    flash(f"Quick login effettuato come {username}!")

    return redirect(url_for("dashboard.dashboard"))
