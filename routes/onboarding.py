"""Onboarding obbligatorio (ADR-035).

Pagina dedicata, brevissima, mostrata una volta sola a ogni utente (al primo
login per gli account esistenti — backfill). L'obbligatorietà è imposta
server-side dall'hook ``enforce_onboarding`` in ``app.py``: finché
``onboarding_completed`` è ``False`` l'utente non-admin viene reindirizzato qui.

Step (design V3 §7, riconciliato ADR-033/034):
1. *Dove*: città home (fallback prossimità) + selezione sale (disponibilità).
2. *Cosa*: interessi (drill / match / tornei).

Tutti i campi sono opt-in; completare la pagina segna l'onboarding come fatto.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_babel import gettext as _
from flask_login import login_required, current_user

from models.location.models import BilliardHall
from models.user.onboarding_service import OnboardingService, VALID_INTERESTS

onboarding_bp = Blueprint("onboarding", __name__)


@onboarding_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    """Mostra (GET) o completa (POST) l'onboarding dell'utente corrente."""
    if request.method == "POST":
        home_city = request.form.get("home_city", "")
        venue_ids = request.form.getlist("venue_ids")
        interests = [
            i for i in request.form.getlist("interests") if i in VALID_INTERESTS
        ]

        OnboardingService.complete_onboarding(
            user_id=current_user.id,
            home_city=home_city,
            venue_ids=venue_ids,
            interests=interests,
        )

        flash(_("Tutto pronto! Buon divertimento."), "success")
        return redirect(url_for("dashboard.dashboard"))

    active_venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )
    return render_template(
        "onboarding.html",
        active_venues=active_venues,
        valid_interests=VALID_INTERESTS,
    )
