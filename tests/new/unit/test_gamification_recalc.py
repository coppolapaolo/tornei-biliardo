# tests/new/unit/test_gamification_recalc.py
"""Unit tests for the pure streak logic of GamificationRecalcService."""

from datetime import date

from models.gamification.recalc_service import GamificationRecalcService


def _streak(dates):
    return GamificationRecalcService._streak_from_dates(dates)


def test_streak_empty():
    assert _streak([]) == (0, 0, None)


def test_streak_consecutive_weeks():
    # Three consecutive Mondays → current=3, longest=3.
    dates = [date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19)]
    current, longest, last = _streak(dates)
    assert current == 3
    assert longest == 3
    assert last == date(2026, 1, 19)


def test_streak_same_week_counts_once():
    # Two activities in the same ISO week → streak of 1.
    dates = [date(2026, 1, 5), date(2026, 1, 8)]
    current, longest, _ = _streak(dates)
    assert current == 1
    assert longest == 1


def test_streak_gap_breaks_current_but_keeps_longest():
    # Weeks 1,2,3 then a gap then a single recent week.
    dates = [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 2, 16),  # gap → resets current run
    ]
    current, longest, last = _streak(dates)
    assert longest == 3
    assert current == 1
    assert last == date(2026, 2, 16)
