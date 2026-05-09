"""TDD tests for race-to-n score validation.

Tests the business rule that in a "race to n" match, both players
cannot have n (or more) points simultaneously - this is logically
impossible since the match ends when the first player reaches n.
"""

import pytest
from unittest.mock import MagicMock

from models.match.scoring_service import ScoringService


class TestRaceToScoreValidation:
    """Tests for _validate_score_limits with race-to-n matches."""

    def _create_mock_match(self, distance: int, is_race_to: bool):
        """Crea mock match con Distance VO sul match (ADR-027).

        Lo scoring legge `match.distance_config` (non `match.gara.distance`),
        per rispettare gli override per turno. Il mock fornisce direttamente
        un Distance reale.
        """
        from models.match.distance import Distance

        real_distance = Distance(
            racks=distance,
            is_race_to_racks=is_race_to,
            is_multi_set=False,
        )

        mock_gara = MagicMock()
        mock_gara.distance = distance
        mock_gara.is_race_to = is_race_to
        mock_gara.distance_config = real_distance

        mock_match = MagicMock()
        mock_match.gara = mock_gara
        mock_match.distance_config = real_distance
        return mock_match

    def test_race_to_5_rejects_5_5_score(self):
        """In race-to-5, score 5-5 is impossible (match ends at first 5)."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, 5, 5)

        assert "entrambi i giocatori" in str(exc_info.value).lower()

    def test_race_to_5_rejects_5_6_score(self):
        """In race-to-5, score 5-6 is rejected (exceeds max first)."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, 5, 6)

        # Score 6 exceeds max (5), so "superare" error comes first
        assert "superare" in str(exc_info.value).lower()

    def test_race_to_5_accepts_5_4_score(self):
        """In race-to-5, score 5-4 is valid (player1 wins)."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        # Should not raise
        ScoringService._validate_score_limits(match, 5, 4)

    def test_race_to_5_accepts_4_5_score(self):
        """In race-to-5, score 4-5 is valid (player2 wins)."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        # Should not raise
        ScoringService._validate_score_limits(match, 4, 5)

    def test_race_to_5_accepts_3_3_score(self):
        """In race-to-5, score 3-3 is valid (match in progress)."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        # Should not raise
        ScoringService._validate_score_limits(match, 3, 3)

    def test_race_to_3_rejects_3_3_score(self):
        """In race-to-3, score 3-3 is impossible."""
        match = self._create_mock_match(distance=3, is_race_to=True)

        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, 3, 3)

        assert "entrambi i giocatori" in str(exc_info.value).lower()

    def test_exact_mode_allows_equal_scores_when_total_equals_distance(self):
        """Exact mode (not race-to): equal scores valid when total=distance."""
        match = self._create_mock_match(distance=6, is_race_to=False)

        # In exact mode with distance=6, score 3-3 (total=6) is a valid tie result
        ScoringService._validate_score_limits(match, 3, 3)

    def test_exact_mode_rejects_invalid_total(self):
        """In 'exact' mode, total racks must equal distance."""
        match = self._create_mock_match(distance=7, is_race_to=False)

        # In exact mode with distance=7, score 3-3 (total=6) is invalid
        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, 3, 3)

        assert "esatto numero" in str(exc_info.value).lower()
        assert "6" in str(exc_info.value)  # Actual total
        assert "7" in str(exc_info.value)  # Expected total

    def test_negative_scores_rejected(self):
        """Negative scores are always rejected."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, -1, 3)

        assert "negativi" in str(exc_info.value).lower()

    def test_score_exceeding_distance_rejected(self):
        """Scores exceeding distance are rejected."""
        match = self._create_mock_match(distance=5, is_race_to=True)

        with pytest.raises(ValueError) as exc_info:
            ScoringService._validate_score_limits(match, 6, 3)

        assert "superare" in str(exc_info.value).lower()
