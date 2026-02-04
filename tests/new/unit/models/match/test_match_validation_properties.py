"""Test Match.is_at_distance and is_player_validated properties.

These properties are used to determine when the director validation button
should appear in the UI. The validation button should show when:
1. Distance has been reached (is_at_distance = True)
2. Not yet validated by admin (validated_by_admin = False)
3. Players haven't all confirmed yet (is_player_validated = False)
"""

from unittest.mock import MagicMock, PropertyMock


# --- is_at_distance tests ---


def test_race_to_5_at_distance_when_player1_reaches():
    """Race to 5: player1 has 5 racks → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 5
    match.player2_score = 3

    # Mock gara with race-to mode
    mock_gara = MagicMock()
    mock_gara.distance = 5
    mock_gara.is_race_to = True
    match.gara = mock_gara

    assert match.is_at_distance is True


def test_race_to_5_at_distance_when_player2_reaches():
    """Race to 5: player2 has 5 racks → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 4
    match.player2_score = 5

    mock_gara = MagicMock()
    mock_gara.distance = 5
    mock_gara.is_race_to = True
    match.gara = mock_gara

    assert match.is_at_distance is True


def test_race_to_5_not_at_distance():
    """Race to 5: neither player reached 5 → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 4
    match.player2_score = 3

    mock_gara = MagicMock()
    mock_gara.distance = 5
    mock_gara.is_race_to = True
    match.gara = mock_gara

    assert match.is_at_distance is False


def test_exactly_8_at_distance_with_tie():
    """Exactly 8: total is 8 with tie (4-4) → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 4
    match.player2_score = 4

    mock_gara = MagicMock()
    mock_gara.distance = 8
    mock_gara.is_race_to = False
    match.gara = mock_gara

    assert match.is_at_distance is True


def test_exactly_8_at_distance_with_winner():
    """Exactly 8: total is 8 with winner (5-3) → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 5
    match.player2_score = 3

    mock_gara = MagicMock()
    mock_gara.distance = 8
    mock_gara.is_race_to = False
    match.gara = mock_gara

    assert match.is_at_distance is True


def test_exactly_8_not_at_distance():
    """Exactly 8: total less than 8 → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.player1_score = 3
    match.player2_score = 2

    mock_gara = MagicMock()
    mock_gara.distance = 8
    mock_gara.is_race_to = False
    match.gara = mock_gara

    assert match.is_at_distance is False


def test_standalone_match_uses_defaults():
    """Standalone match (no gara): uses default distance=5, is_race_to=True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.gara = None  # Standalone
    match.player1_score = 5
    match.player2_score = 3

    assert match.is_at_distance is True


def test_standalone_match_not_at_distance():
    """Standalone match (no gara): not at distance yet"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.gara = None  # Standalone
    match.player1_score = 4
    match.player2_score = 3

    assert match.is_at_distance is False


def test_trio_at_distance():
    """Trio: all 6 racks played (distance=2, so 2 rounds × 3 = 6) → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    # Mock trio_match with trio_config
    mock_trio = MagicMock()
    mock_trio.total_racks_played = 6

    mock_config = MagicMock()
    mock_config.total_played_racks = 6
    type(mock_trio).trio_config = PropertyMock(return_value=mock_config)

    match.trio_match = mock_trio

    assert match.is_at_distance is True


def test_trio_not_at_distance():
    """Trio: only 4 racks played out of 6 → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.total_racks_played = 4

    mock_config = MagicMock()
    mock_config.total_played_racks = 6
    type(mock_trio).trio_config = PropertyMock(return_value=mock_config)

    match.trio_match = mock_trio

    assert match.is_at_distance is False


def test_trio_exactly_at_distance():
    """Trio: exactly at required racks → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.total_racks_played = 9  # distance=3 → 3 rounds × 3 = 9

    mock_config = MagicMock()
    mock_config.total_played_racks = 9
    type(mock_trio).trio_config = PropertyMock(return_value=mock_config)

    match.trio_match = mock_trio

    assert match.is_at_distance is True


# --- is_player_validated tests ---


def test_regular_match_player_validated_both_confirmed():
    """Regular match: both players confirmed → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.trio_match = None
    match.player1_confirmed = True
    match.player2_confirmed = True

    assert match.is_player_validated is True


def test_regular_match_player_validated_one_confirmed():
    """Regular match: only one player confirmed → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.trio_match = None
    match.player1_confirmed = True
    match.player2_confirmed = False

    assert match.is_player_validated is False


def test_regular_match_player_validated_none_confirmed():
    """Regular match: neither player confirmed → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = False
    match.trio_match = None
    match.player1_confirmed = False
    match.player2_confirmed = False

    assert match.is_player_validated is False


def test_trio_player_validated_all_confirmed():
    """Trio: all 3 players confirmed → True"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.player1_confirmed = True
    mock_trio.player2_confirmed = True
    mock_trio.player3_confirmed = True
    match.trio_match = mock_trio

    assert match.is_player_validated is True


def test_trio_player_validated_two_confirmed():
    """Trio: only 2 players confirmed → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.player1_confirmed = True
    mock_trio.player2_confirmed = True
    mock_trio.player3_confirmed = False
    match.trio_match = mock_trio

    assert match.is_player_validated is False


def test_trio_player_validated_one_confirmed():
    """Trio: only 1 player confirmed → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.player1_confirmed = True
    mock_trio.player2_confirmed = False
    mock_trio.player3_confirmed = False
    match.trio_match = mock_trio

    assert match.is_player_validated is False


def test_trio_player_validated_none_confirmed():
    """Trio: no players confirmed → False"""
    from models.match.models import Match

    match = Match()
    match.is_trio = True

    mock_trio = MagicMock()
    mock_trio.player1_confirmed = False
    mock_trio.player2_confirmed = False
    mock_trio.player3_confirmed = False
    match.trio_match = mock_trio

    assert match.is_player_validated is False
