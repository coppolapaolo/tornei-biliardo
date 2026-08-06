"""Unit tests for utils/geo.py proximity helpers (ADR-034)."""

import pytest

from utils.geo import (
    haversine_km,
    bounding_box,
    clamp_radius,
    city_centroid,
    DEFAULT_RADIUS_KM,
    MAX_RADIUS_KM,
)


class TestHaversine:
    def test_zero_distance_same_point(self):
        assert haversine_km(46.07, 13.23, 46.07, 13.23) == pytest.approx(0.0, abs=1e-9)

    def test_known_distance_udine_trieste(self):
        # Udine (~46.07, 13.23) to Trieste (~45.65, 13.77): ~62 km as the crow flies
        d = haversine_km(46.0711, 13.2346, 45.6495, 13.7768)
        assert d == pytest.approx(62.0, abs=6.0)

    def test_symmetric(self):
        a = haversine_km(45.0, 7.0, 45.5, 7.5)
        b = haversine_km(45.5, 7.5, 45.0, 7.0)
        assert a == pytest.approx(b, abs=1e-9)


class TestBoundingBox:
    def test_contains_center(self):
        lat, lng = 45.0, 9.0
        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, 20)
        assert min_lat < lat < max_lat
        assert min_lng < lng < max_lng

    def test_box_circumscribes_circle(self):
        # A point exactly at the radius distance (due north) must be inside the box.
        lat, lng, radius = 45.0, 9.0, 20.0
        min_lat, max_lat, _, _ = bounding_box(lat, lng, radius)
        north_lat = lat + radius / 111.0
        assert min_lat <= north_lat <= max_lat

    def test_wider_radius_wider_box(self):
        small = bounding_box(45.0, 9.0, 10)
        big = bounding_box(45.0, 9.0, 50)
        assert (big[1] - big[0]) > (small[1] - small[0])


class TestClampRadius:
    def test_default_on_none(self):
        assert clamp_radius(None) == DEFAULT_RADIUS_KM

    def test_default_on_garbage(self):
        assert clamp_radius("abc") == DEFAULT_RADIUS_KM

    def test_default_on_zero_or_negative(self):
        assert clamp_radius(0) == DEFAULT_RADIUS_KM
        assert clamp_radius(-5) == DEFAULT_RADIUS_KM

    def test_caps_at_maximum(self):
        assert clamp_radius(99999) == MAX_RADIUS_KM

    def test_passes_through_valid(self):
        assert clamp_radius(35) == 35

    def test_accepts_numeric_string(self):
        assert clamp_radius("42") == 42


class TestCityCentroid:
    def test_empty_returns_none(self):
        assert city_centroid([]) is None

    def test_all_none_returns_none(self):
        assert city_centroid([(None, None), (None, 9.0)]) is None

    def test_average(self):
        c = city_centroid([(45.0, 9.0), (47.0, 11.0)])
        assert c == pytest.approx((46.0, 10.0))

    def test_ignores_partial_none(self):
        c = city_centroid([(45.0, 9.0), (None, None)])
        assert c == pytest.approx((45.0, 9.0))
