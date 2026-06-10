"""
Test module for models/playoff/services.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from models.playoff.services import PlayoffService
from models.playoff.models import (
    PlayoffType,
    QualificationStatus,
)
from models.base import utc_now


class TestPlayoffService:
    """Test cases for PlayoffService class."""

    def test_create_playoff_configuration(self):
        """Test creating a playoff configuration."""
        with patch("models.playoff.services.db") as mock_db:
            mock_configuration = Mock()
            mock_configuration.id = 1

            with patch(
                "models.playoff.services.PlayoffConfiguration"
            ) as mock_config_class:
                mock_config_class.return_value = mock_configuration

                qualification_criteria = {
                    "category": "elite",
                    "elite_positions": 6,
                    "academy_positions": 6,
                }

                result = PlayoffService.create_playoff_configuration(
                    campionato_id=1,
                    name="Elite Playoff",
                    playoff_type=PlayoffType.ELITE_ACADEMY,
                    max_participants=6,
                    qualification_criteria=qualification_criteria,
                    description="Playoff for top 6 classified players",
                    min_garas_played=3,
                    location="Test Location",
                    scheduled_date=datetime(2023, 6, 15, 14, 0, 0),
                    entry_fee=50.0,
                    response_deadline=datetime(2023, 6, 1, 12, 0, 0),
                )

                # Verify PlayoffConfiguration was created with correct parameters
                mock_config_class.assert_called_once()
                args, kwargs = mock_config_class.call_args
                assert kwargs["campionato_id"] == 1
                assert kwargs["name"] == "Elite Playoff"
                assert kwargs["playoff_type"] == PlayoffType.ELITE_ACADEMY
                assert kwargs["max_participants"] == 6
                assert kwargs["description"] == "Playoff for top 6 classified players"
                assert kwargs["min_garas_played"] == 3
                assert kwargs["location"] == "Test Location"
                assert kwargs["scheduled_date"] == datetime(2023, 6, 15, 14, 0, 0)
                assert kwargs["entry_fee"] == 50.0
                assert kwargs["response_deadline"] == datetime(2023, 6, 1, 12, 0, 0)

                # Verify set_qualification_criteria was called
                mock_configuration.set_qualification_criteria.assert_called_once_with(
                    qualification_criteria
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_configuration)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_configuration

    def test_create_standard_playoff_configurations(self):
        """Test creating standard playoff configurations."""
        with patch.object(
            PlayoffService, "create_playoff_configuration"
        ) as mock_create_config:
            mock_elite_config = Mock()
            mock_elite_config.id = 1
            mock_academy_config = Mock()
            mock_academy_config.id = 2

            # Set up mock to return different configurations based on name
            def create_config_side_effect(**kwargs):
                if kwargs["name"] == "Elite Playoff":
                    return mock_elite_config
                elif kwargs["name"] == "Academy Playoff":
                    return mock_academy_config
                return Mock()

            mock_create_config.side_effect = create_config_side_effect

            result = PlayoffService.create_standard_playoff_configurations(
                campionato_id=1
            )

            # Verify two configurations were created
            assert len(result) == 2
            assert mock_elite_config in result
            assert mock_academy_config in result

            # Verify create_playoff_configuration was called twice
            assert mock_create_config.call_count == 2

            # Verify first call (Elite Playoff)
            mock_create_config.assert_any_call(
                campionato_id=1,
                name="Elite Playoff",
                playoff_type=PlayoffType.ELITE_ACADEMY,
                max_participants=6,
                qualification_criteria={
                    "category": "elite",
                    "elite_positions": 6,
                    "academy_positions": 6,
                },
                description="Playoff for top 6 classified players",
                min_garas_played=3,
            )

            # Verify second call (Academy Playoff)
            mock_create_config.assert_any_call(
                campionato_id=1,
                name="Academy Playoff",
                playoff_type=PlayoffType.ELITE_ACADEMY,
                max_participants=6,
                qualification_criteria={
                    "category": "academy",
                    "elite_positions": 6,
                    "academy_positions": 6,
                },
                description="Playoff for players in positions 7-12",
                min_garas_played=3,
            )

    def test_generate_all_qualifications(self):
        """Test generating all qualifications for a campionato."""
        mock_config1 = Mock()
        mock_config1.name = "Elite Playoff"
        mock_config1.id = 1

        mock_config2 = Mock()
        mock_config2.name = "Academy Playoff"
        mock_config2.id = 2

        mock_qualification1 = Mock()
        mock_qualification2 = Mock()
        mock_qualification3 = Mock()

        # Set up mock configurations to return qualifications
        mock_config1.generate_qualifications.return_value = [
            mock_qualification1,
            mock_qualification2,
        ]
        mock_config2.generate_qualifications.return_value = [mock_qualification3]

        with patch("models.playoff.services.PlayoffConfiguration") as mock_config_class:
            mock_query = Mock()
            mock_config_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_config1, mock_config2]

            result = PlayoffService.generate_all_qualifications(campionato_id=1)

            # Verify the structure of the result
            assert "Elite Playoff" in result
            assert "Academy Playoff" in result
            assert len(result["Elite Playoff"]) == 2
            assert len(result["Academy Playoff"]) == 1

            # Verify generate_qualifications was called on each config
            mock_config1.generate_qualifications.assert_called_once()
            mock_config2.generate_qualifications.assert_called_once()

    def test_notify_qualified_players(self):
        """Test notifying qualified players."""
        mock_qualification1 = Mock()
        mock_qualification1.id = 1
        mock_qualification1.notified_at = None

        mock_qualification2 = Mock()
        mock_qualification2.id = 2
        mock_qualification2.notified_at = None

        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_qualification1, mock_qualification2]

            with patch("models.playoff.services.db") as mock_db:
                with patch("models.playoff.services.datetime") as mock_datetime:
                    mock_utc_now.return_value = datetime(2023, 1, 1, 12, 0, 0)

                    result = PlayoffService.notify_qualified_players(configuration_id=1)

                    # Verify both qualifications were marked as notified
                    assert mock_qualification1.notified_at == datetime(
                        2023, 1, 1, 12, 0, 0
                    )
                    assert mock_qualification2.notified_at == datetime(
                        2023, 1, 1, 12, 0, 0
                    )

                    # Verify database commit
                    mock_db.session.commit.assert_called_once()

                    # Verify result (count of notified players)
                    assert result == 2

    def test_confirm_qualification_success(self):
        """Test confirming a playoff qualification successfully."""
        mock_qualification = Mock()
        mock_qualification.id = 1
        mock_qualification.user_id = 10
        mock_qualification.configuration_id = 1  # Add this line

        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_qualification.configuration = mock_configuration

        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = mock_qualification

            with patch("models.playoff.services.db") as mock_db:
                with patch.object(
                    PlayoffService, "_check_playoff_readiness"
                ) as mock_check_readiness:
                    result = PlayoffService.confirm_qualification(
                        qualification_id=1, user_id=10
                    )

                    # Verify confirm_participation was called
                    mock_qualification.confirm_participation.assert_called_once()

                    # Verify database commit
                    mock_db.session.commit.assert_called_once()

                    # Verify playoff readiness check with the actual configuration ID
                    mock_check_readiness.assert_called_once_with(1)

                    # Verify result
                    assert result == mock_qualification

    def test_confirm_qualification_not_found(self):
        """Test confirming a playoff qualification when not found."""
        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = None

            with pytest.raises(Exception):
                PlayoffService.confirm_qualification(qualification_id=1, user_id=10)

    def test_decline_qualification_success(self):
        """Test declining a playoff qualification successfully."""
        mock_qualification = Mock()
        mock_qualification.id = 1
        mock_qualification.user_id = 10
        mock_qualification.configuration_id = 1  # Add this line

        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_qualification.configuration = mock_configuration

        mock_replacement = Mock()

        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = mock_qualification

            with patch("models.playoff.services.db") as mock_db:
                mock_qualification.decline_participation.return_value = mock_replacement

                with patch.object(
                    PlayoffService, "notify_qualified_players"
                ) as mock_notify:
                    result = PlayoffService.decline_qualification(
                        qualification_id=1, user_id=10
                    )

                    # Verify decline_participation was called
                    mock_qualification.decline_participation.assert_called_once()

                    # Verify database commit
                    mock_db.session.commit.assert_called_once()

                    # Verify notification was sent to replacement
                    # with correct configuration ID
                    mock_notify.assert_called_once_with(1)

                    # Verify result
                    assert result == mock_replacement

    def test_decline_qualification_not_found(self):
        """Test declining a playoff qualification when not found."""
        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = None

            with pytest.raises(Exception):
                PlayoffService.decline_qualification(qualification_id=1, user_id=10)

    def test_find_replacement_player_success(self):
        """Test finding a replacement player successfully."""
        mock_configuration = Mock()
        mock_configuration.id = 1

        mock_confirmed_qual = Mock()
        mock_confirmed_qual.user_id = 10

        mock_pending_qual = Mock()
        mock_pending_qual.user_id = 20

        mock_player_data = {
            "user_id": 30,
            "position": 7,
            "qualification_reason": "Next eligible player",
        }

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            with patch(
                "models.playoff.services.PlayoffQualification"
            ) as mock_qual_class:
                # Mock confirmed qualifications query
                mock_confirmed_query = Mock()
                mock_qual_class.query.filter_by.return_value = mock_confirmed_query
                mock_confirmed_query.all.side_effect = [
                    [mock_confirmed_qual],  # First call for CONFIRMED
                    [mock_pending_qual],  # Second call for PENDING
                    [],  # Third call in replacement creation
                ]

                # Mock configuration.evaluate_qualifications
                mock_configuration.evaluate_qualifications.return_value = [
                    mock_player_data
                ]

                mock_replacement = Mock()
                mock_replacement.id = 3

                with patch(
                    "models.playoff.services.PlayoffQualification"
                ) as mock_replacement_class:
                    mock_replacement_class.return_value = mock_replacement

                    result = PlayoffService.find_replacement_player(configuration_id=1)

                    # Verify database operations
                    mock_db.session.add.assert_called_once_with(mock_replacement)
                    mock_db.session.commit.assert_called_once()

                    # Verify result
                    assert result == mock_replacement

    def test_find_replacement_player_not_found(self):
        """Test finding a replacement player when none available."""
        mock_configuration = Mock()
        mock_configuration.id = 1

        mock_confirmed_qual = Mock()
        mock_confirmed_qual.user_id = 10

        mock_pending_qual = Mock()
        mock_pending_qual.user_id = 20

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            with patch(
                "models.playoff.services.PlayoffQualification"
            ) as mock_qual_class:
                # Mock confirmed qualifications query
                mock_confirmed_query = Mock()
                mock_qual_class.query.filter_by.return_value = mock_confirmed_query
                mock_confirmed_query.all.side_effect = [
                    [mock_confirmed_qual],  # First call for CONFIRMED
                    [mock_pending_qual],  # Second call for PENDING
                    [],  # Third call in replacement creation
                ]

                # Mock configuration.evaluate_qualifications to return
                # only existing players
                mock_configuration.evaluate_qualifications.return_value = [
                    {
                        "user_id": 10,
                        "position": 1,
                        "qualification_reason": "Already qualified",
                    },
                    {
                        "user_id": 20,
                        "position": 2,
                        "qualification_reason": "Already qualified",
                    },
                ]

                result = PlayoffService.find_replacement_player(configuration_id=1)

                # Verify no replacement was found
                assert result is None

    def test_find_replacement_player_configuration_not_found(self):
        """Test finding a replacement player when configuration is not found."""
        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    PlayoffService.find_replacement_player(configuration_id=1)

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_expire_old_qualifications(self):
        """Test expiring old qualifications."""
        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_configuration.response_deadline = datetime(
            2022, 12, 31, 12, 0, 0
        )  # Past deadline
        mock_configuration.is_active = True

        mock_qualification = Mock()
        mock_qualification.id = 1

        with patch("models.playoff.services.PlayoffConfiguration") as mock_config_class:
            # Mock the class attributes directly to avoid datetime comparison
            mock_config_class.response_deadline = datetime(2022, 12, 31, 12, 0, 0)
            mock_config_class.is_active = True
            # Mock the entire query operation
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_filtered_query.all.return_value = [mock_configuration]
            mock_query.filter.return_value = mock_filtered_query
            mock_config_class.query = mock_query

            # Mock qualifications filter
            mock_config_qualifications = Mock()
            mock_configuration.qualifications.filter_by.return_value = (
                mock_config_qualifications
            )
            mock_config_qualifications.all.return_value = [mock_qualification]

            with patch.object(
                PlayoffService, "find_replacement_player"
            ) as mock_find_replacement:
                mock_find_replacement.return_value = Mock()  # Found replacement

                with patch.object(
                    PlayoffService, "notify_qualified_players"
                ) as mock_notify:
                    with patch("models.playoff.services.db") as mock_db:
                        with patch("models.playoff.services.datetime") as mock_datetime:
                            mock_utc_now.return_value = datetime(2023, 1, 1, 12, 0, 0)

                            result = PlayoffService.expire_old_qualifications()

                            # Verify qualification was expired
                            mock_qualification.expire_qualification.assert_called_once()

                            # Verify replacement was found
                            mock_find_replacement.assert_called_once_with(1)

                            # Verify notification was sent
                            mock_notify.assert_called_once_with(1)

                            # Verify database commit
                            mock_db.session.commit.assert_called_once()

                            # Verify result (count of expired qualifications)
                            assert result == 1

    def test_create_playoff_campionato_success(self):
        """Test creating a playoff campionato successfully."""
        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_configuration.name = "Elite Playoff"
        mock_configuration.scheduled_date = datetime(2023, 6, 15, 14, 0, 0)
        mock_configuration.location = "Test Location"
        mock_configuration.entry_fee = 50.0
        mock_configuration.max_participants = 6
        mock_configuration.playoff_campionato = None

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            mock_campionato = Mock()
            mock_campionato.id = 1

            with patch(
                "models.playoff.services.PlayoffTournament"
            ) as mock_campionato_class:
                mock_campionato_class.return_value = mock_campionato

                result = PlayoffService.create_playoff_campionato(configuration_id=1)

                # Verify PlayoffTournament was created with correct parameters
                mock_campionato_class.assert_called_once()
                args, kwargs = mock_campionato_class.call_args
                assert kwargs["configuration_id"] == 1
                assert kwargs["name"] == "Elite Playoff"
                assert kwargs["campionato_date"] == datetime(2023, 6, 15, 14, 0, 0)
                assert kwargs["location"] == "Test Location"
                assert kwargs["entry_fee"] == 50.0
                assert kwargs["max_participants"] == 6

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_campionato)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_campionato

    def test_create_playoff_campionato_already_exists(self):
        """Test creating a playoff campionato when it already exists."""
        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_configuration.playoff_campionato = Mock()

        mock_existing_campionato = Mock()
        mock_existing_campionato.id = 1

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            with patch(
                "models.playoff.services.PlayoffTournament"
            ) as mock_campionato_class:
                mock_query = Mock()
                mock_campionato_class.query.filter_by.return_value = mock_query
                mock_query.first.return_value = mock_existing_campionato

                result = PlayoffService.create_playoff_campionato(configuration_id=1)

                # Verify existing campionato was returned
                assert result == mock_existing_campionato

    def test_create_playoff_campionato_configuration_not_found(self):
        """Test creating a playoff campionato when configuration is not found."""
        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    PlayoffService.create_playoff_campionato(configuration_id=1)

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_start_playoff_registration_success(self):
        """Test starting playoff registration successfully."""
        mock_campionato = Mock()
        mock_campionato.id = 1

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_campionato

            result = PlayoffService.start_playoff_registration(campionato_id=1)

            # Verify start_registration was called
            mock_campionato.start_registration.assert_called_once()

            # Verify database commit
            mock_db.session.commit.assert_called_once()

            # Verify result
            assert result == mock_campionato

    def test_start_playoff_registration_not_found(self):
        """Test starting playoff registration when campionato is not found."""
        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    PlayoffService.start_playoff_registration(campionato_id=1)

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_get_campionato_playoff_status(self):
        """Test getting campionato playoff status."""
        mock_config1 = Mock()
        mock_config1.name = "Elite Playoff"
        mock_config1.id = 1
        mock_config1.max_participants = 6
        mock_config1.playoff_campionato = None

        mock_config2 = Mock()
        mock_config2.name = "Academy Playoff"
        mock_config2.id = 2
        mock_config2.max_participants = 6
        mock_config2.playoff_campionato = Mock()
        mock_config2.playoff_campionato.status = "completed"

        # Mock qualification counts
        mock_config1.qualifications.count.return_value = 8
        mock_config1.qualifications.filter_by.return_value.count.side_effect = [
            5,
            2,
            1,
        ]  # confirmed, pending, declined

        mock_config2.qualifications.count.return_value = 6
        mock_config2.qualifications.filter_by.return_value.count.side_effect = [
            6,
            0,
            0,
        ]  # confirmed, pending, declined

        with patch("models.playoff.services.PlayoffConfiguration") as mock_config_class:
            mock_query = Mock()
            mock_config_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_config1, mock_config2]

            result = PlayoffService.get_campionato_playoff_status(campionato_id=1)

            # Verify the structure of the returned status
            assert result["has_playoffs"] is True
            assert len(result["configurations"]) == 2
            assert result["total_qualified"] == 14
            assert result["total_confirmed"] == 11

            # Verify first configuration status
            config1_status = result["configurations"][0]
            assert config1_status["configuration"] == mock_config1
            assert config1_status["total_qualified"] == 8
            assert config1_status["confirmed"] == 5
            assert config1_status["pending"] == 2
            assert config1_status["declined"] == 1
            assert config1_status["has_campionato"] is False

            # Verify second configuration status
            config2_status = result["configurations"][1]
            assert config2_status["configuration"] == mock_config2
            assert config2_status["total_qualified"] == 6
            assert config2_status["confirmed"] == 6
            assert config2_status["pending"] == 0
            assert config2_status["declined"] == 0
            assert config2_status["has_campionato"] is True
            assert config2_status["campionato_status"] == "completed"

    def test_check_playoff_readiness_ready_to_start(self):
        """Test checking playoff readiness when ready to start."""
        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_configuration.max_participants = 6
        mock_configuration.playoff_campionato = None

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            # Mock qualification counts - 5 confirmed (83% of 6), 0 pending
            mock_confirmed_query = Mock()
            mock_confirmed_query.count.return_value = 5
            mock_configuration.qualifications.filter_by.return_value = (
                mock_confirmed_query
            )

            mock_pending_query = Mock()
            mock_pending_query.count.return_value = 0
            # Second call to filter_by should return pending query
            mock_configuration.qualifications.filter_by.side_effect = [
                mock_confirmed_query,
                mock_pending_query,
            ]

            with patch.object(
                PlayoffService, "create_playoff_campionato"
            ) as mock_create_campionato:
                PlayoffService._check_playoff_readiness(configuration_id=1)

                # Verify playoff campionato was created
                mock_create_campionato.assert_called_once_with(1)

    def test_check_playoff_readiness_not_ready(self):
        """Test checking playoff readiness when not ready to start."""
        mock_configuration = Mock()
        mock_configuration.id = 1
        mock_configuration.max_participants = 6
        mock_configuration.playoff_campionato = None

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_configuration

            # Mock qualification counts - 3 confirmed (50% of 6), 2 pending
            mock_confirmed_query = Mock()
            mock_confirmed_query.count.return_value = 3
            mock_configuration.qualifications.filter_by.return_value = (
                mock_confirmed_query
            )

            mock_pending_query = Mock()
            mock_pending_query.count.return_value = 2
            # Second call to filter_by should return pending query
            mock_configuration.qualifications.filter_by.side_effect = [
                mock_confirmed_query,
                mock_pending_query,
            ]

            with patch.object(
                PlayoffService, "create_playoff_campionato"
            ) as mock_create_campionato:
                PlayoffService._check_playoff_readiness(configuration_id=1)

                # Verify playoff campionato was not created
                mock_create_campionato.assert_not_called()

    def test_complete_playoff_campionato_success(self):
        """Test completing a playoff campionato successfully."""
        mock_campionato = Mock()
        mock_campionato.id = 1

        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = mock_campionato

            result = PlayoffService.complete_playoff_campionato(
                campionato_id=1, winner_id=10
            )

            # Verify complete_campionato was called
            mock_campionato.complete_campionato.assert_called_once_with(10)

            # Verify database commit
            mock_db.session.commit.assert_called_once()

            # Verify result
            assert result == mock_campionato

    def test_complete_playoff_campionato_not_found(self):
        """Test completing a playoff campionato when not found."""
        with patch("models.playoff.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    PlayoffService.complete_playoff_campionato(campionato_id=1)

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_get_user_playoff_history(self):
        """Test getting user's playoff history."""
        mock_qualification1 = Mock()
        mock_qualification1.qualifying_position = 1
        mock_qualification1.status = QualificationStatus.CONFIRMED
        mock_qualification1.created_at = datetime(2023, 1, 1, 10, 0, 0)
        mock_qualification1.responded_at = datetime(2023, 1, 2, 10, 0, 0)

        mock_config1 = Mock()
        mock_config1.name = "Elite Playoff"
        mock_qualification1.configuration = mock_config1

        mock_campionato1 = Mock()
        mock_campionato1.name = "Campionato 1"
        mock_config1.campionato = mock_campionato1

        mock_qualification2 = Mock()
        mock_qualification2.qualifying_position = 7
        mock_qualification2.status = QualificationStatus.DECLINED
        mock_qualification2.created_at = datetime(2023, 2, 1, 10, 0, 0)
        mock_qualification2.responded_at = datetime(2023, 2, 2, 10, 0, 0)

        mock_config2 = Mock()
        mock_config2.name = "Academy Playoff"
        mock_qualification2.configuration = mock_config2

        mock_campionato2 = Mock()
        mock_campionato2.name = "Campionato 2"
        mock_config2.campionato = mock_campionato2

        with patch("models.playoff.services.PlayoffQualification") as mock_qual_class:
            mock_query = Mock()
            mock_qual_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_qualification1, mock_qualification2]

            result = PlayoffService.get_user_playoff_history(user_id=10)

            # Verify the structure of the returned history
            assert len(result) == 2

            # Verify most recent entry first (sorted by created_at desc)
            assert result[0]["campionato_name"] == "Campionato 2"
            assert result[0]["playoff_name"] == "Academy Playoff"
            assert result[0]["qualifying_position"] == 7
            assert result[0]["status"] == "declined"
            assert result[0]["qualified_at"] == datetime(2023, 2, 1, 10, 0, 0)
            assert result[0]["responded_at"] == datetime(2023, 2, 2, 10, 0, 0)

            # Verify older entry second
            assert result[1]["campionato_name"] == "Campionato 1"
            assert result[1]["playoff_name"] == "Elite Playoff"
            assert result[1]["qualifying_position"] == 1
            assert result[1]["status"] == "confirmed"
            assert result[1]["qualified_at"] == datetime(2023, 1, 1, 10, 0, 0)
            assert result[1]["responded_at"] == datetime(2023, 1, 2, 10, 0, 0)


if __name__ == "__main__":
    pytest.main([__file__])
