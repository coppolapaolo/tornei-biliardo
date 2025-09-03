# routes/main.py - AGGIORNATO per correggere import path
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, logout_user
from datetime import date
from models import db, Campionato, Gara, Classification, User
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

    # Mostra TUTTI i campionati attivi
    active_campionatos = (
        Campionato.query.filter_by(is_active=True)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    if not active_campionatos:
        return render_template("no_campionato.html")

    # Raccogli dati per TUTTI i campionati attivi
    tournaments_data = []
    for campionato in active_campionatos:
        # Prossime gare per questo campionato
        upcoming_garas = (
            Gara.query.filter(
                Gara.campionato_id == campionato.id, Gara.date >= date.today()
            )
            .order_by(Gara.date)
            .limit(3)
            .all()
        )

        # Classifica generale per questo campionato (top 5)
        top_classifications = (
            Classification.query.filter(Classification.campionato_id == campionato.id)
            .order_by(Classification.position)
            .limit(5)
            .all()
        )
        
        # Se non c'è classifica generale, gara a prendere la classifica della gara più recente
        if not top_classifications and campionato.campionato_type == 'Amalfi':
            from models.classification.models import RoundClassification
            from models.status_enum import GaraStatus
            
            # Trova la gara completata più recente
            latest_completed_gara = (
                Gara.query.filter(
                    Gara.campionato_id == campionato.id,
                    Gara.status == GaraStatus.COMPLETED.value
                )
                .order_by(Gara.date.desc())
                .first()
            )
            
            if latest_completed_gara:
                # Prendi la classifica dell'ultimo turno di questa gara
                top_classifications = (
                    RoundClassification.query.filter(
                        RoundClassification.gara_id == latest_completed_gara.id
                    )
                    .filter(RoundClassification.round_number == latest_completed_gara.current_round)
                    .order_by(RoundClassification.position)
                    .limit(5)
                    .all()
                )

        tournaments_data.append(
            {
                "campionato": campionato,
                "upcoming_garas": upcoming_garas,
                "top_classifications": top_classifications,
            }
        )

    return render_template(
        "index.html",
        tournaments_data=tournaments_data,
        active_campionatos=active_campionatos,
    )


@main_bp.route("/reset")
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403
    
    from utils.reset_manager import ResetManager
    manager = ResetManager()
    reset_options = manager.get_reset_options()
    
    return render_template("reset.html", reset_options=reset_options)


@main_bp.route("/reset/confirm", methods=["POST"])
def reset_database_confirm():
    """Conferma reset database"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    password = request.form.get("password", "")
    reset_type = request.form.get("reset_type", "base")
    
    if password != "RESET_DB_CONFIRM":
        flash("Password di conferma errata!")
        return redirect(url_for("main.reset_database"))

    try:
        # LOGOUT dell'utente corrente prima del reset
        if current_user.is_authenticated:
            logout_user()

        from utils.reset_manager import ResetManager
        manager = ResetManager()
        result = manager.execute_reset(reset_type)
        
        if result['status'] == 'success':
            flash(result['message'])
            flash("Sei stato disconnesso automaticamente. Rieffettua il login.", "info")
        else:
            flash(f"Errore: {result['message']}", "danger")
            
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


@main_bp.route("/reset/save", methods=["POST"])
def save_reset_snapshot():
    """Salva lo stato corrente del database come snapshot"""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403
    
    name = request.form.get("name", "")
    description = request.form.get("description", "")
    
    if not name:
        flash("Il nome dello snapshot è obbligatorio!", "danger")
        return redirect(request.referrer or url_for("main.reset_database"))
    
    from utils.reset_manager import ResetManager
    manager = ResetManager()
    result = manager.save_current_state(name, description)
    
    if result['status'] == 'success':
        flash(result['message'], "success")
    else:
        flash(result['message'], "danger")
    
    return redirect(request.referrer or url_for("main.reset_database"))


@main_bp.route("/reset/delete/<snapshot_id>", methods=["POST"])
def delete_reset_snapshot(snapshot_id):
    """Elimina uno snapshot salvato"""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403
    
    from utils.reset_manager import ResetManager
    manager = ResetManager()
    result = manager.delete_snapshot(snapshot_id)
    
    if result['status'] == 'success':
        flash(result['message'], "success")
    else:
        flash(result['message'], "danger")
    
    return redirect(url_for("main.reset_database"))
