"""Unit tests for CampionatoFormParser.parse_default_settings.

Single source of truth for the 'default gare settings' block shared by the
creation wizard and the edit handler. Invalid/empty inputs must fall back to
safe defaults (so neither route can 500 on a malformed field).
"""

import pytest
from werkzeug.datastructures import MultiDict

from routes.admin.campionato_form_parser import CampionatoFormParser


@pytest.mark.unit
class TestParseDefaultSettings:
    def test_valid_values(self):
        form = MultiDict(
            {
                "default_venue_id": "7",
                "default_entry_fee": "12.5",
                "default_rounds_count": "4",
                "default_odd_policy": "trio",
                "default_anti_rematch": "on",
            }
        )
        result = CampionatoFormParser.parse_default_settings(form)
        assert result == {
            "default_venue_id": 7,
            "default_entry_fee": 12.5,
            "default_rounds_count": 4,
            "default_odd_policy": "trio",
            "default_anti_rematch": True,
            "has_handicap": False,
        }

    def test_empty_form_uses_safe_defaults(self):
        result = CampionatoFormParser.parse_default_settings(MultiDict())
        assert result == {
            "default_venue_id": None,
            "default_entry_fee": None,
            "default_rounds_count": 3,
            "default_odd_policy": "bye",
            "default_anti_rematch": False,
            "has_handicap": False,
        }

    def test_invalid_numeric_inputs_fall_back(self):
        form = MultiDict(
            {
                "default_venue_id": "abc",
                "default_entry_fee": "x",
                "default_rounds_count": "not-a-number",
            }
        )
        result = CampionatoFormParser.parse_default_settings(form)
        assert result["default_venue_id"] is None
        assert result["default_entry_fee"] is None
        assert result["default_rounds_count"] == 3

    def test_rounds_count_below_one_falls_back(self):
        form = MultiDict({"default_rounds_count": "0"})
        assert (
            CampionatoFormParser.parse_default_settings(form)["default_rounds_count"]
            == 3
        )

    def test_unknown_odd_policy_falls_back_to_bye(self):
        form = MultiDict({"default_odd_policy": "bogus"})
        assert (
            CampionatoFormParser.parse_default_settings(form)["default_odd_policy"]
            == "bye"
        )

    def test_anti_rematch_absent_is_false(self):
        form = MultiDict({"default_rounds_count": "3"})
        assert (
            CampionatoFormParser.parse_default_settings(form)["default_anti_rematch"]
            is False
        )
