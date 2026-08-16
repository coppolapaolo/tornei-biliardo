# routes/player/geo.py
"""Geographic matching routes for players.

Provides endpoints for:
- Finding competitions in user's area
- Getting user's location preferences
"""

from flask import jsonify
from flask_login import login_required, current_user

from models.location.geo_service import GeoMatchingService, get_province_name
from . import player_bp


@player_bp.route("/api/nearby-gare")
@login_required
def api_nearby_gare():
    """
    API endpoint to get gare near the user's locations.

    Returns JSON with gare that have open inscriptions in the user's provinces.
    """
    # Get user's provinces based on their availability settings
    provinces = GeoMatchingService.get_user_provinces(current_user.id)

    if not provinces:
        return jsonify(
            {
                "success": True,
                "gare": [],
                "provinces": [],
                "message": (
                    "Imposta le tue disponibilità nelle sale per vedere gare vicine"
                ),
            }
        )

    # Get gare with open inscriptions
    gare = GeoMatchingService.get_open_gare_nearby(current_user.id, limit=5)

    # Format for frontend
    gare_data = []
    for gara in gare:
        venue = gara.venue
        gare_data.append(
            {
                "id": gara.id,
                "name": gara.nome or f"Gara #{gara.number}",
                "date": gara.date.isoformat() if gara.date else None,
                "time": gara.time.strftime("%H:%M") if gara.time else None,
                "venue_name": venue.name if venue else gara.location_display,
                "city": venue.city if venue else None,
                "province": venue.province if venue else None,
                "province_name": (
                    get_province_name(venue.province)
                    if venue and venue.province
                    else None
                ),
                "inscription_end": (
                    gara.inscription_end.isoformat() if gara.inscription_end else None
                ),
                "current_inscriptions": gara.active_inscription_count,
                "max_participants": gara.max_participants,
            }
        )

    return jsonify(
        {
            "success": True,
            "gare": gare_data,
            "provinces": [
                {"code": p, "name": get_province_name(p)} for p in sorted(provinces)
            ],
        }
    )


@player_bp.route("/api/my-provinces")
@login_required
def api_my_provinces():
    """Get provinces where user has availability set."""
    provinces = GeoMatchingService.get_user_provinces(current_user.id)

    return jsonify(
        {
            "success": True,
            "provinces": [
                {"code": p, "name": get_province_name(p)} for p in sorted(provinces)
            ],
        }
    )
