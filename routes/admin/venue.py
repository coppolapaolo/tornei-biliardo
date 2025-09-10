# routes/admin/venue.py
"""Venue management blueprint for admin interface."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from PIL import Image, ImageOps

from models import BilliardHall
from models.location.services import LocationService
from utils import admin_required
from models.base import db

# Venue management blueprint
venue_bp = Blueprint("venue", __name__)


@venue_bp.route("/venues")
@admin_required
def venues_list():
    """Lista di tutte le sale biliardo (integrata con sistema location esistente)"""
    venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    # Get statistics for each venue
    venues_with_stats = []
    for venue in venues:
        try:
            stats = LocationService.get_location_statistics(venue.id)
            venues_with_stats.append({"venue": venue, "stats": stats})
        except Exception:
            # Fallback if stats fail
            venues_with_stats.append(
                {
                    "venue": venue,
                    "stats": {
                        "active_users_count": 0,
                        "total_matches_played": 0,
                        "reviews_count": 0,
                        "average_rating": 0,
                    },
                }
            )

    return render_template(
        "admin/venues_list.html", venues_with_stats=venues_with_stats
    )


@venue_bp.route("/venue/<int:venue_id>")
@admin_required
def venue_detail(venue_id):
    """Scheda dettagliata sala biliardo"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

    # Get venue statistics
    try:
        stats = LocationService.get_location_statistics(venue_id)
        reviews = LocationService.get_location_reviews(venue_id)
    except Exception:
        stats = {
            "active_users_count": 0,
            "total_matches_played": 0,
            "reviews_count": 0,
            "average_rating": 0,
            "table_types": [],
            "amenities": [],
        }
        reviews = []

    return render_template(
        "admin/venue_detail.html", venue=venue, stats=stats, reviews=reviews
    )


@venue_bp.route("/venue/new", methods=["GET", "POST"])
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
            )

            # Set business hours if provided
            if business_hours:
                venue.business_hours = business_hours
                db.session.commit()

            flash("Sala biliardo creata con successo!", "success")
            return redirect(url_for("admin.venue.venue_detail", venue_id=venue.id))

        except ValueError as e:
            flash(f"Errore nella creazione: {e}", "error")
        except Exception as e:
            flash(f"Errore imprevisto: {e}", "error")

    return render_template("admin/venue_form.html", venue=None)


@venue_bp.route("/venue/<int:venue_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_venue(venue_id):
    """Modifica sala biliardo"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

    if request.method == "POST":
        # Get form data
        update_data = {
            "name": request.form.get("name"),
            "address": request.form.get("address"),
            "city": request.form.get("city"),
            "postal_code": request.form.get("postal_code"),
            "phone": request.form.get("phone"),
            "email": request.form.get("email"),
            "website": request.form.get("website"),
            "business_hours": request.form.get("business_hours"),
        }

        # Handle numeric fields
        number_of_tables = request.form.get("number_of_tables")
        if number_of_tables:
            update_data["number_of_tables"] = int(number_of_tables)

        hourly_rate = request.form.get("hourly_rate")
        if hourly_rate:
            update_data["hourly_rate"] = float(hourly_rate)

        # Handle table types and amenities
        table_types_str = request.form.get("table_types", "")
        table_types = [t.strip() for t in table_types_str.split(",") if t.strip()]
        if table_types:
            update_data["table_types"] = table_types

        amenities_str = request.form.get("amenities", "")
        amenities = [a.strip() for a in amenities_str.split(",") if a.strip()]
        if amenities:
            update_data["amenities"] = amenities

        try:
            LocationService.update_billiard_hall(venue_id, **update_data)
            flash("Sala biliardo aggiornata con successo!", "success")
            return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))
        except Exception as e:
            flash(f"Errore nell'aggiornamento: {e}", "error")

    return render_template("admin/venue_form.html", venue=venue)


@venue_bp.route("/venue/<int:venue_id>/delete", methods=["POST"])
@admin_required
def delete_venue(venue_id):
    """Disattiva sala biliardo (soft delete)"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

    try:
        venue.is_active = False
        db.session.commit()
        flash(f"Sala biliardo '{venue.name}' disattivata.", "success")
    except Exception as e:
        flash(f"Errore nella disattivazione: {e}", "error")

    return redirect(url_for("admin.venue.venues_list"))


@venue_bp.route("/venue/<int:venue_id>/verify", methods=["POST"])
@admin_required
def verify_venue(venue_id):
    """Verifica sala biliardo"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

    try:
        venue.verified = not venue.verified
        db.session.commit()
        status = "verificata" if venue.verified else "non verificata"
        flash(f"Sala biliardo '{venue.name}' ora è {status}.", "success")
    except Exception as e:
        flash(f"Errore nella modifica dello stato: {e}", "error")

    return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))


@venue_bp.route("/venue/<int:venue_id>/table_numbers", methods=["POST"])
@admin_required
def update_table_numbers(venue_id):
    """Aggiorna numerazione tavoli"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

    table_numbers = request.form.get("table_numbers", "")

    try:
        # Store table numbers as JSON in amenities or create a new field
        # For now, we'll store it as a special amenity entry
        current_amenities = venue.get_amenities()

        # Remove existing table number entries
        current_amenities = [
            a for a in current_amenities if not a.startswith("Tavoli:")
        ]

        # Add new table numbers
        if table_numbers.strip():
            current_amenities.append(f"Tavoli: {table_numbers}")

        venue.set_amenities(current_amenities)
        db.session.commit()

        flash("Numerazione tavoli aggiornata!", "success")
    except Exception as e:
        flash(f"Errore nell'aggiornamento: {e}", "error")

    return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))


@venue_bp.route("/venue/<int:venue_id>/photo", methods=["POST"])
@admin_required
def upload_photo(venue_id):
    """Carica foto per la sala biliardo"""
    venue = db.session.get(BilliardHall, venue_id)
    if not venue:
        from flask import abort

        abort(404)

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
                f"venue_{venue_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            )

            # Create upload directory if it doesn't exist
            upload_dir = os.path.join("static", "uploads", "venues")
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, filename)

            # Resize and optimize image
            _resize_and_save_image(file, file_path)

            # Store photo path in amenities for now
            current_amenities = venue.get_amenities()

            # Remove existing photo entries
            current_amenities = [
                a for a in current_amenities if not a.startswith("Foto:")
            ]

            # Add new photo path
            current_amenities.append(f"Foto: uploads/venues/{filename}")
            venue.set_amenities(current_amenities)
            db.session.commit()

            flash("Foto caricata e ridimensionata con successo!", "success")
        except Exception as e:
            flash(f"Errore nel caricamento foto: {e}", "error")
    else:
        flash("Formato file non supportato. Usa JPG, PNG o GIF.", "error")

    return redirect(url_for("admin.venue.venue_detail", venue_id=venue_id))


@venue_bp.route("/venues/names")
@admin_required
def venue_names_api():
    """API endpoint per ottenere nomi delle venue (per integrare con datalist location esistenti)"""
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
        format_mapping = {
            '.jpg': 'JPEG',
            '.jpeg': 'JPEG', 
            '.png': 'PNG',
            '.gif': 'GIF'
        }
        
        file_ext = os.path.splitext(save_path)[1].lower()
        save_format = format_mapping.get(file_ext, 'JPEG')
        
        # Save with optimization
        if save_format == 'JPEG':
            image.save(save_path, format=save_format, quality=quality, optimize=True)
        elif save_format == 'PNG':
            image.save(save_path, format=save_format, optimize=True)
        else:
            image.save(save_path, format=save_format)
            
    except Exception as e:
        # Fallback to regular save if image processing fails
        file.seek(0)  # Reset file pointer
        with open(save_path, 'wb') as f:
            f.write(file.read())
        raise e


def _allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
