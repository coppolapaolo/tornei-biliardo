"""Player availability and discovery routes for individual matches.

Consolidated home of the player-availability surface (location string +
billiard-hall venue) and player discovery. Previously this lived as a
separate, partly-broken set of routes on the ``player`` blueprint
(``routes/player/proposals.py``); it was unified here onto
``AvailabilityService`` as the single source of truth.

See docs/adr/ADR-032-availability-surface-consolidation.md.
"""

from datetime import datetime

from flask import render_template, request, redirect, url_for, flash
from flask_babel import _
from flask_login import current_user

from models.base import db
from models.individual_match.availability_service import AvailabilityService
from models.location.models import BilliardHall, UserLocationAvailability
from models.user.models import User
from models.user.permissions import RoleRequirement
from utils.route_helpers import ajax_error, ajax_success, is_ajax_request

from . import individual_match_bp

_TRUTHY = ("true", "on", "1")


def _wants_json() -> bool:
    """True when the caller expects a JSON response (AJAX or JSON body)."""
    return is_ajax_request() or request.is_json


def _form_bool(data, key: str, default: bool = False) -> bool:
    """Parse a checkbox/boolean field from form or JSON data."""
    raw = data.get(key)
    if raw is None:
        return default
    return str(raw).lower() in _TRUTHY


def _form_day_ints(data, key: str) -> list[int]:
    """Parse a multi-value day field (form getlist or JSON list) to ints."""
    if hasattr(data, "getlist"):
        values = data.getlist(key)
    else:
        values = data.get(key) or []
    return [int(d) for d in values if str(d).isdigit()]


@individual_match_bp.route("/availability")
@RoleRequirement.player_or_director_required
def manage_availability():
    """Manage player availability (billiard-hall venues, ADR-033)."""
    preferences = AvailabilityService.get_user_availability_preferences(current_user.id)
    active_venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    return render_template(
        "individual_match/availability.html",
        venues=preferences["venues"],
        active_venues=active_venues,
    )


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

    # Unchecked HTML checkboxes are omitted from the POST body, so a missing
    # value means "not available" (matches the form's switch semantics).
    is_available = _form_bool(data, "is_available", default=False)
    preferred_times = (data.get("preferred_times") or "").strip()
    day_ints = _form_day_ints(data, "available_days")

    if not venue_id:
        return _availability_error(
            _("Devi selezionare una sala"),
            redirect_endpoint="individual_match.manage_availability",
        )

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
        return ajax_success()

    flash(_("Disponibilità aggiornata per %(loc)s", loc=venue_name), "success")
    return redirect(url_for("individual_match.manage_availability"))


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
    """Discover players available at venues (ADR-033: venue-only)."""
    venue_filter = request.args.get("venue_id", type=int)

    available_players: dict = {}

    if venue_filter:
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
        return ajax_success()

    flash(_("Richiesta di match inviata a %(name)s", name=target_name), "success")
    return redirect(url_for("individual_match.discover_players"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _availability_error(message: str, redirect_endpoint: str):
    """Return a JSON 400 or a flashed redirect depending on the request type."""
    if _wants_json():
        return ajax_error(message)
    flash(message, "danger")
    return redirect(url_for(redirect_endpoint))


def _availability_remove_response(removed: bool):
    """Shared response for the two remove endpoints."""
    if not removed:
        if _wants_json():
            return ajax_error(_("Record non trovato"), status=404)
        flash(_("Disponibilità non trovata"), "warning")
        return redirect(url_for("individual_match.manage_availability"))

    if _wants_json():
        return ajax_success()
    flash(_("Disponibilità rimossa"), "success")
    return redirect(url_for("individual_match.manage_availability"))


def _discover_everywhere() -> dict:
    """Build the discovery map across every venue with available players."""
    available_players: dict = {}

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
