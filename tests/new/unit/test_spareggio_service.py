"""Tests for SpareggioService - SSR tiebreaker resolution."""

import pytest
from unittest.mock import MagicMock, patch

from models.competition.spareggio_service import SpareggioService


class TestSpareggioServiceValidation:
    """Tests for SSR score validation logic."""

    def test_validate_ssr_scores_valid(self):
        """Valid SSR scores should pass validation."""
        scores = {1: 5, 2: 3, 3: 1}
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        assert is_valid is True
        assert error == ""

    def test_validate_ssr_scores_empty(self):
        """Empty scores should fail validation."""
        is_valid, error = SpareggioService.validate_ssr_scores({})
        assert is_valid is False
        assert "Nessun punteggio" in error

    def test_validate_ssr_scores_zero(self):
        """Zero scores are valid - player didn't pocket any balls in SSR."""
        scores = {1: 5, 2: 0, 3: 1}
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        assert is_valid is True
        assert error == ""

    def test_validate_ssr_scores_negative(self):
        """Negative scores should fail validation."""
        scores = {1: 5, 2: -1, 3: 1}
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        assert is_valid is False
        assert "non negativi" in error

    def test_validate_ssr_scores_duplicate(self):
        """Duplicate scores should fail validation."""
        scores = {1: 5, 2: 5, 3: 1}
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        assert is_valid is False
        assert "tutti diversi" in error

    def test_validate_ssr_scores_non_integer(self):
        """Non-integer scores should fail validation."""
        scores = {1: 5.5, 2: 3, 3: 1}  # type: ignore
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        assert is_valid is False
        assert "non negativi" in error


class TestSpareggioServiceDetection:
    """Tests for tiebreaker detection logic."""

    @patch("models.competition.spareggio_service.db")
    def test_detect_tiebreakers_no_gara(self, mock_db):
        """Should return empty list if gara not found."""
        mock_db.session.get.return_value = None
        result = SpareggioService.detect_tiebreakers(999)
        assert result == []

    @patch("models.competition.spareggio_service.db")
    def test_detect_tiebreakers_no_classifications(self, mock_db):
        """Should return empty list if no classifications exist."""
        mock_gara = MagicMock()
        mock_gara.current_round = 3
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []

        result = SpareggioService.detect_tiebreakers(1)
        assert result == []

    @patch("models.competition.spareggio_service.db")
    def test_detect_tiebreakers_no_ties_in_top_3(self, mock_db):
        """Should return empty list if no ties in top 3."""
        mock_gara = MagicMock()
        mock_gara.current_round = 3
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        # Create mock classifications with no ties in top 3
        mock_class1 = MagicMock()
        mock_class1.user_id = 1
        mock_class1.rack_difference = 20
        mock_class1.user = MagicMock(display_name="Player 1")

        mock_class2 = MagicMock()
        mock_class2.user_id = 2
        mock_class2.rack_difference = 18
        mock_class2.user = MagicMock(display_name="Player 2")

        mock_class3 = MagicMock()
        mock_class3.user_id = 3
        mock_class3.rack_difference = 15
        mock_class3.user = MagicMock(display_name="Player 3")

        # Each position has unique rack count = no ties
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [
            mock_class1, mock_class2, mock_class3
        ]
        # Mock GaraClassification query to return empty (no existing SSR scores)
        mock_db.session.query.return_value.filter.return_value.all.return_value = []

        result = SpareggioService.detect_tiebreakers(1)
        assert result == []

    @patch("models.competition.spareggio_service.db")
    def test_detect_tiebreakers_tie_for_first(self, mock_db):
        """Should detect tie for first place."""
        mock_gara = MagicMock()
        mock_gara.current_round = 3
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        # Create mock classifications with tie for 1st place
        mock_class1 = MagicMock()
        mock_class1.user_id = 1
        mock_class1.rack_difference = 20  # Tied
        mock_class1.user = MagicMock(display_name="Player 1")

        mock_class2 = MagicMock()
        mock_class2.user_id = 2
        mock_class2.rack_difference = 20  # Tied
        mock_class2.user = MagicMock(display_name="Player 2")

        mock_class3 = MagicMock()
        mock_class3.user_id = 3
        mock_class3.rack_difference = 15
        mock_class3.user = MagicMock(display_name="Player 3")

        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [
            mock_class1, mock_class2, mock_class3
        ]
        # No existing GaraClassification entries
        mock_db.session.query.return_value.filter.return_value.all.return_value = []

        result = SpareggioService.detect_tiebreakers(1)

        assert len(result) == 1
        assert result[0]["position"] == 1
        assert result[0]["rack_totali"] == 20
        assert len(result[0]["players"]) == 2

    @patch("models.competition.spareggio_service.db")
    def test_detect_tiebreakers_tie_for_third(self, mock_db):
        """Should detect tie for third place."""
        mock_gara = MagicMock()
        mock_gara.current_round = 3
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        # Create mock classifications with tie for 3rd place
        mock_class1 = MagicMock()
        mock_class1.user_id = 1
        mock_class1.rack_difference = 20
        mock_class1.user = MagicMock(display_name="Player 1")

        mock_class2 = MagicMock()
        mock_class2.user_id = 2
        mock_class2.rack_difference = 18
        mock_class2.user = MagicMock(display_name="Player 2")

        mock_class3 = MagicMock()
        mock_class3.user_id = 3
        mock_class3.rack_difference = 15  # Tied for 3rd
        mock_class3.user = MagicMock(display_name="Player 3")

        mock_class4 = MagicMock()
        mock_class4.user_id = 4
        mock_class4.rack_difference = 15  # Tied for 3rd
        mock_class4.user = MagicMock(display_name="Player 4")

        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [
            mock_class1, mock_class2, mock_class3, mock_class4
        ]
        mock_db.session.query.return_value.filter.return_value.all.return_value = []

        result = SpareggioService.detect_tiebreakers(1)

        assert len(result) == 1
        assert result[0]["position"] == 3
        assert result[0]["rack_totali"] == 15
        assert len(result[0]["players"]) == 2


class TestSpareggioServiceHasUnresolved:
    """Tests for has_unresolved_tiebreakers method."""

    @patch.object(SpareggioService, "detect_tiebreakers")
    def test_has_unresolved_true(self, mock_detect):
        """Should return True when tiebreakers exist."""
        mock_detect.return_value = [{"position": 1, "players": []}]
        assert SpareggioService.has_unresolved_tiebreakers(1) is True

    @patch.object(SpareggioService, "detect_tiebreakers")
    def test_has_unresolved_false(self, mock_detect):
        """Should return False when no tiebreakers exist."""
        mock_detect.return_value = []
        assert SpareggioService.has_unresolved_tiebreakers(1) is False


class TestSpareggioServiceRandomStrategyRound:
    """Regression tests: SSR tiebreaker must use max(Match.round_number),
    not gara.current_round, for Random strategy gare where all rounds
    are created at startup and current_round may lag behind."""

    @patch("models.competition.spareggio_service.db")
    @patch("models.competition.spareggio_service.Match")
    def test_detect_tiebreakers_uses_max_round_not_current_round(
        self, mock_match_cls, mock_db
    ):
        """When current_round=2 but matches exist up to round 3,
        detect_tiebreakers should query classification for round 3."""
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.current_round = 2  # Stale - lags behind
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        # _get_effective_final_round queries func.max(Match.round_number)
        # Mock the chain: db.session.query(func.max(...)).filter(...).scalar()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.scalar.return_value = 3  # Max round from matches
        mock_query.filter.return_value = mock_filter

        # filter_by is used for RoundClassification query
        mock_filter_by = MagicMock()
        mock_filter_by.order_by.return_value.all.return_value = []
        mock_query.filter_by.return_value = mock_filter_by

        mock_db.session.query.return_value = mock_query

        SpareggioService.detect_tiebreakers(1)

        # Verify filter_by was called with round_number=3 (not 2)
        mock_query.filter_by.assert_called_with(
            gara_id=1, round_number=3
        )

    @patch("models.competition.spareggio_service.db")
    @patch("models.competition.spareggio_service.Match")
    def test_get_all_ssr_groups_uses_max_round(self, mock_match_cls, mock_db):
        """get_all_ssr_groups should also use max(Match.round_number)."""
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.current_round = 2  # Stale
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.scalar.return_value = 3
        mock_query.filter.return_value = mock_filter

        mock_filter_by = MagicMock()
        mock_filter_by.order_by.return_value.all.return_value = []
        mock_query.filter_by.return_value = mock_filter_by

        mock_db.session.query.return_value = mock_query

        SpareggioService.get_all_ssr_groups(1)

        mock_query.filter_by.assert_called_with(
            gara_id=1, round_number=3
        )

    @patch("models.competition.spareggio_service.db")
    @patch("models.competition.spareggio_service.Match")
    def test_fallback_when_no_matches_exist(self, mock_match_cls, mock_db):
        """When no matches exist, should fall back to current_round/rounds_count."""
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.current_round = 0
        mock_gara.rounds_count = 3
        mock_gara.tiebreaker_enabled = True
        mock_gara.tiebreaker_until_position = 3
        mock_db.session.get.return_value = mock_gara

        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.scalar.return_value = None  # No matches
        mock_query.filter.return_value = mock_filter

        mock_filter_by = MagicMock()
        mock_filter_by.order_by.return_value.all.return_value = []
        mock_query.filter_by.return_value = mock_filter_by

        mock_db.session.query.return_value = mock_query

        SpareggioService.detect_tiebreakers(1)

        # Should fall back to rounds_count=3 (since current_round=0 is falsy)
        mock_query.filter_by.assert_called_with(
            gara_id=1, round_number=3
        )
