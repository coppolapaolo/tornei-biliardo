# routes/admin/venue.py
"""Venue management blueprint for admin interface."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.utils import secure_filename
import os
from typing import cast
from PIL import Image, ImageOps

from models import BilliardHall
from models.location.services import LocationService
from models.user.services import VenueManagementService
from models.user.venue_manager_service import VenueManagerService
from models.user.models import User
from utils import admin_required, venue_manager_required
from utils.route_helpers import handle_service_action, safe_json_error
from flask_login import login_required
from models.base import db, utc_now

# Venue management blueprint
venue_bp = Blueprint("venue", __name__)


@venue_bp.route("/venues")
@login_required
def venues_list():
    """Lista delle sale biliardo - vista role-based (Content Negotiation Pattern)"""
    from flask_login import current_user

    # VenueManagerRequestService functionality is now in VenueManagerService

    # Admin sees all venues, players only see active ones
    if current_user.is_admin:
        venues = BilliardHall.query.order_by(
            BilliardHall.is_active.desc(), BilliardHall.name
        ).all()
    else:
        venues = (
            BilliardHall.query.filter_by(is_active=True)
            .order_by(BilliardHall.name)
            .all()
        )

    if current_user.is_admin:
        # Vista completa admin con statistiche, manager e richieste
        venues_with_stats = []
        for venue in venues:
            try:
                stats = LocationService.get_location_statistics(venue.id)
            except Exception:
                # Fallback if stats fail
                stats = {
                    "active_users_count": 0,
                    "total_matches_played": 0,
                }

            # Get venue manager
            manager = VenueManagementService.get_venue_manager(venue.id)

            # Get manager assignment if manager exists
            manager_assignment = None
            if manager:
                from models.user.models import VenueManagement

                manager_assignment = VenueManagement.query.filter_by(
                    venue_id=venue.id, user_id=manager.id, is_active=True
                ).first()

            # Get pending requests for this venue

            pending_requests = VenueManagerService.get_venue_manager_requests_by_venue(
                venue.id
            )

            # Check if current user is manager of this venue
            is_current_user_manager = manager and manager.id == current_user.id

            venues_with_stats.append(
                {
                    "venue": venue,
                    "stats": stats,
                    "manager": manager,
                    "manager_assignment": manager_assignment,
                    "pending_requests": pending_requests,
                    "is_current_user_manager": is_current_user_manager,
                }
            )
        return render_template(
            "admin/venues_list.html", venues_with_stats=venues_with_stats
        )
    else:
        # Vista semplificata per player/director
        venues_with_managers = []
        for venue in venues:
            manager = VenueManagementService.get_venue_manager(venue.id)

            # Check if current user has pending request for this specific venue
            has_pending_request_for_venue = False
            if not current_user.is_admin:
                # Check if user has pending request for this venue
                user_requests = VenueManagerService.get_venue_manager_requests_by_user(
                    current_user.id
                )
                has_pending_request_for_venue = any(
                    req.venue_id == venue.id and req.status == "pending"
                    for req in user_requests
                )

            venues_with_managers.append(
                {
                    "venue": venue,
                    "manager": manager,
                    "can_request_management": not current_user.is_admin
                    and not current_user.is_venue_manager,
                    "has_pending_request": has_pending_request_for_venue,
                }
            )

        # Check if user has pending venue manager requests
        has_pending_requests = False
        if not current_user.is_admin:
            user_requests = VenueManagerService.get_venue_manager_requests_by_user(
                current_user.id
            )
            has_pending_requests = any(req.status == "pending" for req in user_requests)

        return render_template(
            "player/venues.html",
            venues_with_managers=venues_with_managers,
            has_pending_requests=has_pending_requests,
        )


@venue_bp.route("/venues/<int:venue_id>")
@login_required
def venue_detail(venue_id):
    """Scheda dettagliata sala biliardo - vista role-based"""
    from flask_login import current_user

    venue = db.get_or_404(BilliardHall, venue_id)

    # Allow admin to see inactive venues, but not regular users
    if not venue.is_active and not current_user.is_admin:
        from flask import abort

        abort(404)

    # Get venue statistics
    try:
        stats = LocationService.get_location_statistics(venue_id)
    except Exception:
        stats = {
            "active_users_count": 0,
            "total_matches_played": 0,
            "table_types": [],
            "amenities": [],
        }

    # Get venue manager
    manager = VenueManagementService.get_venue_manager(venue_id)

    if current_user.is_admin or current_user.can_manage_venue(venue_id):
        # Vista completa admin/manager
        # Get all approved venue manager requests (users eligible to be assigned)
        all_requests = VenueManagerService.get_pending_venue_manager_requests()
        from models.status_enum import VenueManagerRequestStatus

        approved_requests = [
            req
            for req in all_requests
            if req.status == VenueManagerRequestStatus.APPROVED
        ]
        eligible_users = [req.user for req in approved_requests]

        # Remove duplicates and current manager
        unique_users = {}
        for user in eligible_users:
            if user.id not in unique_users and (not manager or user.id != manager.id):
                unique_users[user.id] = user

        eligible_users = list(unique_users.values())

        return render_template(
            "admin/venue_detail.html",
            venue=venue,
            stats=stats,
            manager=manager,
            eligible_users=eligible_users,
        )
    else:
        # Vista semplificata player/director
        # Check if current user can manage this venue
        can_manage = current_user.can_manage_venue(venue_id)

        # Check if user has pending requests
        has_pending_requests = False
        if not current_user.is_admin:
            user_requests = VenueManagerService.get_venue_manager_requests_by_user(
                current_user.id
            )
            has_pending_requests = any(req.status == "pending" for req in user_requests)

        return render_template(
            "player/venue_detail.html",
            venue=venue,
            stats=stats,
            manager=manager,
            can_manage=can_manage,
            has_pending_requests=has_pending_requests,
        )


@venue_bp.route("/venues/new", methods=["GET", "POST"])
@admin_required
def create_venue():
    """Crea nuova sala biliardo"""
    if request.method == "POST":
        name = request.form.get("name")
        address = request.form.get("address")
        city = request.form.get("city")
        postal_code = request.form.get("postal_code")
        phone = request.form.get("phone")
        email = request.form.get("email")
        website = request.form.get("website")
        number_of_tables = request.form.get("number_of_tables")
        business_hours = request.form.get("business_hours")
        hourly_rate = request.form.get("hourly_rate")

        # Validate required fields
        if not name:
            flash("Il nome della sala è obbligatorio", "error")
            return render_template("admin/venue_form.html", venue=None)

        if not number_of_tables:
            flash("Il numero di tavoli è obbligatorio", "error")
            return render_template("admin/venue_form.html", venue=None)

        # Table types and amenities as comma-separated values
        table_types_str = request.form.get("table_types", "")
        table_types = [t.strip() for t in table_types_str.split(",") if t.strip()]

        amenities_str = request.form.get("amenities", "")
        amenities = [a.strip() for a in amenities_str.split(",") if a.strip()]

        try:
            venue = LocationService.create_billiard_hall(
                name=name,
                address=address,
                city=city,
                postal_code=postal_code,
                phone=phone,
                email=email,
                website=website,
                number_of_tables=int(number_of_tables) if number_of_tables else None,
                table_types=table_types if table_types else None,
                amenities=amenities if amenities else None,
                hourly_rate=float(hourly_rate) if hourly_rate else None,
                business_hours=business_hours if business_hours else None,
            )

            flash("Sala biliardo creata con successo!", "success")
            return redirect(url_for("admin.venue.venue_detail", venue_id=venue.id))

        except ValueError as e:
            flash(f"Errore nella creazione: {e}", "error")
        except Exception as e:
            flash(f"Errore imprevisto: {e}", "error")

    return render_template("admin/venue_form.html", venue=None)


@venue_bp.route("/venues/<int:venue_id>/edit", methods=["GET", "POST"])
@venue_manager_required
def edit_venue(venue_id):
    """Modifica sala biliardo"""
    venue = db.get_or_404(BilliardHall, venue_id)

    if request.method == "POST":
        # Get form data - collect in kwargs dict to avoid type issues
        update_kwargs = {}

        # String fields
        string_fields = [
            "name",
            "address",
            "city",
            "postal_code",
            "phone",
            "email",
            "website",
            "business_hours",
        ]
        for field in string_fields:
            value = request.form.get(field)
            if value:
                update_kwargs[field] = value

        # Numeric fields
        number_of_tables = request.form.get("number_of_tables")
        if number_of_tables:
            update_kwargs["number_of_tables"] = int(number_of_tables)

        hourly_rate = request.form.get("hourly_rate")
        if hourly_rate:
            update_kwargs["hourly_rate"] = float(hourly_rate)

        # Note: is_active e verified sono gestiti via toggle AJAX, non dal form

        # Handle table types and amenities
        table_types_str = request.form.get("table_types", "")
        table_types = [t.strip() for t in table_types_str.split(",") if t.strip()]
        if table_types:
            update_kwargs["table_types"] = table_types

        amenities_str = request.form.get("amenities", "")
        amenities = [a.strip() for a in amenities_str.split(",") if a.strip()]
        if amenities:
            update_kwargs["amenities"] = amenities

        try:
            LocationService.update_billiard_hall(venue_id, **update_kwargs)
            flash("Sala biliardo aggiornata con successo!", "success")
            return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))
        except Exception as e:
            flash(f"Errore nell'aggiornamento: {e}", "error")

    return render_template("admin/venue_form.html", venue=venue)


@venue_bp.route("/venues/<int:venue_id>/delete", methods=["POST"])
@admin_required
def delete_venue(venue_id):
    """Disattiva sala biliardo (soft delete)"""
    return handle_service_action(
        action=lambda: LocationService.set_venue_active(venue_id, False),
        redirect_url=url_for("admin.venue.venues_list"),
        success_message="Sala biliardo disattivata.",
        error_prefix=None,
    )


@venue_bp.route("/venues/<int:venue_id>/activate", methods=["POST"])
@admin_required
def activate_venue(venue_id):
    """Attiva sala biliardo"""
    return handle_service_action(
        action=lambda: LocationService.set_venue_active(venue_id, True),
        redirect_url=url_for("admin.venue.venues_list"),
        success_message="Sala biliardo attivata.",
        error_prefix=None,
    )


@venue_bp.route("/venues/<int:venue_id>/toggle", methods=["POST"])
@admin_required
def toggle_venue_status(venue_id):
    """API AJAX per cambiare stato venue (is_active o verified)"""
    from flask import jsonify

    data = request.get_json()
    field = data.get("field") if data else None
    raw_value = data.get("value") if data else None

    if field not in ["is_active", "verified"]:
        return jsonify({"success": False, "message": "Campo non valido"}), 400

    # Coercizione esplicita a bool: la colonna e' Boolean e una stringa
    # ('false') o None passati cosi' com'erano finivano in TypeError al
    # commit (500) o NULL nel campo.
    if isinstance(raw_value, bool):
        value = raw_value
    elif isinstance(raw_value, str) and raw_value.strip().lower() in ("true", "1"):
        value = True
    elif isinstance(raw_value, str) and raw_value.strip().lower() in ("false", "0"):
        value = False
    else:
        # Solo true/false espliciti: una stringa qualsiasi ("maybe") NON deve
        # diventare False e disattivare la sala.
        return jsonify({"success": False, "message": "Valore non valido"}), 400

    try:
        if field == "is_active":
            venue = LocationService.set_venue_active(venue_id, value)
            message = f"Sala '{venue.name}' {'attivata' if value else 'disattivata'}."
        else:
            venue = LocationService.set_venue_verified(venue_id, value)
            message = (
                f"Sala '{venue.name}' {'verificata' if value else 'non verificata'}."
            )

        return jsonify({"success": True, "message": message})

    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except Exception as e:
        return safe_json_error(e, "toggling venue status")


@venue_bp.route("/venues/<int:venue_id>/verify", methods=["POST"])
@venue_manager_required
def verify_venue(venue_id):
    """Verifica sala biliardo"""
    venue = db.get_or_404(BilliardHall, venue_id)

    new_verified = not venue.verified

    return handle_service_action(
        action=lambda: LocationService.set_venue_verified(venue_id, new_verified),
        redirect_url=url_for("admin.venue.venue_detail", venue_id=venue_id),
        success_message=(
            f"Sala biliardo ora è {'verificata' if new_verified else 'non verificata'}."
        ),
        error_prefix=None,
    )


@venue_bp.route("/venues/<int:venue_id>/table_numbers", methods=["POST"])
@venue_manager_required
def update_table_numbers(venue_id):
    """Aggiorna numerazione tavoli"""
    table_numbers = request.form.get("table_numbers", "")

    return handle_service_action(
        action=lambda: LocationService.update_venue_table_numbers(
            venue_id, table_numbers
        ),
        redirect_url=url_for("admin.venue.venue_detail", venue_id=venue_id),
        success_message="Numerazione tavoli aggiornata!",
        error_prefix=None,
    )


@venue_bp.route("/venues/<int:venue_id>/photo", methods=["POST"])
@venue_manager_required
def upload_photo(venue_id):
    """Carica foto per la sala biliardo"""
    db.get_or_404(BilliardHall, venue_id)  # 404 se la venue non esiste

    if "photo" not in request.files:
        flash("Nessuna foto selezionata", "error")
        return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))

    file = request.files["photo"]
    if file.filename == "":
        flash("Nessuna foto selezionata", "error")
        return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))

    if file and _allowed_file(file.filename):
        try:
            filename = secure_filename(
                f"venue_{venue_id}_{utc_now().strftime('%Y%m%d_%H%M%S')}"
                f"_{file.filename}"
            )

            # Use centralized image path management
            from utils.image_paths import ImagePathManager

            # Create upload directory if it doesn't exist
            ImagePathManager.ensure_venue_upload_dir()
            upload_dir = ImagePathManager.get_venue_upload_dir()

            file_path = os.path.join(upload_dir, filename)

            # Resize and optimize image (file I/O — not DB-related)
            _resize_and_save_image(file, file_path)

            # Update venue photo in DB via service
            venue_db_path = ImagePathManager.get_venue_db_path(filename)
            LocationService.update_venue_photo(venue_id, venue_db_path)

            flash("Foto caricata e ridimensionata con successo!", "success")
        except Exception as e:
            flash(f"Errore nel caricamento foto: {e}", "error")
    else:
        flash("Formato file non supportato. Usa JPG, PNG o GIF.", "error")

    return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))


@venue_bp.route("/venues/names")
@admin_required
def venue_names_api():
    """API per i nomi delle venue (per la datalist delle location esistenti)."""
    venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )
    venue_names = [venue.name for venue in venues]

    from flask import jsonify

    return jsonify(venue_names)


def _resize_and_save_image(file, save_path, max_size=(400, 300), quality=80):
    """Resize and save image with optimization."""
    try:
        # Open image
        image = Image.open(file.stream)

        # Convert RGBA to RGB if necessary (for JPEG)
        if image.mode in ("RGBA", "P"):
            # Create a white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
            image = background

        # Auto-rotate based on EXIF data
        image = ImageOps.exif_transpose(image)

        # Resize image maintaining aspect ratio
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Determine format and save
        format_mapping = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".gif": "GIF"}

        file_ext = os.path.splitext(save_path)[1].lower()
        save_format = format_mapping.get(file_ext, "JPEG")

        # Save with optimization
        if save_format == "JPEG":
            image.save(save_path, format=save_format, quality=quality, optimize=True)
        elif save_format == "PNG":
            image.save(save_path, format=save_format, optimize=True)
        else:
            image.save(save_path, format=save_format)

    except Exception as e:
        # Fallback to regular save if image processing fails
        file.seek(0)  # Reset file pointer
        with open(save_path, "wb") as f:
            f.write(file.read())
        raise e


def _allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUESTS MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────────


@venue_bp.route("/manager-requests")
@admin_required
def venue_manager_requests():
    """Lista delle richieste per diventare gestori di sale"""
    requests = VenueManagerService.get_pending_venue_manager_requests()
    return render_template("admin/venue_manager_requests.html", requests=requests)


@venue_bp.route("/manager-requests/<int:request_id>/process", methods=["POST"])
@admin_required
def process_venue_manager_request(request_id):
    """Processa (approva/rifiuta) una richiesta di gestore sala"""
    action = request.form.get("action")  # approve or reject
    admin_notes = request.form.get("admin_notes", "").strip()

    try:
        from flask_login import current_user

        admin_user = cast(User, current_user)
        if action == "approve":
            VenueManagerService.process_venue_manager_request(
                request_id, admin_user, True, admin_notes
            )
            flash("Richiesta approvata con successo!", "success")
        elif action == "reject":
            VenueManagerService.process_venue_manager_request(
                request_id, admin_user, False, admin_notes
            )
            flash("Richiesta rifiutata.", "info")
        else:
            flash("Azione non valida.", "error")
    except Exception as e:
        flash(f"Errore nel processare la richiesta: {str(e)}", "error")

    return redirect(url_for("admin.venue.venue_manager_requests"))


@venue_bp.route("/<int:venue_id>/assign-manager", methods=["POST"])
@admin_required
def assign_venue_manager(venue_id):
    """Assegna un gestore a una sala"""
    user_id = request.form.get("user_id")
    if not user_id:
        flash("Seleziona un utente da assegnare come gestore.", "error")
        return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))

    from flask_login import current_user

    return handle_service_action(
        action=lambda: VenueManagementService.assign_venue_manager(
            int(user_id), venue_id, cast(User, current_user)
        ),
        redirect_url=url_for("admin.venue.venue_detail", venue_id=venue_id),
        success_message="Gestore assegnato con successo!",
    )


@venue_bp.route("/assignments/<int:assignment_id>/revoke", methods=["POST"])
@admin_required
def revoke_venue_manager(assignment_id):
    """Revoca l'assegnazione di un gestore sala"""
    try:
        from flask_login import current_user

        admin_user = cast(User, current_user)
        assignment = VenueManagementService.revoke_venue_manager(
            assignment_id, admin_user
        )
        flash("Gestione sala revocata con successo!", "success")
        return redirect(
            url_for("admin.venue.venue_detail", venue_id=assignment.venue_id)
        )
    except Exception as e:
        flash(f"Errore nel revocare la gestione: {str(e)}", "error")
        return redirect(url_for("admin.venue.venues_list"))
