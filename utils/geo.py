"""Geographic helpers for proximity discovery (ADR-034).

No external dependencies and no network: a haversine distance, a bounding-box
pre-filter suitable for a plain SQLite ``BETWEEN`` query, a radius clamp, and a
city-centroid fallback (approximate an origin from known venue coordinates when
the user has no GPS fix).
"""

from __future__ import annotations

from math import radians, sin, cos, asin, sqrt
from typing import Iterable, Optional, Tuple

# Mean Earth radius (km). Good enough for "near me" ranking.
EARTH_RADIUS_KM = 6371.0088

# Product defaults (ADR-034): 20 km default, 100 km hard cap.
DEFAULT_RADIUS_KM = 20
MAX_RADIUS_KM = 100

# Approximate km per degree of latitude (roughly constant).
_KM_PER_DEG_LAT = 111.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    rlat1, rlng1, rlat2, rlng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def bounding_box(
    lat: float, lng: float, radius_km: float
) -> Tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lng, max_lng) covering the radius.

    A cheap pre-filter for SQLite: select rows whose lat/lng fall in this box,
    then refine with :func:`haversine_km`. The box is slightly larger than the
    circle (it circumscribes it), so it never excludes a real match.
    """
    lat_delta = radius_km / _KM_PER_DEG_LAT
    # Longitude degrees shrink with latitude; guard against the poles.
    cos_lat = max(cos(radians(lat)), 0.01)
    lng_delta = radius_km / (_KM_PER_DEG_LAT * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


def clamp_radius(
    radius_km, default: int = DEFAULT_RADIUS_KM, maximum: int = MAX_RADIUS_KM
) -> int:
    """Coerce a user-supplied radius to a sane int within [1, maximum]."""
    try:
        value = int(radius_km)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


def city_centroid(
    coords: Iterable[Tuple[Optional[float], Optional[float]]]
) -> Optional[Tuple[float, float]]:
    """Average of the given (lat, lng) points, ignoring None pairs.

    Used as a network-free fallback origin: the centroid of the known venue
    coordinates in the user's home city. Returns None if no usable point.
    """
    points = [
        (la, ln) for la, ln in coords if la is not None and ln is not None
    ]
    if not points:
        return None
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)
