"""Player availability and discovery routes for individual matches.

Consolidated home of the player-availability surface (location string +
billiard-hall venue) and player discovery. Previously this lived as a
separate, partly-broken set of routes on the ``player`` blueprint
(``routes/player/proposals.py``); it was unified here onto
``AvailabilityService`` as the single source of truth.

See docs/adr/ADR-032-availability-surface-consolidation.md.
"""

from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_babel import _
from flask_login import current_user

from models.base import db
from models.individual_match.availability_service import AvailabilityService
from models.individual_match.models import PlayerAvailability
from models.location.models import BilliardHall, UserLocationAvailability
from models.user.models import User
from models.user.permissions import RoleRequirement

from . import individual_match_bp


def _wants_json() -> bool:
    """True when the caller expects a JSON response (AJAX or JSON body)."""
    return request.is_json or (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


@individual_match_bp.route("/availability")
@RoleRequirement.player_or_director_required
def manage_availability():
    """Manage player availability (location strings + billiard-hall venues)."""
    preferences = AvailabilityService.get_user_availability_preferences(current_user.id)
    active_venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    return render_template(
        "individual_match/availability.html",
        locations=preferences["locations"],
        venues=preferences["venues"],
        active_venues=active_venues,
    )


@individual_match_bp.route("/availability/location", methods=["POST"])
@RoleRequirement.player_or_director_required
def set_location_availability():
    """Set or update availability for a free-text location."""
    data = request.get_json() if request.is_json else request.form

    location = (data.get("location") or "").strip()
    is_available = str(data.get("is_available", "true")).lower() in ("true", "on", "1")
    preferred_times = (data.get("preferred_times") or "").strip()
    if hasattr(data, "getlist"):
        preferred_days = data.getlist("preferred_days")
    else:
        preferred_days = data.get("preferred_days") or []

    if not location:
        return _availability_error(
            _("La località è obbligatoria"),
            redirect_endpoint="individual_match.manage_availability",
        )

    day_ints = [int(d) for d in preferred_days if str(d).isdigit()]

    AvailabilityService.set_player_availability(
        user_id=current_user.id,
        location=location,
        is_available=is_available,
        preferred_days=day_ints or None,
        preferred_times=preferred_times or None,
    )

    notified = 0
    if is_available and str(data.get("notify_players", "")).lower() in (
        "true",
        "on",
        "1",
    ):
        notified = AvailabilityService.notify_players_of_availability(
            user_id=current_user.id, location=location
        )

    if _wants_json():
        return jsonify({"success": True, "notified": notified})

    flash(_("Disponibilità aggiornata per %(loc)s", loc=location), "success")
    if notified:
        flash(
            _("Notificati %(n)s giocatori della tua disponibilità", n=notified),
            "info",
        )
    return redirect(url_for("individual_match.manage_availability"))


@individual_match_bp.route("/availability/venue", methods=["POST"])
@RoleRequirement.player_or_director_required
def set_venue_availability():
    """Set or update availability for a specific billiard hall (venue)."""
    data = request.get_json() if request.is_json else request.form

    venue_id = data.get("venue_id")
    try:
        venue_id = int(venue_id) if venue_id not in (None, "") else None
    except (TypeError, ValueError):
        venue_id = None

    is_available = str(data.get("is_available", "true")).lower() in ("true", "on", "1")
    preferred_times = (data.get("preferred_times") or "").strip()
    if hasattr(data, "getlist"):
        available_days = data.getlist("available_days")
    else:
        available_days = data.get("available_days") or []

    if not venue_id:
        return _availability_error(
            _("Devi selezionare una sala"),
            redirect_endpoint="individual_match.manage_availability",
        )

    day_ints = [int(d) for d in available_days if str(d).isdigit()]

    AvailabilityService.set_venue_availability(
        user_id=current_user.id,
        billiard_hall_id=venue_id,
        is_available=is_available,
        available_days=day_ints or None,
        preferred_times=preferred_times or None,
    )

    venue = db.session.get(BilliardHall, venue_id)
    venue_name = venue.name if venue else _("Sala #%(id)s", id=venue_id)

    if _wants_json():
        return jsonify({"success": True})

    flash(_("Disponibilità aggiornata per %(loc)s", loc=venue_name), "success")
    return redirect(url_for("individual_match.manage_availability"))


@individual_match_bp.route(
    "/availability/location/<int:availability_id>/remove", methods=["POST"]
)
@RoleRequirement.player_or_director_required
def remove_location_availability(availability_id):
    """Delete a location-based availability record owned by the current user."""
    removed = AvailabilityService.remove_player_availability(
        user_id=current_user.id, availability_id=availability_id
    )
    return _availability_remove_response(removed)


@individual_match_bp.route(
    "/availability/venue/<int:availability_id>/remove", methods=["POST"]
)
@RoleRequirement.player_or_director_required
def remove_venue_availability(availability_id):
    """Delete a venue-based availability record owned by the current user."""
    removed = AvailabilityService.remove_venue_availability(
        user_id=current_user.id, availability_id=availability_id
    )
    return _availability_remove_response(removed)


@individual_match_bp.route("/availability/discover")
@RoleRequirement.player_or_director_required
def discover_players():
    """Discover players available at locations and venues."""
    location_filter = request.args.get("location", "").strip()
    venue_filter = request.args.get("venue_id", type=int)

    available_players: dict = {}

    if location_filter:
        available_players[location_filter] = (
            AvailabilityService.get_available_players_at_location(
                location=location_filter, exclude_user_id=current_user.id
            )
        )
    elif venue_filter:
        venue = db.session.get(BilliardHall, venue_filter)
        venue_name = venue.name if venue else _("Sala #%(id)s", id=venue_filter)
        available_players[venue_name] = (
            AvailabilityService.get_available_players_at_venue(
                billiard_hall_id=venue_filter, exclude_user_id=current_user.id
            )
        )
    else:
        available_players = _discover_everywhere()

    active_venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    return render_template(
        "individual_match/discover_players.html",
        available_players=available_players,
        active_venues=active_venues,
        location_filter=location_filter,
        venue_filter=venue_filter,
    )


@individual_match_bp.route(
    "/availability/request-match/<int:target_user_id>", methods=["POST"]
)
@RoleRequirement.player_or_director_required
def request_availability_match(target_user_id):
    """Send a direct match request to a player discovered via availability."""
    data = request.get_json() if request.is_json else request.form

    location = (data.get("location") or "").strip()
    message = (data.get("message") or "").strip()
    proposed_date = data.get("proposed_date")
    proposed_time = data.get("proposed_time")

    if not location:
        return _availability_error(
            _("La località è obbligatoria per richiedere un match"),
            redirect_endpoint="individual_match.discover_players",
        )

    proposed_datetime = None
    if proposed_date and proposed_time:
        try:
            proposed_datetime = datetime.strptime(
                f"{proposed_date} {proposed_time}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            return _availability_error(
                _("Formato data/ora non valido"),
                redirect_endpoint="individual_match.discover_players",
            )

    try:
        AvailabilityService.create_availability_based_match_request(
            requesting_user_id=current_user.id,
            target_user_id=target_user_id,
            location=location,
            proposed_datetime=proposed_datetime,
            message=message or None,
        )
    except ValueError as exc:
        return _availability_error(
            str(exc), redirect_endpoint="individual_match.discover_players"
        )

    target = db.session.get(User, target_user_id)
    target_name = target.username if target else _("Utente #%(id)s", id=target_user_id)

    if _wants_json():
        return jsonify({"success": True})

    flash(_("Richiesta di match inviata a %(name)s", name=target_name), "success")
    return redirect(url_for("individual_match.discover_players"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _availability_error(message: str, redirect_endpoint: str):
    """Return a JSON 400 or a flashed redirect depending on the request type."""
    if _wants_json():
        return jsonify({"success": False, "error": message}), 400
    flash(message, "danger")
    return redirect(url_for(redirect_endpoint))


def _availability_remove_response(removed: bool):
    """Shared response for the two remove endpoints."""
    if not removed:
        if _wants_json():
            return jsonify({"success": False, "error": _("Record non trovato")}), 404
        flash(_("Disponibilità non trovata"), "warning")
        return redirect(url_for("individual_match.manage_availability"))

    if _wants_json():
        return jsonify({"success": True})
    flash(_("Disponibilità rimossa"), "success")
    return redirect(url_for("individual_match.manage_availability"))


def _discover_everywhere() -> dict:
    """Build the discovery map across every location and venue with players."""
    available_players: dict = {}

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

    venues = (
        db.session.query(UserLocationAvailability.billiard_hall_id, BilliardHall.name)
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

    return available_players
