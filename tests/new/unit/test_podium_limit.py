"""Tests for podium limit logic."""

from unittest.mock import MagicMock, patch
from models.competition.models import Gara, GaraStatus


@patch("models.classification.services.RoundClassificationService.get_round_standings")
def test_get_podium_respects_limit(mock_get_standings):
    """Should only return podium players within the specified limit."""
    # Create a real Gara object
    gara = Gara()
    gara.id = 1
    gara.status = GaraStatus.COMPLETED.value
    gara.rounds_count = 3
    gara.tiebreaker_until_position = 2  # Limit set to 2

    # Mock standings
    mock_rc1 = MagicMock()
    mock_rc1.position = 1
    mock_rc1.user = MagicMock(username="player1")

    mock_rc2 = MagicMock()
    mock_rc2.position = 2
    mock_rc2.user = MagicMock(username="player2")

    mock_rc3 = MagicMock()
    mock_rc3.position = 3
    mock_rc3.user = MagicMock(username="player3")

    mock_get_standings.return_value = [mock_rc1, mock_rc2, mock_rc3]

    # Get podium
    podium = gara.get_podium()

    # Should only have 2 players
    assert len(podium) == 2
    assert podium[0]["username"] == "player1"
    assert podium[1]["username"] == "player2"

    # Change limit to 3
    gara.tiebreaker_until_position = 3
    podium = gara.get_podium()

    # Should now have 3 players
    assert len(podium) == 3
    assert podium[2]["username"] == "player3"
