"""Director routes for tournament and standalone competition management."""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from functools import wraps

from app import db
from models.competition.models import Prova, WithdrawPolicy
from models.competition.services import ProvaService
from models.tournament.models import Tournament, TournamentDirector


director_bp = Blueprint("director", __name__, url_prefix="/director")


def director_required(f):
    """Decorator to require director role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_director and not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@director_bp.route("/create_standalone", methods=["GET", "POST"])
@director_required
def create_prova_standalone():
    """Crea prova standalone (director o admin)"""
    if request.method == "POST":
        try:
            # Campi base
            name = request.form.get("name", "").strip()
            if not name:
                flash("Il nome della competizione è obbligatorio!", "error")
                return redirect(url_for("director.create_prova_standalone"))

            date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            
            # Campi opzionali
            location = request.form.get("location", "").strip()
            description = request.form.get("description", "").strip()
            rounds_count = int(request.form.get("rounds_count", 3))
            min_participants = int(request.form.get("min_participants", 2))
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None
            entry_fee = float(request.form.get("entry_fee", 0.0))

            # Game settings
            discipline = request.form["discipline"]
            distance = int(request.form["distance"])
            exact_number = "exact_number" in request.form
            best_of = not exact_number
            withdraw_policy = request.form.get("withdraw_policy", WithdrawPolicy.EXCLUDE.value)

            # Crea la prova standalone usando il service layer (senza tournament_id)
            prova = ProvaService.create_prova(
                tournament_id=None,  # Prove standalone non hanno torneo
                number=1,  # Sempre 1 per prove standalone
                name=name,
                date=date,
                location=location,
                description=description,
                rounds_count=rounds_count,
                min_participants=min_participants,
                max_participants=max_participants,
                entry_fee=entry_fee,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                withdraw_policy=withdraw_policy,
                director_id=current_user.id  # Il direttore che crea è il gestore
            )

            flash(f"Gara singola '{name}' creata con successo!", "success")
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova.id))

        except ValueError as e:
            flash(f"Errore nella creazione: {str(e)}", "error")
            return redirect(url_for("director.create_prova_standalone"))
        except Exception as e:
            flash(f"Errore imprevisto: {str(e)}", "error")
            return redirect(url_for("director.create_prova_standalone"))

    # GET request - show form
    # Recupera luoghi utilizzati in precedenza
    recent_locations = db.session.query(Prova.location).distinct().filter(
        Prova.location.isnot(None), 
        Prova.location != ""
    ).limit(10).all()
    recent_locations = [loc[0] for loc in recent_locations if loc[0]]
    
    return render_template(
        "director/prova_create_standalone.html",
        WithdrawPolicy=WithdrawPolicy,
        recent_locations=recent_locations
    )