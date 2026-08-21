"""Player availability and discovery routes for individual matches.

Consolidated home of the player-availability surface (location string +
billiard-hall venue) and player discovery. Previously this lived as a
separate, partly-broken set of routes on the ``player`` blueprint
(``routes/player/proposals.py``); it was unified here onto
``AvailabilityService`` as the single source of truth.

See docs/adr/ADR-032-availability-surface-consolidation.md.
"""

from flask import render_template, request, redirect, url_for, flash
from flask_babel import _
from flask_login import current_user

from models.base import db
from models.individual_match.availability_service import AvailabilityService
from models.location.models import BilliardHall
from models.user.models import User
from models.user.permissions import RoleRequirement
from utils.geo import clamp_radius, haversine_km
from utils.local_time import parse_local_datetime
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
    """Discover players and open proposals, ranked by proximity (ADR-034).

    Venue-only after ADR-033. Proximity origin = browser GPS (``near_lat``/
    ``near_lng``) or, as fallback, the centroid of venues in the user's
    ``home_city``. Proximity only sorts/filters; it never changes eligibility.
    """
    venue_filter = request.args.get("venue_id", type=int)
    near_lat = request.args.get("near_lat", type=float)
    near_lng = request.args.get("near_lng", type=float)
    radius_km = clamp_radius(request.args.get("radius_km"))

    active_venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    venue_groups: list = []
    placeless_groups: list = []
    near_proposals = None
    proximity_active = False
    proximity_origin = None

    if venue_filter:
        venue = db.session.get(BilliardHall, venue_filter)
        name = venue.name if venue else _("Sala #%(id)s", id=venue_filter)
        players = AvailabilityService.get_available_players_at_venue(
            billiard_hall_id=venue_filter, exclude_user_id=current_user.id
        )
        venue_groups.append({"name": name, "distance_km": None, "players": players})
    else:
        origin = _resolve_origin(near_lat, near_lng)
        venues = AvailabilityService.get_venues_with_available_players(
            exclude_user_id=current_user.id
        )
        if origin:
            proximity_active = True
            (lat, lng), proximity_origin = origin
            with_coords = []
            for v in venues:
                if v["latitude"] is not None and v["longitude"] is not None:
                    dist = haversine_km(lat, lng, v["latitude"], v["longitude"])
                    if dist <= radius_km:
                        with_coords.append((dist, v))
                else:
                    placeless_groups.append(
                        {"name": v["venue_name"], "players": v["players"]}
                    )
            with_coords.sort(key=lambda t: t[0])
            venue_groups = [
                {
                    "name": v["venue_name"],
                    "distance_km": round(dist, 1),
                    "players": v["players"],
                }
                for dist, v in with_coords
            ]
            near_proposals = _open_proposals_near(lat, lng, radius_km)
        else:
            venue_groups = [
                {
                    "name": v["venue_name"],
                    "distance_km": None,
                    "players": v["players"],
                }
                for v in venues
            ]

    return render_template(
        "individual_match/discover_players.html",
        venue_groups=venue_groups,
        placeless_groups=placeless_groups,
        near_proposals=near_proposals,
        proximity_active=proximity_active,
        proximity_origin=proximity_origin,
        radius_km=radius_km,
        active_venues=active_venues,
        venue_filter=venue_filter,
        has_home_city=bool(getattr(current_user, "home_city", None)),
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

    # Data e ora arrivano dal modulo di scoperta in **due campi separati**,
    # scritti da chi guarda l'orologio della sua città. Il DB tiene i naive
    # come UTC e `|datetime_local` in lettura ci risomma il fuso: uno
    # `strptime` diretto salvava la stringa grezza e spostava l'appuntamento di
    # tutto il fuso, in silenzio — le 21:00 diventavano le 23:00 a Roma
    # (ADR-043, la stessa correzione già fatta sul modulo della proposta).
    #
    # `parse_local_datetime` legge un `datetime-local`, quindi i due campi si
    # rimettono insieme con la T in mezzo. Torna `None` sul malformato invece
    # di sollevare, e la risposta all'utente resta quella di prima.
    proposed_datetime = None
    if proposed_date and proposed_time:
        proposed_datetime = parse_local_datetime(f"{proposed_date}T{proposed_time}")
        if proposed_datetime is None:
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


def _resolve_origin(near_lat, near_lng):
    """Return ((lat, lng), source) or None. source in {'gps', 'city'}.

    Browser GPS wins; otherwise fall back to the centroid of venues in the
    user's self-declared home city (network-free, ADR-034).
    """
    if near_lat is not None and near_lng is not None:
        return ((near_lat, near_lng), "gps")
    home_city = getattr(current_user, "home_city", None)
    if home_city:
        centroid = AvailabilityService.city_centroid_for(home_city)
        if centroid:
            return (centroid, "city")
    return None


def _open_proposals_near(lat, lng, radius_km):
    """Eligible open proposals (ADR-033) within radius, sorted by venue distance.

    Eligibility is unchanged: we only rank/filter what the user can already see.
    """
    from models.individual_match.proposal_service import ProposalService

    proposals = ProposalService.get_user_proposals(current_user.id).get(
        "open_proposals", []
    )
    ranked = []
    for proposal in proposals:
        venue = proposal.billiard_hall
        if venue and venue.latitude is not None and venue.longitude is not None:
            dist = haversine_km(lat, lng, venue.latitude, venue.longitude)
            if dist <= radius_km:
                ranked.append({"proposal": proposal, "distance_km": round(dist, 1)})
    ranked.sort(key=lambda r: r["distance_km"])
    return ranked
