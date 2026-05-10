"""Tests for tiebreaker limit logic."""

import pytest
from unittest.mock import MagicMock, patch
from models.competition.spareggio_service import SpareggioService

@patch("models.competition.spareggio_service.db")
def test_detect_tiebreakers_respects_limit(mock_db):
    """Should only detect tiebreakers within the specified limit."""
    mock_gara = MagicMock()
    mock_gara.current_round = 3
    mock_gara.rounds_count = 3
    mock_gara.tiebreaker_enabled = True
    mock_gara.tiebreaker_until_position = 2  # Only top 2
    # B20: SpareggioService now keys on (matches_won, rack_difference) for WINS;
    # tests must populate matches_won for proper tuple comparison.
    mock_gara.classification_system = "WINS"
    mock_db.session.get.return_value = mock_gara

    # Create mock classifications:
    # 1: P1 (3w/20)
    # 2: P2 (2w/18)
    # 3: P3 (1w/15) - Tied
    # 4: P4 (1w/15) - Tied
    mock_class1 = MagicMock()
    mock_class1.user_id = 1
    mock_class1.matches_won = 3
    mock_class1.rack_difference = 20

    mock_class2 = MagicMock()
    mock_class2.user_id = 2
    mock_class2.matches_won = 2
    mock_class2.rack_difference = 18

    mock_class3 = MagicMock()
    mock_class3.user_id = 3
    mock_class3.matches_won = 1
    mock_class3.rack_difference = 15

    mock_class4 = MagicMock()
    mock_class4.user_id = 4
    mock_class4.matches_won = 1
    mock_class4.rack_difference = 15

    mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [
        mock_class1, mock_class2, mock_class3, mock_class4
    ]
    mock_db.session.query.return_value.filter.return_value.all.return_value = []

    # Detect tiebreakers with limit = 2
    result = SpareggioService.detect_tiebreakers(1)
    
    # Position 3 tie should be ignored because limit is 2
    assert len(result) == 0

    # Change limit to 3
    mock_gara.tiebreaker_until_position = 3
    result = SpareggioService.detect_tiebreakers(1)
    
    # Now it should detect the tie at position 3
    assert len(result) == 1
    assert result[0]["position"] == 3
