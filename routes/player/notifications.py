# routes/player/notifications.py
"""Notification management and venue manager request routes."""

from typing import cast

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, User
from utils import feature_required

from . import player_bp

# ============ NOTIFICATIONS ============


@player_bp.route("/notifications")
@login_required
def notifications():
    """Mostra le notifiche dell'utente (accessibile a tutti gli utenti autenticati)"""
    from models.notification.models import Notification
    from models.notification.services import NotificationService

    # Mark PENDING notifications as SENT (via service layer)
    NotificationService.mark_pending_as_sent(current_user.id)

    # Bug 16: ad ogni apertura cancella TUTTE le notifiche scadute rispetto
    # alla finestra di auto-cancellazione globale (default 30 giorni se non
    # configurata), così l'utente atterra su una vista pulita.
    try:
        NotificationService.auto_delete_for_user(current_user.id)
    except Exception:
        # Auto-delete is a best-effort cleanup: never block the listing.
        import logging

        logging.getLogger(__name__).warning(
            "auto_delete_for_user failed for user %s",
            current_user.id,
            exc_info=True,
        )

    # Get all notifications for current user
    user_notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    # Finestra di auto-cancellazione globale (default 30 se mai configurata,
    # None se disattivata esplicitamente) — pre-popola il form.
    auto_delete_days = NotificationService.get_global_auto_delete_days(current_user.id)

    return render_template(
        "player/notifications.html",
        notifications=user_notifications,
        auto_delete_days=auto_delete_days,
    )


@player_bp.route("/notifications/<int:notification_id>/mark_read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Segna una notifica come letta"""
    from models.notification.services import NotificationService

    notification = NotificationService.mark_notification_read(
        notification_id, current_user.id
    )

    # If there's an action URL, redirect to it
    if notification and notification.action_url:
        return redirect(notification.action_url)

    return redirect(url_for("player.notifications"))


@player_bp.route("/notifications/mark_all_read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Segna tutte le notifiche come lette"""
    from models.notification.services import NotificationService

    NotificationService.mark_all_read(current_user.id)

    flash("Tutte le notifiche sono state segnate come lette.")
    return redirect(url_for("player.notifications"))


@player_bp.route("/notifications/delete_selected", methods=["POST"])
@login_required
def delete_selected_notifications():
    """Cancella le notifiche selezionate"""
    from models.notification.services import NotificationService

    notification_ids = request.form.getlist("notification_ids[]")

    if not notification_ids:
        flash("Nessuna notifica selezionata.", "warning")
        return redirect(url_for("player.notifications"))

    # Convert to integers
    notification_ids = [int(nid) for nid in notification_ids]

    count = NotificationService.delete_notifications_bulk(
        notification_ids, current_user.id
    )

    flash(f"{count} notifiche eliminate con successo.", "success")
    return redirect(url_for("player.notifications"))


@player_bp.route("/notifications/update_auto_delete", methods=["POST"])
@login_required
def update_auto_delete():
    """Aggiorna impostazione globale auto-cancellazione notifiche"""
    from models.notification.services import NotificationService

    is_enabled = "auto_delete_enabled" in request.form
    days = request.form.get("auto_delete_days")

    # Check if this is an AJAX request
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.accept_json
    )

    if is_enabled and days:
        try:
            days_int = int(days)
            if days_int < 1 or days_int > 365:
                if is_ajax:
                    return (
                        {
                            "success": False,
                            "message": "Il numero di giorni deve essere tra 1 e 365.",
                        },
                        400,
                    )
                flash("Il numero di giorni deve essere tra 1 e 365.", "warning")
                return redirect(url_for("player.notifications"))

            # Set global auto-delete window
            NotificationService.set_global_auto_delete_days(current_user.id, days_int)

            message = (
                "Auto-cancellazione attivata: le notifiche lette verranno "
                f"eliminate dopo {days_int} giorni."
            )
            if is_ajax:
                return {"success": True, "message": message}, 200
            flash(message, "success")
        except (ValueError, TypeError):
            if is_ajax:
                return (
                    {"success": False, "message": "Numero di giorni non valido."},
                    400,
                )
            flash("Numero di giorni non valido.", "warning")
    else:
        # Disable auto-delete (persiste esplicitamente None)
        NotificationService.set_global_auto_delete_days(current_user.id, None)
        message = "Auto-cancellazione disattivata."
        if is_ajax:
            return {"success": True, "message": message}, 200
        flash(message, "success")

    return redirect(url_for("player.notifications"))


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUESTS
# ────────────────────────────────────────────────────────────────────────────────
# NOTE: Main venue listing and details now handled by admin.venue.venues_list()
# and admin.venue.venue_detail() with role-based content negotiation pattern


@player_bp.route("/request_venue_manager", methods=["POST"])
@login_required
@feature_required("request_venue_manager")
def request_venue_manager():
    """Richiesta per diventare gestore di una sala specifica"""
    if current_user.is_admin:
        flash(
            "Gli amministratori non hanno bisogno di richiedere "
            "il ruolo di gestore sala.",
            "info",
        )
        return redirect(url_for("admin.venue.venues_list"))

    venue_id = request.form.get("venue_id")
    notes = request.form.get("notes", "").strip()

    if not venue_id:
        flash("Errore: Sala non specificata.", "error")
        return redirect(url_for("admin.venue.venues_list"))

    try:
        from models.user.venue_manager_service import VenueManagerService
        from models import BilliardHall

        new_request = VenueManagerService.create_venue_manager_request(
            current_user.id, int(venue_id), notes
        )

        # Get venue for flash message
        venue = db.session.get(BilliardHall, venue_id)

        flash_message = f"Richiesta per gestire '{venue.name}' inviata con successo!"
        if new_request.is_contested:
            flash_message += (
                " Nota: questa sala ha già un gestore, "
                "l'admin valuterà la tua richiesta."
            )
        flash(flash_message, "success")

    except ValueError as e:
        flash(str(e), "error")

    return redirect(url_for("admin.venue.venues_list"))


@player_bp.route("/cancel_venue_manager_request/<int:request_id>", methods=["POST"])
@login_required
def cancel_venue_manager_request(request_id):
    """Annulla una richiesta per diventare gestore di sala"""
    try:
        from models.user.venue_manager_service import VenueManagerService

        VenueManagerService.cancel_venue_manager_request(
            request_id, cast(User, current_user)
        )
        flash("Richiesta annullata con successo.", "success")
    except Exception as e:
        flash(f"Errore nell'annullare la richiesta: {str(e)}", "error")

    return redirect(url_for("admin.venue.venues_list"))


@player_bp.route("/my_venue_requests")
@login_required
def my_venue_requests():
    """Visualizza le richieste di gestione venue dell'utente"""
    if current_user.is_admin:
        return redirect(url_for("admin.venue.venue_manager_requests"))

    from models.user.venue_manager_service import VenueManagerService

    requests = VenueManagerService.get_venue_manager_requests_by_user(current_user.id)

    return render_template("player/my_venue_requests.html", requests=requests)
