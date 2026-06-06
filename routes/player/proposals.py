# routes/player/proposals.py
"""Player availability system routes (Use Case 7).

Le proposte di match individuali vivono nel blueprint `individual_match`
(/match/proposals*); questo file conserva solo il sistema di disponibilità
giocatore, non ancora migrato a quel blueprint.
"""

from datetime import datetime

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from models import db, User
from models.location.models import BilliardHall
from utils import player_required

from . import player_bp


# ====================================================================
# AVAILABILITY SYSTEM ROUTES - Use Case 7
# ====================================================================


@player_bp.route("/availability")
@login_required
@player_required
def availability_preferences():
    """Manage player availability preferences"""
    from models.individual_match.availability_service import AvailabilityService

    preferences = AvailabilityService.get_user_availability_preferences(current_user.id)
    venues = BilliardHall.query.filter_by(is_active=True).all()

    return render_template(
        "player/availability_preferences.html", preferences=preferences, venues=venues
    )


@player_bp.route("/availability/location", methods=["POST"])
@login_required
@player_required
def set_location_availability():
    """Set availability for a specific location"""
    from models.individual_match.availability_service import AvailabilityService

    location = request.form.get("location", "").strip()
    is_available = request.form.get("is_available") == "true"
    preferred_days = request.form.getlist("preferred_days")
    preferred_times = request.form.get("preferred_times", "").strip()

    if not location:
        flash("La location è obbligatoria", "danger")
        return redirect(url_for("player.availability_preferences"))

    try:
        # Convert day strings to integers
        day_ints = [int(d) for d in preferred_days if d.isdigit()]

        AvailabilityService.set_player_availability(
            user_id=current_user.id,
            location=location,
            is_available=is_available,
            preferred_days=day_ints if day_ints else None,
            preferred_times=preferred_times if preferred_times else None,
        )

        flash(f"Disponibilità aggiornata per {location}", "success")

        # If setting availability, optionally notify other players
        if is_available and request.form.get("notify_players") == "true":
            notifications_sent = AvailabilityService.notify_players_of_availability(
                user_id=current_user.id, location=location
            )
            if notifications_sent > 0:
                flash(
                    f"Notificati {notifications_sent} giocatori "
                    "della tua disponibilità",
                    "info",
                )

    except Exception as e:
        flash(f"Errore nell'aggiornare la disponibilità: {str(e)}", "danger")

    return redirect(url_for("player.availability_preferences"))


@player_bp.route("/availability/venue", methods=["POST"])
@login_required
@player_required
def set_venue_availability():
    """Set availability for a specific venue"""
    from models.individual_match.availability_service import AvailabilityService

    venue_id = request.form.get("venue_id", type=int)
    is_available = request.form.get("is_available") == "true"
    available_days = request.form.getlist("available_days")
    preferred_times = request.form.get("preferred_times", "").strip()

    if not venue_id:
        flash("Devi selezionare una sala", "danger")
        return redirect(url_for("player.availability_preferences"))

    try:
        # Convert day strings to integers
        day_ints = [int(d) for d in available_days if d.isdigit()]

        AvailabilityService.set_venue_availability(
            user_id=current_user.id,
            billiard_hall_id=venue_id,
            is_available=is_available,
            available_days=day_ints if day_ints else None,
            preferred_times=preferred_times if preferred_times else None,
        )

        venue = db.session.get(BilliardHall, venue_id)
        venue_name = venue.name if venue else f"Sala #{venue_id}"
        flash(f"Disponibilità aggiornata per {venue_name}", "success")

    except Exception as e:
        flash(f"Errore nell'aggiornare la disponibilità: {str(e)}", "danger")

    return redirect(url_for("player.availability_preferences"))


@player_bp.route("/availability/discover")
@login_required
@player_required
def discover_available_players():
    """Discover players available at various locations"""
    from models.individual_match.availability_service import AvailabilityService

    # Get location filter from query params
    location_filter = request.args.get("location", "").strip()
    venue_filter = request.args.get("venue_id", type=int)

    available_players = {}

    if location_filter:
        # Get players available at specific location
        players = AvailabilityService.get_available_players_at_location(
            location=location_filter, exclude_user_id=current_user.id
        )
        available_players[location_filter] = players

    elif venue_filter:
        # Get players available at specific venue
        players = AvailabilityService.get_available_players_at_venue(
            billiard_hall_id=venue_filter, exclude_user_id=current_user.id
        )
        venue = db.session.get(BilliardHall, venue_filter)
        venue_name = venue.name if venue else f"Sala #{venue_filter}"
        available_players[venue_name] = players

    else:
        # Get all locations with available players
        from models.individual_match.models import PlayerAvailability
        from models.location.models import UserLocationAvailability

        # Get all locations with available players
        locations = (
            db.session.query(PlayerAvailability.location)
            .filter(
                PlayerAvailability.is_available.is_(True),
                PlayerAvailability.user_id != current_user.id,
            )
            .distinct()
            .all()
        )

        for (location,) in locations:
            players = AvailabilityService.get_available_players_at_location(
                location=location, exclude_user_id=current_user.id
            )
            if players:
                available_players[location] = players

        # Get all venues with available players
        venues = (
            db.session.query(
                UserLocationAvailability.billiard_hall_id, BilliardHall.name
            )
            .join(BilliardHall)
            .filter(
                UserLocationAvailability.is_available.is_(True),
                UserLocationAvailability.user_id != current_user.id,
            )
            .distinct()
            .all()
        )

        for venue_id, venue_name in venues:
            players = AvailabilityService.get_available_players_at_venue(
                billiard_hall_id=venue_id, exclude_user_id=current_user.id
            )
            if players:
                available_players[venue_name] = players

    venues = BilliardHall.query.filter_by(is_active=True).all()

    return render_template(
        "player/discover_players.html",
        available_players=available_players,
        venues=venues,
        location_filter=location_filter,
        venue_filter=venue_filter,
    )


@player_bp.route("/availability/request_match/<int:target_user_id>", methods=["POST"])
@login_required
@player_required
def request_availability_match(target_user_id):
    """Request a match with an available player"""
    from models.individual_match.availability_service import AvailabilityService

    location = request.form.get("location", "").strip()
    message = request.form.get("message", "").strip()
    proposed_date = request.form.get("proposed_date")
    proposed_time = request.form.get("proposed_time")

    if not location:
        flash("La location è obbligatoria per richiedere un match", "danger")
        return redirect(url_for("player.discover_available_players"))

    # Parse proposed datetime
    proposed_datetime = None
    if proposed_date and proposed_time:
        try:
            proposed_datetime = datetime.strptime(
                f"{proposed_date} {proposed_time}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            flash("Formato data/ora non valido", "danger")
            return redirect(url_for("player.discover_available_players"))

    try:
        AvailabilityService.create_availability_based_match_request(
            requesting_user_id=current_user.id,
            target_user_id=target_user_id,
            location=location,
            proposed_datetime=proposed_datetime,
            message=message,
        )

        target_user = db.session.get(User, target_user_id)
        target_name = (
            target_user.username if target_user else f"Utente #{target_user_id}"
        )

        flash(f"Richiesta di match inviata a {target_name}", "success")

    except Exception as e:
        flash(f"Errore nell'inviare la richiesta: {str(e)}", "danger")

    return redirect(url_for("player.discover_available_players"))
