"""Unit tests for MatchStatus state predicates (models/status_enum.py).

These predicates replace scattered raw-literal status checks
(`status in ["completed", "validated"]`) with a single typo-safe helper.
"""

import pytest

from models.status_enum import MatchStatus


@pytest.mark.unit
class TestMatchStatusPredicates:
    def test_finished_values(self):
        assert set(MatchStatus.finished_values()) == {"completed", "validated"}

    @pytest.mark.parametrize("status", ["completed", "validated"])
    def test_is_finished_true(self, status):
        assert MatchStatus.is_finished(status) is True

    @pytest.mark.parametrize(
        "status", ["pending", "playing", "in_progress", "scheduled", "cancelled"]
    )
    def test_is_finished_false(self, status):
        assert MatchStatus.is_finished(status) is False

    def test_active_values(self):
        assert set(MatchStatus.active_values()) == {"playing", "in_progress"}

    @pytest.mark.parametrize("status", ["playing", "in_progress"])
    def test_is_active_true(self, status):
        assert MatchStatus.is_active(status) is True

    @pytest.mark.parametrize(
        "status", ["completed", "validated", "pending", "scheduled"]
    )
    def test_is_active_false(self, status):
        assert MatchStatus.is_active(status) is False

    def test_predicates_accept_enum_member_value(self):
        """Predicates work with `.value` of enum members (typo-safe usage)."""
        assert MatchStatus.is_finished(MatchStatus.COMPLETED.value)
        assert MatchStatus.is_active(MatchStatus.PLAYING.value)
