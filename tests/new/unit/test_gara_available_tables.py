"""Unit tests for Gara available_tables feature.

Tests the ability to specify specific tables for a gara,
instead of just using the venue's tables.

Feature: Gara-specific table configuration
Date: 2025-12-27
"""

import json
from datetime import date, timedelta

import pytest
from models.competition.models import Gara
from models.location.models import BilliardHall


class TestGaraParseTablesInput:
    """Tests for Gara.parse_tables_input() static method."""

    def test_comma_separated_numbers(self):
        """Parse simple comma-separated table numbers."""
        result = Gara.parse_tables_input("2,3,5")
        assert result == ["2", "3", "5"]

    def test_comma_separated_with_spaces(self):
        """Parse comma-separated with spaces around values."""
        result = Gara.parse_tables_input("2, 3, 5")
        assert result == ["2", "3", "5"]

    def test_multiple_spaces_and_alphanumeric(self):
        """Parse with multiple spaces and alphanumeric names."""
        result = Gara.parse_tables_input("2,  a,      7  , 1")
        assert result == ["2", "a", "7", "1"]

    def test_single_number_as_count(self):
        """Single number is interpreted as table count 1-N."""
        result = Gara.parse_tables_input("5")
        assert result == ["1", "2", "3", "4", "5"]

    def test_single_digit_1(self):
        """Single digit 1 returns just table 1."""
        result = Gara.parse_tables_input("1")
        assert result == ["1"]

    def test_empty_string(self):
        """Empty string returns empty list."""
        result = Gara.parse_tables_input("")
        assert result == []

    def test_whitespace_only(self):
        """Whitespace only returns empty list."""
        result = Gara.parse_tables_input("   ")
        assert result == []

    def test_none_input(self):
        """None input returns empty list."""
        result = Gara.parse_tables_input(None)
        assert result == []

    def test_room_names(self):
        """Parse full room names with spaces."""
        result = Gara.parse_tables_input("Sala Rossa, Sala Blu")
        assert result == ["Sala Rossa", "Sala Blu"]

    def test_mixed_alphanumeric(self):
        """Parse mixed alphanumeric table names."""
        result = Gara.parse_tables_input("1, A, 2, B")
        assert result == ["1", "A", "2", "B"]

    def test_zero_count(self):
        """Zero as count returns empty list."""
        result = Gara.parse_tables_input("0")
        assert result == []

    def test_leading_trailing_spaces(self):
        """Handles leading/trailing spaces in input."""
        result = Gara.parse_tables_input("  2, 3, 5  ")
        assert result == ["2", "3", "5"]


class TestGaraGetAvailableTables:
    """Tests for Gara.get_available_tables() method."""

    def test_returns_parsed_json_when_set(self, db_session):
        """Returns parsed JSON list when available_tables is set."""
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
        )
        gara.available_tables = json.dumps(["2", "3", "5"])
        db_session.add(gara)
        db_session.commit()

        result = gara.get_available_tables()
        assert result == ["2", "3", "5"]

    def test_returns_empty_when_none(self, db_session):
        """Returns empty list when available_tables is None."""
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
        )
        gara.available_tables = None
        db_session.add(gara)
        db_session.commit()

        # Without venue, should return empty
        result = gara.get_available_tables()
        assert result == []

    def test_fallback_to_venue_tables(self, db_session):
        """Falls back to venue tables when available_tables is None."""
        tomorrow = date.today() + timedelta(days=1)

        # Create venue with tables
        venue = BilliardHall(
            name="Test Venue Tables",
            number_of_tables=3,
        )
        db_session.add(venue)
        db_session.commit()

        # Create gara linked to venue via location string
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            location="Test Venue Tables",
        )
        gara.available_tables = None
        db_session.add(gara)
        db_session.commit()

        result = gara.get_available_tables()
        assert result == ["1", "2", "3"]

    def test_gara_tables_override_venue(self, db_session):
        """Gara-specific tables override venue tables."""
        tomorrow = date.today() + timedelta(days=1)

        # Create venue with 5 tables
        venue = BilliardHall(
            name="Test Venue Override",
            number_of_tables=5,
        )
        db_session.add(venue)
        db_session.commit()

        # Create gara with specific tables (only 2, 3, 5)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
            location="Test Venue Override",
        )
        gara.available_tables = json.dumps(["2", "3", "5"])
        db_session.add(gara)
        db_session.commit()

        result = gara.get_available_tables()
        assert result == ["2", "3", "5"]


class TestGaraSetAvailableTables:
    """Tests for Gara.set_available_tables() method."""

    def test_stores_as_json(self, db_session):
        """Stores table list as JSON string."""
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
        )
        db_session.add(gara)
        db_session.commit()

        gara.set_available_tables(["2", "3", "5"])

        assert gara.available_tables == '["2", "3", "5"]'

    def test_stores_none_for_empty_list(self, db_session):
        """Stores None for empty list."""
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
        )
        gara.available_tables = '["1", "2"]'  # Pre-set
        db_session.add(gara)
        db_session.commit()

        gara.set_available_tables([])

        assert gara.available_tables is None

    def test_roundtrip(self, db_session):
        """Set and get returns same values."""
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            date=tomorrow,
            discipline="palla 9",
            distance=7,
        )
        db_session.add(gara)
        db_session.commit()

        tables = ["A", "B", "Sala Rossa"]
        gara.set_available_tables(tables)

        result = gara.get_available_tables()
        assert result == tables
