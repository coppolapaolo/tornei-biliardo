"""
Test module for models/match/multi_discipline_service.py
"""

import pytest
from unittest.mock import Mock, patch
from models.match.multi_discipline_service import MultiDisciplineService
# No unused imports needed


class TestMultiDisciplineService:
    """Test cases for MultiDisciplineService class."""

    def test_get_available_disciplines(self):
        """Test getting available disciplines."""
        disciplines = MultiDisciplineService.get_available_disciplines()

        # Should return a list of disciplines with value and label
        assert isinstance(disciplines, list)
        assert len(disciplines) > 0

        # Check that each discipline has required fields
        for discipline in disciplines:
            assert "value" in discipline
            assert "label" in discipline
            assert "description" in discipline

    def test_get_discipline_rules(self):
        """Test getting discipline rules."""
        # Test with a valid discipline
        rules = MultiDisciplineService.get_discipline_rules("palla_8")
        assert isinstance(rules, dict)
        assert "name" in rules
        assert "rack_size" in rules
        assert "winning_condition" in rules

        # Test with an invalid discipline
        rules = MultiDisciplineService.get_discipline_rules("invalid_discipline")
        assert isinstance(rules, dict)
        assert len(rules) == 0

    def test_validate_discipline_configuration_valid(self):
        """Test validating a valid discipline configuration."""
        config = {
            "match_id": 1,
            "disciplines": ["palla_8", "palla_9"],
            "rotation_type": "set_level",
        }

        result = MultiDisciplineService.validate_discipline_configuration(config)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_discipline_configuration_invalid_discipline(self):
        """Test validating configuration with invalid discipline."""
        config = {
            "match_id": 1,
            "disciplines": ["palla_8", "invalid_discipline"],
            "rotation_type": "set_level",
        }

        result = MultiDisciplineService.validate_discipline_configuration(config)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "Invalid discipline" in result["errors"][0]

    def test_validate_discipline_configuration_missing_match_id(self):
        """Test validating configuration without match_id."""
        config = {"disciplines": ["palla_8", "palla_9"], "rotation_type": "set_level"}

        result = MultiDisciplineService.validate_discipline_configuration(config)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "match_id is required" in result["errors"]

    def test_validate_discipline_configuration_invalid_rotation_type(self):
        """Test validating configuration with invalid rotation type."""
        config = {
            "match_id": 1,
            "disciplines": ["palla_8", "palla_9"],
            "rotation_type": "invalid_type",
        }

        result = MultiDisciplineService.validate_discipline_configuration(config)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "rotation_type must be" in result["errors"][0]

    def test_create_preset_configuration_valid(self):
        """Test creating a valid preset configuration."""
        preset = MultiDisciplineService.create_preset_configuration("pool_variety")
        assert isinstance(preset, dict)
        assert "name" in preset
        assert "disciplines" in preset
        assert "rotation_type" in preset

    def test_create_preset_configuration_invalid(self):
        """Test creating an invalid preset configuration."""
        with pytest.raises(ValueError, match="Unknown preset"):
            MultiDisciplineService.create_preset_configuration("invalid_preset")

    def test_configure_rotating_disciplines_match_not_found(self):
        """Test configuring rotating disciplines for non-existent match."""
        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = None

            with pytest.raises(Exception):  # Flask abort raises an exception
                MultiDisciplineService.configure_rotating_disciplines(
                    999, ["palla_8", "palla_9"]
                )

    def test_configure_rotating_disciplines_insufficient_disciplines(self):
        """Test configuring rotating disciplines with insufficient disciplines."""
        mock_match = Mock()
        mock_match.supports_multi_discipline.return_value = True

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with pytest.raises(ValueError, match="At least 2 disciplines required"):
                MultiDisciplineService.configure_rotating_disciplines(1, ["palla_8"])

    def test_configure_rotating_disciplines_unsupported_match(self):
        """Test configuring rotating disciplines for unsupported match."""
        mock_match = Mock()
        mock_match.supports_multi_discipline.return_value = False

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with pytest.raises(ValueError, match="does not support multi-discipline"):
                MultiDisciplineService.configure_rotating_disciplines(
                    1, ["palla_8", "palla_9"]
                )

    def test_configure_rotating_disciplines_set_level(self):
        """Test configuring set-level rotating disciplines."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        mock_set1 = Mock()
        mock_set1.set_number = 1
        mock_set2 = Mock()
        mock_set2.set_number = 2

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1, mock_set2]
                mock_set_class.query = mock_query

                MultiDisciplineService.configure_rotating_disciplines(
                    1, ["palla_8", "palla_9"], "set_level"
                )

                # Verify the sets were configured correctly
                assert mock_set1.discipline == "palla_8"
                assert mock_set1.is_multi_discipline is False
                assert mock_set2.discipline == "palla_9"
                assert mock_set2.is_multi_discipline is False

                # Verify database commit was called
                mock_db.session.commit.assert_called_once()

    def test_configure_rotating_disciplines_rack_level(self):
        """Test configuring rack-level rotating disciplines."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        mock_set1 = Mock()
        mock_set1.set_number = 1
        mock_set2 = Mock()
        mock_set2.set_number = 2

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1, mock_set2]
                mock_set_class.query = mock_query

                MultiDisciplineService.configure_rotating_disciplines(
                    1, ["palla_8", "palla_9"], "rack_level"
                )

                # Verify the sets were configured for multi-discipline
                mock_set1.configure_multi_discipline.assert_called_once_with(
                    ["palla_8", "palla_9"], "rotation"
                )
                mock_set2.configure_multi_discipline.assert_called_once_with(
                    ["palla_8", "palla_9"], "rotation"
                )

                # Verify database commit was called
                mock_db.session.commit.assert_called_once()

    def test_configure_rotating_disciplines_invalid_rotation_type(self):
        """Test configuring rotating disciplines with invalid rotation type."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            # Mock the Set query to avoid database access
            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = []
                mock_set_class.query = mock_query

                with pytest.raises(ValueError, match="Unsupported rotation type"):
                    MultiDisciplineService.configure_rotating_disciplines(
                        1, ["palla_8", "palla_9"], "invalid_type"
                    )

    def test_configure_custom_disciplines_match_not_found(self):
        """Test configuring custom disciplines for non-existent match."""
        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = None

            with pytest.raises(Exception):  # Flask abort raises an exception
                MultiDisciplineService.configure_custom_disciplines(999, {})

    def test_configure_custom_disciplines_unsupported_match(self):
        """Test configuring custom disciplines for unsupported match."""
        mock_match = Mock()
        mock_match.supports_multi_discipline.return_value = False

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with pytest.raises(ValueError, match="does not support multi-discipline"):
                MultiDisciplineService.configure_custom_disciplines(1, {})

    def test_configure_custom_disciplines_multi_discipline_rotation(self):
        """Test configuring custom disciplines with multi-discipline rotation."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        mock_set1 = Mock()
        mock_set1.set_number = 1

        set_configurations = {
            1: {"multi_discipline": True, "rotation": ["palla_8", "palla_9"]}
        }

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1]
                mock_set_class.query = mock_query

                MultiDisciplineService.configure_custom_disciplines(
                    1, set_configurations
                )

                # Verify the set was configured for multi-discipline rotation
                mock_set1.configure_multi_discipline.assert_called_once_with(
                    ["palla_8", "palla_9"], "rotation"
                )

                # Verify database commit was called
                mock_db.session.commit.assert_called_once()

    def test_configure_custom_disciplines_multi_discipline_assignment(self):
        """Test configuring custom disciplines with multi-discipline assignment."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        mock_set1 = Mock()
        mock_set1.set_number = 1

        set_configurations = {
            1: {"multi_discipline": True, "assignment": {1: "palla_8", 2: "palla_9"}}
        }

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1]
                mock_set_class.query = mock_query

                MultiDisciplineService.configure_custom_disciplines(
                    1, set_configurations
                )

                # Verify the set was configured for multi-discipline assignment
                # The order might vary because list(set(...)) doesn't preserve order
                mock_set1.configure_multi_discipline.assert_called_once()
                call_args = mock_set1.configure_multi_discipline.call_args
                assert call_args[0][1] == "assignment"
                # Check that both disciplines are present regardless of order
                assert set(call_args[0][0]) == {"palla_8", "palla_9"}

                mock_set1.set_discipline_assignment.assert_called_once_with(
                    {1: "palla_8", 2: "palla_9"}
                )

                # Verify database commit was called
                mock_db.session.commit.assert_called_once()

    def test_configure_custom_disciplines_single_discipline(self):
        """Test configuring custom disciplines with single discipline."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.supports_multi_discipline.return_value = True

        mock_set1 = Mock()
        mock_set1.set_number = 1

        set_configurations = {1: {"discipline": "palla_8"}}

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1]
                mock_set_class.query = mock_query

                MultiDisciplineService.configure_custom_disciplines(
                    1, set_configurations
                )

                # Verify the set was configured with single discipline
                assert mock_set1.discipline == "palla_8"
                assert mock_set1.is_multi_discipline is False

                # Verify database commit was called
                mock_db.session.commit.assert_called_once()

    def test_get_match_discipline_progress_single_discipline(self):
        """Test getting discipline progress for single discipline match."""
        mock_match = Mock()
        mock_match.is_multi_set = False
        mock_match.discipline = "palla_8"

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            progress = MultiDisciplineService.get_match_discipline_progress(1)

            assert progress["is_multi_discipline"] is False
            assert progress["current_discipline"] == "palla_8"

    def test_get_match_discipline_progress_multi_discipline(self):
        """Test getting discipline progress for multi-discipline match."""
        mock_match = Mock()
        mock_match.id = 1
        mock_match.is_multi_set = True

        mock_current_set = Mock()
        mock_current_set.set_number = 1

        mock_match.get_current_set.return_value = mock_current_set
        mock_match.get_multi_discipline_summary.return_value = {
            "is_multi_discipline": True,
            "disciplines_used": ["palla_8", "palla_9"],
        }

        mock_set1 = Mock()
        mock_set1.set_number = 1
        mock_set1.status = "completed"
        mock_set1.discipline = "palla_8"
        mock_set1.is_multi_discipline = False
        mock_set1.is_completed.return_value = True

        mock_set2 = Mock()
        mock_set2.set_number = 2
        mock_set2.status = "pending"
        mock_set2.discipline = "palla_9"
        mock_set2.is_multi_discipline = False
        mock_set2.is_completed.return_value = False

        with patch("models.match.multi_discipline_service.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch("models.match.multi_discipline_service.Set") as mock_set_class:
                mock_query = Mock()
                mock_query.filter_by.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.all.return_value = [mock_set1, mock_set2]
                mock_set_class.query = mock_query

                progress = MultiDisciplineService.get_match_discipline_progress(1)

                assert progress["is_multi_discipline"] is True
                assert len(progress["disciplines_used"]) == 2
                assert progress["total_sets"] == 2
                assert progress["completed_sets"] == 1
                assert len(progress["sets_summary"]) == 2
