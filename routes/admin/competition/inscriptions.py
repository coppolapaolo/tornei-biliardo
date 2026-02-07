# routes/admin/competition/inscriptions.py
"""Inscription management routes for competitions."""

from flask import (
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user
from datetime import datetime
from models.shared.utils import parse_date_string

from models import (
    db,
    Gara,
)
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.state_service import StateService
from utils import gara_manager_required
from utils.route_helpers import handle_service_action

from . import competition_bp


@competition_bp.route("/<int:gara_id>/open_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def open_inscriptions(gara_id):
    """Apri iscrizioni per una gara"""

    def action():
        start_key = "inscription_start_utc" if "inscription_start_utc" in request.form else "inscription_start"
        end_key = "inscription_end_utc" if "inscription_end_utc" in request.form else "inscription_end"
        start_str = request.form.get(start_key)
        end_str = request.form.get(end_key)
        if not start_str or not end_str:
            raise ValueError("Date di inizio o fine iscrizioni mancanti")
        inscription_start = parse_date_string(start_str)
        if not inscription_start:
            raise ValueError(f"Formato data non valido: {start_str}")
        inscription_end = parse_date_string(end_str)
        if not inscription_end:
            raise ValueError(f"Formato data non valido: {end_str}")
        InscriptionService.open_inscriptions(gara_id, inscription_start, inscription_end)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Iscrizioni aperte!",
    )


@competition_bp.route("/<int:gara_id>/modify_inscription_dates", methods=["POST"])
@login_required
@gara_manager_required
def modify_inscription_dates(gara_id):
    """Modifica date di iscrizione per una gara"""
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    return handle_service_action(
        action=lambda: InscriptionService.modify_inscription_dates(
            gara_id, inscription_start, inscription_end
        ),
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Date di iscrizione aggiornate con successo!",
        error_prefix=None,
    )


@competition_bp.route("/<int:gara_id>/close_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def close_inscriptions(gara_id):
    """Chiude le iscrizioni e torna la gara allo stato setup se non ci sono iscritti"""

    def action():
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError("Gara non trovata.")

        if gara.status != GaraStatus.INSCRIPTION.value:
            raise ValueError("La gara non è in stato di iscrizione.")

        active_count = gara.get_active_inscriptions_count()
        if active_count > 0:
            raise ValueError(
                "Non è possibile chiudere le iscrizioni quando ci sono già "
                "degli iscritti."
            )

        StateService.reopen_setup(gara)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Iscrizioni chiuse con successo! La gara è tornata allo stato di setup.",
    )


@competition_bp.route("/<int:gara_id>/admin_inscribe", methods=["POST"])
@login_required
@gara_manager_required
def admin_inscribe_user(gara_id):
    """Iscrive un utente alla gara (solo admin/direttori)."""
    from models.competition.inscription_service import InscriptionService
    from models.notification.factory import NotificationFactory
    from models.user.models import User
    from models.competition.models import Gara

    try:
        # Verifica che la gara esista
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash("Gara non trovata.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara sia ancora in fase di iscrizioni
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash(
                "Non è possibile iscrivere utenti quando la gara non è in fase di iscrizione.",
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Valida user_id dal form
        user_id_str = request.form.get("user_id")
        if not user_id_str:
            flash("Nessun utente selezionato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        user_id = int(user_id_str)

        # Verifica che l'utente esista
        user = db.session.get(User, user_id)
        if not user:
            flash("Utente non trovato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Esegui l'iscrizione usando il service layer
        inscription = InscriptionService.inscribe_user(user_id, gara_id)

        if inscription:
            # Formatta la data per la notifica
            gara_date_str = gara.date.strftime("%d/%m/%Y") if gara.date else "data da definire"
            gara_name = gara.name or f"Gara {gara.number}"

            # Crea notifica per l'utente iscritto
            NotificationFactory.create_gara_inscription_notification(
                user_id=user_id,
                gara_id=gara_id,
                gara_name=gara_name,
                gara_date=gara_date_str,
                enrolled_by=current_user.username,
            )

            if inscription.is_waitlist:
                flash(
                    f"Utente {user.username} aggiunto alla lista d'attesa (posizione {inscription.waitlist_position}).",
                    "warning",
                )
            else:
                flash(f"Utente {user.username} iscritto con successo.", "success")
        else:
            flash(f"Utente {user.username} già iscritto a questa gara.", "warning")

    except ValueError as ve:
        flash(f"Errore: {str(ve)}", "error")
    except Exception as e:
        flash(f"Errore durante l'iscrizione: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/admin_uninscribe/<int:user_id>", methods=["POST"])
@login_required
@gara_manager_required
def admin_uninscribe_user(gara_id, user_id):
    """Disiscrive un utente dalla gara (solo admin/direttori)."""
    from models.competition.inscription_service import InscriptionService
    from models.user.models import User
    from models.competition.models import Gara

    try:
        # Verifica che l'utente esista
        user = db.session.get(User, user_id)
        if not user:
            flash("Utente non trovato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara esista
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash("Gara non trovata.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara sia ancora in fase di iscrizioni
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash(
                "Non è possibile disiscrivere utenti quando il primo turno "
                "è già iniziato.",
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Esegui la disiscrizione
        success = InscriptionService.admin_uninscribe_user(
            user_id, gara_id, current_user.id
        )

        if success:
            flash(f"Utente {user.username} discritto con successo.", "success")
        else:
            flash("Errore: utente non iscritto a questa gara.", "error")

    except Exception as e:
        flash(f"Errore durante la disiscrizione: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────────


@competition_bp.route("/<int:gara_id>/add_director", methods=["POST"])
@login_required
@gara_manager_required
def add_director(gara_id):
    """Aggiunge un co‑direttore alla gara"""
    new_director_id = int(request.form["user_id"])

    try:
        success = GaraService.add_director(
            gara_id=gara_id,
            user_id=new_director_id,
            assigned_by_id=current_user.id,
        )

        if success:
            flash("Direttore aggiunto con successo.")
        else:
            flash("Utente già presente come direttore.", "warning")

    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Errore durante l'aggiunta del direttore: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/remove_director", methods=["POST"])
@login_required
@gara_manager_required
def remove_director(gara_id):
    """Rimuove un co‑direttore dalla gara"""
    director_id = int(request.form["user_id"])

    success = GaraService.remove_director(gara_id=gara_id, user_id=director_id)

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Errore: direttore non trovato.", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
