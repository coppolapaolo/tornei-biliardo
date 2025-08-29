"""
Test module for models/match/set_models.py
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from models.match.set_models import Set, SetRack

# No unused imports needed


class TestSetModel:
    """Test cases for Set model."""

    def test_set_creation(self):
        """Test Set model creation."""
        set_obj = Set(match_id=1, set_number=1, distance=5, best_of=True)

        assert set_obj.match_id == 1
        assert set_obj.set_number == 1
        assert set_obj.distance == 5
        assert set_obj.best_of is True
        # Initialize default values that are set in the database model
        set_obj.status = "pending"
        set_obj.player1_racks = 0
        set_obj.player2_racks = 0
        assert set_obj.status == "pending"
        assert set_obj.player1_racks == 0
        assert set_obj.player2_racks == 0

    def test_can_be_modified(self):
        """Test can_be_modified method."""
        set_obj = Set(status="pending")
        assert not set_obj.can_be_modified()

        set_obj.status = "playing"
        assert set_obj.can_be_modified()

        set_obj.status = "completed"
        assert not set_obj.can_be_modified()

    def test_configure_multi_discipline(self):
        """Test configure_multi_discipline method."""
        set_obj = Set()

        # Test with insufficient disciplines
        with pytest.raises(ValueError):
            set_obj.configure_multi_discipline([])

        with pytest.raises(ValueError):
            set_obj.configure_multi_discipline(["discipline1"])

        # Test rotation mode
        disciplines = ["discipline1", "discipline2", "discipline3"]
        set_obj.configure_multi_discipline(disciplines, "rotation")
        assert set_obj.is_multi_discipline is True
        assert set_obj.discipline_rotation == disciplines
        assert set_obj.discipline_assignment is None

        # Test assignment mode
        set_obj.configure_multi_discipline(disciplines, "assignment")
        assert set_obj.is_multi_discipline is True
        assert set_obj.discipline_rotation == disciplines
        assert set_obj.discipline_assignment == {}

        # Test unsupported mode
        with pytest.raises(ValueError):
            set_obj.configure_multi_discipline(disciplines, "unsupported")

    def test_set_discipline_assignment(self):
        """Test set_discipline_assignment method."""
        set_obj = Set()
        set_obj.is_multi_discipline = True

        # Test setting discipline assignment
        rack_disciplines = {1: "discipline1", 2: "discipline2"}
        set_obj.set_discipline_assignment(rack_disciplines)
        assert set_obj.discipline_assignment == {"1": "discipline1", "2": "discipline2"}

        # Test with non-multi-discipline set
        set_obj.is_multi_discipline = False
        with pytest.raises(ValueError):
            set_obj.set_discipline_assignment(rack_disciplines)

    def test_get_discipline_for_rack(self):
        """Test get_discipline_for_rack method."""
        # Test non-multi-discipline set
        set_obj = Set()
        set_obj.is_multi_discipline = False
        set_obj.discipline = "palla_8"

        assert set_obj.get_discipline_for_rack(1) == "palla_8"

        # Test with assignment
        set_obj.is_multi_discipline = True
        set_obj.discipline_assignment = {"1": "discipline1", "2": "discipline2"}
        assert set_obj.get_discipline_for_rack(1) == "discipline1"
        assert set_obj.get_discipline_for_rack(2) == "discipline2"

        # Test with rotation
        set_obj.discipline_assignment = None
        set_obj.discipline_rotation = ["discipline1", "discipline2", "discipline3"]
        assert set_obj.get_discipline_for_rack(1) == "discipline1"
        assert set_obj.get_discipline_for_rack(2) == "discipline2"
        assert set_obj.get_discipline_for_rack(3) == "discipline3"
        assert set_obj.get_discipline_for_rack(4) == "discipline1"  # Should cycle back

    def test_get_discipline_summary(self):
        """Test get_discipline_summary method."""
        # Test non-multi-discipline set
        set_obj = Set()
        set_obj.is_multi_discipline = False
        set_obj.discipline = "palla_8"

        summary = set_obj.get_discipline_summary()
        assert summary["is_multi_discipline"] is False
        assert summary["primary_discipline"] == "palla_8"
        assert summary["disciplines_used"] == ["palla_8"]

        # Test multi-discipline set
        set_obj.is_multi_discipline = True
        set_obj.discipline_rotation = ["discipline1", "discipline2"]
        set_obj.discipline_assignment = {"1": "discipline1", "2": "discipline2"}

        # Mock racks
        mock_rack1 = MagicMock()
        mock_rack1.discipline_override = None
        mock_rack1.rack_number = 1

        mock_rack2 = MagicMock()
        mock_rack2.discipline_override = None
        mock_rack2.rack_number = 2

        set_obj.racks = [mock_rack1, mock_rack2]

        summary = set_obj.get_discipline_summary()
        assert summary["is_multi_discipline"] is True
        assert summary["rotation"] == ["discipline1", "discipline2"]
        assert summary["assignment"] == {"1": "discipline1", "2": "discipline2"}

    def test_start_set(self):
        """Test start_set method."""
        set_obj = Set(status="pending")

        # Test starting a pending set
        set_obj.start_set()
        assert set_obj.status == "playing"
        assert set_obj.started_at is not None
        assert isinstance(set_obj.started_at, datetime)

        # Test starting a non-pending set
        set_obj.status = "playing"
        with pytest.raises(ValueError):
            set_obj.start_set()

    @patch("models.match.set_models.db")
    def test_add_rack_result(self, mock_db):
        """Test add_rack_result method."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        set_obj = Set(
            status="playing",
            match=mock_match,
            distance=5,  # Set the distance attribute
            best_of=True,
            player1_racks=0,
            player2_racks=0,
        )
        set_obj.id = 1

        # Mock database query for max rack number
        mock_db.session.query.return_value.filter_by.return_value.scalar.return_value = (
            0
        )
        mock_db.session.add = MagicMock()

        # Test adding a rack result
        rack = set_obj.add_rack_result(winner_id=1)
        assert rack is not None
        assert set_obj.player1_racks == 1
        assert set_obj.player2_racks == 0
        mock_db.session.add.assert_called_once()

        # Test with invalid winner
        with pytest.raises(ValueError):
            set_obj.add_rack_result(winner_id=3)

        # Test with non-playing set
        set_obj.status = "pending"
        with pytest.raises(ValueError):
            set_obj.add_rack_result(winner_id=1)

    def test_check_set_completion_best_of(self):
        """Test _check_set_completion method with best_of=True."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        set_obj = Set(
            status="playing",
            match=mock_match,
            distance=3,
            best_of=True,
            player1_racks=3,
            player2_racks=1,
        )

        # Mock the _complete_set method
        set_obj._complete_set = MagicMock()

        # Test completion
        set_obj._check_set_completion()
        set_obj._complete_set.assert_called_once_with(1)

    def test_check_set_completion_fixed_distance(self):
        """Test _check_set_completion method with best_of=False."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        set_obj = Set(
            status="playing",
            match=mock_match,
            distance=5,
            best_of=False,
            player1_racks=3,
            player2_racks=2,
        )

        # Mock the _complete_set method
        set_obj._complete_set = MagicMock()

        # Test completion
        set_obj._check_set_completion()
        set_obj._complete_set.assert_called_once_with(1)

    def test_complete_set(self):
        """Test _complete_set method."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.complete_set = MagicMock()

        set_obj = Set(match=mock_match)
        set_obj._complete_set(winner_id=1)

        assert set_obj.status == "completed"
        assert set_obj.completed_at is not None
        assert isinstance(set_obj.completed_at, datetime)
        assert set_obj.winner_id == 1
        mock_match.complete_set.assert_called_once_with(set_obj.set_number, 1)

    def test_is_completed(self):
        """Test is_completed method."""
        set_obj = Set(status="pending")
        assert not set_obj.is_completed()

        set_obj.status = "completed"
        assert set_obj.is_completed()

    def test_get_score_summary(self):
        """Test get_score_summary method."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        set_obj = Set(
            set_number=1,
            distance=5,
            best_of=True,
            discipline="palla_8",
            is_multi_discipline=False,
            player1_racks=3,
            player2_racks=2,
            winner_id=1,
            status="completed",
        )
        set_obj.match = mock_match

        summary = set_obj.get_score_summary()
        assert summary["set_number"] == 1
        assert summary["distance"] == 5
        assert summary["best_of"] is True
        assert summary["discipline"] == "palla_8"
        assert summary["is_multi_discipline"] is False
        assert summary["player1_racks"] == 3
        assert summary["player2_racks"] == 2
        assert summary["total_racks_played"] == 5
        assert summary["winner_id"] == 1
        assert summary["status"] == "completed"
        assert summary["is_completed"] is True

    def test_get_rack_history(self):
        """Test get_rack_history method."""
        set_obj = Set()

        # Mock racks
        mock_rack1 = MagicMock()
        mock_rack1.rack_number = 1
        mock_rack1.winner_id = 1
        mock_rack1.discipline_override = "discipline1"
        mock_rack1.created_at = datetime(2023, 1, 1)

        mock_rack2 = MagicMock()
        mock_rack2.rack_number = 2
        mock_rack2.winner_id = 2
        mock_rack2.discipline_override = None
        mock_rack2.created_at = datetime(2023, 1, 2)

        set_obj.racks = [mock_rack1, mock_rack2]
        set_obj.get_discipline_for_rack = MagicMock(return_value="default_discipline")

        history = set_obj.get_rack_history()
        assert len(history) == 2
        assert history[0]["rack_number"] == 1
        assert history[0]["winner_id"] == 1
        assert history[0]["discipline"] == "discipline1"
        assert history[1]["rack_number"] == 2
        assert history[1]["winner_id"] == 2
        assert history[1]["discipline"] == "default_discipline"


class TestSetRackModel:
    """Test cases for SetRack model."""

    def test_set_rack_creation(self):
        """Test SetRack model creation."""
        rack = SetRack(set_id=1, rack_number=1, winner_id=1)

        assert rack.set_id == 1
        assert rack.rack_number == 1
        assert rack.winner_id == 1
        # Initialize default values that are set in the database model
        rack.confirmed_by_player = False
        rack.validated_by_admin = False
        assert rack.confirmed_by_player is False
        assert rack.validated_by_admin is False

    def test_can_be_confirmed(self):
        """Test can_be_confirmed method."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        # Create mock set
        mock_set = MagicMock()
        mock_set.match = mock_match

        rack = SetRack(set=mock_set, reported_by_id=2)

        # Test confirmed rack
        rack.confirmed_by_player = True
        assert not rack.can_be_confirmed(1)

        # Test validated rack
        rack.confirmed_by_player = False
        rack.validated_by_admin = True
        assert not rack.can_be_confirmed(1)

        # Test player1 confirming player2's report
        rack.validated_by_admin = False
        assert rack.can_be_confirmed(1)

        # Test player2 confirming player1's report
        rack.reported_by_id = 1
        assert rack.can_be_confirmed(2)

        # Test same player trying to confirm
        assert not rack.can_be_confirmed(1)

    def test_confirm_rack(self):
        """Test confirm_rack method."""
        # Create mock match
        mock_match = MagicMock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        # Create mock set
        mock_set = MagicMock()
        mock_set.match = mock_match

        rack = SetRack(set=mock_set, reported_by_id=2)

        # Test successful confirmation
        rack.confirm_rack(1)
        assert rack.confirmed_by_player is True

        # Test unsuccessful confirmation
        rack.confirmed_by_player = False
        with pytest.raises(ValueError):
            rack.confirm_rack(2)

    def test_get_effective_discipline(self):
        """Test get_effective_discipline method."""
        # Create mock set
        mock_set = MagicMock()
        mock_set.get_discipline_for_rack.return_value = "default_discipline"

        rack = SetRack(
            set=mock_set, discipline_override="override_discipline", rack_number=1
        )

        # Test with override
        assert rack.get_effective_discipline() == "override_discipline"

        # Test without override
        rack.discipline_override = None
        assert rack.get_effective_discipline() == "default_discipline"


if __name__ == "__main__":
    pytest.main([__file__])
