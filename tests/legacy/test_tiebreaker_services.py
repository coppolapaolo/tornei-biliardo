"""
Test module for models/tiebreaker/services.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from models.tiebreaker.services import TiebreakerService, TiebreakerConfigurationService
from models.tiebreaker.models import (
    TiebreakerType,
    TiebreakerStatus,
    SpotShotResult,
)


class TestTiebreakerService:
    """Test cases for TiebreakerService class."""

    def test_create_spot_shot_tiebreaker(self):
        """Test creating a spot shot tiebreaker."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_tiebreaker = Mock()
            mock_tiebreaker.id = 1

            with patch(
                "models.tiebreaker.services.Tiebreaker"
            ) as mock_tiebreaker_class:
                mock_tiebreaker_class.return_value = mock_tiebreaker

                result = TiebreakerService.create_spot_shot_tiebreaker(
                    match_id=1,
                    player1_id=10,
                    player2_id=20,
                    campionato_id=100,
                    gara_id=200,
                )

                # Verify Tiebreaker was created with correct parameters
                mock_tiebreaker_class.assert_called_once_with(
                    match_id=1,
                    campionato_id=100,
                    gara_id=200,
                    tiebreaker_type=TiebreakerType.SPOT_SHOT.value,
                    player1_id=10,
                    player2_id=20,
                    configuration={
                        "max_rounds": 5,
                        "sudden_death_after": 5,
                        "ball_type": "8_ball",
                    },
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tiebreaker)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_tiebreaker

    def test_create_spot_shot_tiebreaker_with_custom_config(self):
        """Test creating a spot shot tiebreaker with custom configuration."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_tiebreaker = Mock()
            mock_tiebreaker.id = 1

            with patch(
                "models.tiebreaker.services.Tiebreaker"
            ) as mock_tiebreaker_class:
                mock_tiebreaker_class.return_value = mock_tiebreaker

                custom_config = {
                    "max_rounds": 3,
                    "sudden_death_after": 3,
                    "ball_type": "9_ball",
                }

                result = TiebreakerService.create_spot_shot_tiebreaker(
                    match_id=1,
                    player1_id=10,
                    player2_id=20,
                    configuration=custom_config,
                )

                # Verify Tiebreaker was created with merged configuration
                expected_config = {
                    "max_rounds": 3,
                    "sudden_death_after": 3,
                    "ball_type": "9_ball",
                }

                mock_tiebreaker_class.assert_called_once()
                args, kwargs = mock_tiebreaker_class.call_args
                assert kwargs["configuration"] == expected_config

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tiebreaker)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_tiebreaker

    def test_create_rally_tiebreaker(self):
        """Test creating a rally tiebreaker."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_tiebreaker = Mock()
            mock_tiebreaker.id = 1

            with patch(
                "models.tiebreaker.services.Tiebreaker"
            ) as mock_tiebreaker_class:
                mock_tiebreaker_class.return_value = mock_tiebreaker

                result = TiebreakerService.create_rally_tiebreaker(
                    match_id=1,
                    player1_id=10,
                    player2_id=20,
                    campionato_id=100,
                    gara_id=200,
                    target_score=20,
                )

                # Verify Tiebreaker was created with correct parameters
                mock_tiebreaker_class.assert_called_once_with(
                    match_id=1,
                    campionato_id=100,
                    gara_id=200,
                    tiebreaker_type=TiebreakerType.RALLY.value,
                    player1_id=10,
                    player2_id=20,
                    configuration={
                        "target_score": 20,
                        "max_attempts_per_player": 3,
                        "discipline": "straight_pool",
                    },
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tiebreaker)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_tiebreaker

    def test_create_playoff_tiebreaker(self):
        """Test creating a playoff tiebreaker."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_tiebreaker = Mock()
            mock_tiebreaker.id = 1

            with patch(
                "models.tiebreaker.services.Tiebreaker"
            ) as mock_tiebreaker_class:
                mock_tiebreaker_class.return_value = mock_tiebreaker

                result = TiebreakerService.create_playoff_tiebreaker(
                    match_id=1,
                    player1_id=10,
                    player2_id=20,
                    campionato_id=100,
                    gara_id=200,
                    is_race_to=5,
                )

                # Verify Tiebreaker was created with correct parameters
                mock_tiebreaker_class.assert_called_once_with(
                    match_id=1,
                    campionato_id=100,
                    gara_id=200,
                    tiebreaker_type=TiebreakerType.PLAYOFF_MATCH.value,
                    player1_id=10,
                    player2_id=20,
                    configuration={
                        "best_of": 5,
                        "match_distance": 3,
                        "discipline": "palla_8",
                    },
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tiebreaker)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_tiebreaker

    def test_record_spot_shot_success(self):
        """Test recording a spot shot successfully."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.status = TiebreakerStatus.IN_PROGRESS.value
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            with patch.object(
                TiebreakerService, "_check_spot_shot_completion"
            ) as mock_check_completion:
                mock_spot_shot = Mock()
                mock_spot_shot.id = 1

                with patch(
                    "models.tiebreaker.services.SpotShot"
                ) as mock_spot_shot_class:
                    mock_spot_shot_class.return_value = mock_spot_shot

                    result = TiebreakerService.record_spot_shot(
                        tiebreaker_id=1,
                        player_id=10,
                        round_number=1,
                        order_in_round=1,
                        result=SpotShotResult.MADE,
                    )

                    # Verify SpotShot was created with correct parameters
                    mock_spot_shot_class.assert_called_once_with(
                        tiebreaker_id=1,
                        player_id=10,
                        round_number=1,
                        order_in_round=1,
                        result=SpotShotResult.MADE.value,
                        notes=None,
                    )

                    # Verify database operations
                    mock_db.session.add.assert_called_once_with(mock_spot_shot)
                    mock_check_completion.assert_called_once_with(mock_tiebreaker)
                    mock_db.session.commit.assert_called_once()

                    # Verify result
                    assert result == mock_spot_shot

    def test_record_spot_shot_tiebreaker_not_found(self):
        """Test recording a spot shot when tiebreaker is not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerService.record_spot_shot(
                        tiebreaker_id=1,
                        player_id=10,
                        round_number=1,
                        order_in_round=1,
                        result=SpotShotResult.MADE,
                    )

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_record_spot_shot_wrong_status(self):
        """Test recording a spot shot when tiebreaker is not in progress."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.status = TiebreakerStatus.COMPLETED.value

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            with pytest.raises(ValueError, match="Tiebreaker must be in progress"):
                TiebreakerService.record_spot_shot(
                    tiebreaker_id=1,
                    player_id=10,
                    round_number=1,
                    order_in_round=1,
                    result=SpotShotResult.MADE,
                )

    def test_record_spot_shot_invalid_player(self):
        """Test recording a spot shot with invalid player."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.status = TiebreakerStatus.IN_PROGRESS.value
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            with pytest.raises(
                ValueError, match="Player must be one of the tiebreaker participants"
            ):
                TiebreakerService.record_spot_shot(
                    tiebreaker_id=1,
                    player_id=30,  # Not a participant
                    round_number=1,
                    order_in_round=1,
                    result=SpotShotResult.MADE,
                )

    def test_record_rally_attempt_success(self):
        """Test recording a rally attempt successfully."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.status = TiebreakerStatus.IN_PROGRESS.value
        mock_tiebreaker.rally_attempts = []

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            with patch.object(
                TiebreakerService, "_check_rally_completion"
            ) as mock_check_completion:
                mock_rally_attempt = Mock()
                mock_rally_attempt.id = 1

                with patch(
                    "models.tiebreaker.services.RallyAttempt"
                ) as mock_rally_attempt_class:
                    mock_rally_attempt_class.return_value = mock_rally_attempt

                    with patch("models.tiebreaker.services.datetime") as mock_datetime:
                        mock_datetime.utcnow.return_value = datetime(
                            2023, 1, 1, 12, 0, 0
                        )

                        result = TiebreakerService.record_rally_attempt(
                            tiebreaker_id=1,
                            player_id=10,
                            points_scored=5,
                            balls_pocketed=3,
                        )

                        # Verify RallyAttempt was created with correct parameters
                        mock_rally_attempt_class.assert_called_once_with(
                            tiebreaker_id=1,
                            player_id=10,
                            sequence_number=1,  # First attempt
                            points_scored=5,
                            balls_pocketed=3,
                            was_successful=True,
                            ended_rally=False,
                            notes=None,
                            completed_at=datetime(2023, 1, 1, 12, 0, 0),
                        )

                        # Verify database operations
                        mock_db.session.add.assert_called_once_with(mock_rally_attempt)
                        mock_check_completion.assert_called_once_with(mock_tiebreaker)
                        mock_db.session.commit.assert_called_once()

                        # Verify result
                        assert result == mock_rally_attempt

    def test_record_rally_attempt_tiebreaker_not_found(self):
        """Test recording a rally attempt when tiebreaker is not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerService.record_rally_attempt(
                        tiebreaker_id=1, player_id=10, points_scored=5, balls_pocketed=3
                    )

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_record_rally_attempt_wrong_status(self):
        """Test recording a rally attempt when tiebreaker is not in progress."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.status = TiebreakerStatus.COMPLETED.value

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            with pytest.raises(ValueError, match="Tiebreaker must be in progress"):
                TiebreakerService.record_rally_attempt(
                    tiebreaker_id=1, player_id=10, points_scored=5, balls_pocketed=3
                )

    def test_create_playoff_match_success(self):
        """Test creating a playoff match successfully."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.id = 1
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            mock_playoff_match = Mock()
            mock_playoff_match.id = 1

            with patch(
                "models.tiebreaker.services.PlayoffMatch"
            ) as mock_playoff_match_class:
                mock_playoff_match_class.return_value = mock_playoff_match

                result = TiebreakerService.create_playoff_match(
                    tiebreaker_id=1, match_number=1, distance=5, discipline="palla_9"
                )

                # Verify PlayoffMatch was created with correct parameters
                mock_playoff_match_class.assert_called_once_with(
                    tiebreaker_id=1,
                    match_number=1,
                    player1_id=10,
                    player2_id=20,
                    distance=5,
                    discipline="palla_9",
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_playoff_match)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_playoff_match

    def test_create_playoff_match_tiebreaker_not_found(self):
        """Test creating a playoff match when tiebreaker is not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerService.create_playoff_match(
                        tiebreaker_id=1, match_number=1
                    )

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_complete_playoff_match_success(self):
        """Test completing a playoff match successfully."""
        mock_playoff_match = Mock()
        mock_playoff_match.id = 1

        mock_tiebreaker = Mock()
        mock_playoff_match.tiebreaker = mock_tiebreaker

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_playoff_match

            with patch.object(
                TiebreakerService, "_check_playoff_completion"
            ) as mock_check_completion:
                result = TiebreakerService.complete_playoff_match(
                    playoff_match_id=1, winner_id=10, p1_score=3, p2_score=1
                )

                # Verify complete_match was called
                mock_playoff_match.complete_match.assert_called_once_with(10, 3, 1)

                # Verify completion check
                mock_check_completion.assert_called_once_with(mock_tiebreaker)

                # Verify database commit
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_playoff_match

    def test_complete_playoff_match_not_found(self):
        """Test completing a playoff match when it's not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerService.complete_playoff_match(
                        playoff_match_id=1, winner_id=10, p1_score=3, p2_score=1
                    )

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_get_tiebreaker_status_success(self):
        """Test getting tiebreaker status successfully."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.id = 1
        mock_tiebreaker.tiebreaker_type = TiebreakerType.SPOT_SHOT.value
        mock_tiebreaker.status = TiebreakerStatus.IN_PROGRESS.value
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.winner_id = None
        mock_tiebreaker.created_at = datetime(2023, 1, 1, 10, 0, 0)
        mock_tiebreaker.started_at = datetime(2023, 1, 1, 10, 30, 0)
        mock_tiebreaker.completed_at = None
        mock_tiebreaker.configuration = {"max_rounds": 5}

        mock_player1 = Mock()
        mock_player1.username = "player1"
        mock_tiebreaker.player1 = mock_player1

        mock_player2 = Mock()
        mock_player2.username = "player2"
        mock_tiebreaker.player2 = mock_player2

        mock_tiebreaker.get_score_summary.return_value = {
            "player1_score": 2,
            "player2_score": 1,
        }

        # Mock spot shots for spot shot tiebreaker
        mock_spot_shot = Mock()
        mock_spot_shot.round_number = 1
        mock_spot_shot.player_id = 10
        mock_spot_shot.order_in_round = 1
        mock_spot_shot.result = SpotShotResult.MADE.value
        mock_spot_shot.attempted_at = datetime(2023, 1, 1, 11, 0, 0)
        mock_tiebreaker.spot_shots = [mock_spot_shot]

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_tiebreaker

            result = TiebreakerService.get_tiebreaker_status(tiebreaker_id=1)

            # Verify the structure of the returned status
            assert result["id"] == 1
            assert result["type"] == TiebreakerType.SPOT_SHOT.value
            assert result["status"] == TiebreakerStatus.IN_PROGRESS.value
            assert result["winner_id"] is None
            assert result["configuration"] == {"max_rounds": 5}

            # Verify player information
            assert result["players"]["player1"]["id"] == 10
            assert result["players"]["player1"]["username"] == "player1"
            assert result["players"]["player1"]["score"] == 2
            assert result["players"]["player2"]["id"] == 20
            assert result["players"]["player2"]["username"] == "player2"
            assert result["players"]["player2"]["score"] == 1

            # Verify spot shots data
            assert len(result["spot_shots"]) == 1
            assert result["spot_shots"][0]["round"] == 1
            assert result["spot_shots"][0]["player_id"] == 10
            assert result["spot_shots"][0]["result"] == SpotShotResult.MADE.value

    def test_get_tiebreaker_status_not_found(self):
        """Test getting tiebreaker status when tiebreaker is not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerService.get_tiebreaker_status(tiebreaker_id=1)

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_check_spot_shot_completion_player1_wins(self):
        """Test spot shot completion when player 1 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"max_rounds": 5}

        # Create mock shots where player 1 made and player 2 missed
        mock_shot1 = Mock()
        mock_shot1.round_number = 1
        mock_shot1.player_id = 10
        mock_shot1.result = SpotShotResult.MADE.value

        mock_shot2 = Mock()
        mock_shot2.round_number = 1
        mock_shot2.player_id = 20
        mock_shot2.result = SpotShotResult.MISSED.value

        mock_tiebreaker.spot_shots = [mock_shot1, mock_shot2]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_spot_shot_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 1 as winner
            mock_complete.assert_called_once_with(10)

    def test_check_spot_shot_completion_player2_wins(self):
        """Test spot shot completion when player 2 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"max_rounds": 5}

        # Create mock shots where player 2 made and player 1 missed
        mock_shot1 = Mock()
        mock_shot1.round_number = 1
        mock_shot1.player_id = 10
        mock_shot1.result = SpotShotResult.MISSED.value

        mock_shot2 = Mock()
        mock_shot2.round_number = 1
        mock_shot2.player_id = 20
        mock_shot2.result = SpotShotResult.MADE.value

        mock_tiebreaker.spot_shots = [mock_shot1, mock_shot2]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_spot_shot_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 2 as winner
            mock_complete.assert_called_once_with(20)

    def test_check_rally_completion_player1_wins(self):
        """Test rally completion when player 1 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"target_score": 15}

        # Create mock attempts where player 1 reaches target score
        mock_attempt1 = Mock()
        mock_attempt1.player_id = 10
        mock_attempt1.points_scored = 10

        mock_attempt2 = Mock()
        mock_attempt2.player_id = 10
        mock_attempt2.points_scored = 8  # Total 18 points for player 1

        mock_attempt3 = Mock()
        mock_attempt3.player_id = 20
        mock_attempt3.points_scored = 7  # Player 2 has 7 points

        mock_tiebreaker.rally_attempts = [mock_attempt1, mock_attempt2, mock_attempt3]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_rally_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 1 as winner
            mock_complete.assert_called_once_with(10)

    def test_check_rally_completion_player2_wins(self):
        """Test rally completion when player 2 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"target_score": 15}

        # Create mock attempts where player 2 reaches target score
        mock_attempt1 = Mock()
        mock_attempt1.player_id = 10
        mock_attempt1.points_scored = 10

        mock_attempt2 = Mock()
        mock_attempt2.player_id = 20
        mock_attempt2.points_scored = 12

        mock_attempt3 = Mock()
        mock_attempt3.player_id = 20
        mock_attempt3.points_scored = 5  # Total 17 points for player 2

        mock_tiebreaker.rally_attempts = [mock_attempt1, mock_attempt2, mock_attempt3]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_rally_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 2 as winner
            mock_complete.assert_called_once_with(20)

    def test_check_playoff_completion_player1_wins(self):
        """Test playoff completion when player 1 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"best_of": 3}

        # Create mock matches where player 1 wins 2 out of 3
        mock_match1 = Mock()
        mock_match1.winner_id = 10

        mock_match2 = Mock()
        mock_match2.winner_id = 10

        mock_tiebreaker.playoff_matches = [mock_match1, mock_match2]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_playoff_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 1 as winner
            mock_complete.assert_called_once_with(10)

    def test_check_playoff_completion_player2_wins(self):
        """Test playoff completion when player 2 wins."""
        mock_tiebreaker = Mock()
        mock_tiebreaker.player1_id = 10
        mock_tiebreaker.player2_id = 20
        mock_tiebreaker.configuration = {"best_of": 3}

        # Create mock matches where player 2 wins 2 out of 3
        mock_match1 = Mock()
        mock_match1.winner_id = 20

        mock_match2 = Mock()
        mock_match2.winner_id = 20

        mock_tiebreaker.playoff_matches = [mock_match1, mock_match2]

        with patch.object(mock_tiebreaker, "complete") as mock_complete:
            TiebreakerService._check_playoff_completion(mock_tiebreaker)

            # Verify tiebreaker was completed with player 2 as winner
            mock_complete.assert_called_once_with(20)


class TestTiebreakerConfigurationService:
    """Test cases for TiebreakerConfigurationService class."""

    def test_create_default_configuration(self):
        """Test creating default tiebreaker configuration."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_config = Mock()
            mock_config.id = 1

            with patch(
                "models.tiebreaker.services.TiebreakerConfiguration"
            ) as mock_config_class:
                mock_config_class.return_value = mock_config

                result = TiebreakerConfigurationService.create_default_configuration(
                    campionato_id=100, gara_id=200
                )

                # Verify configuration was created with correct parameters
                mock_config_class.assert_called_once()
                args, kwargs = mock_config_class.call_args
                assert kwargs["campionato_id"] == 100
                assert kwargs["gara_id"] == 200
                assert kwargs["name"] == "Default Tiebreaker Rules"
                assert kwargs["is_default"] is True

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_config)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_config

    def test_get_configuration_for_match_found(self):
        """Test getting configuration for match when found."""
        mock_match = Mock()
        mock_match.gara_id = 50
        mock_match.gara = Mock()
        mock_match.gara.campionato_id = 100

        mock_config = Mock()
        mock_config.supports_discipline.return_value = True

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch(
                "models.tiebreaker.services.TiebreakerConfiguration"
            ) as mock_config_class:
                mock_query = Mock()
                mock_config_class.query.filter_by.return_value = mock_query
                mock_query.first.return_value = mock_config

                result = TiebreakerConfigurationService.get_configuration_for_match(
                    match_id=1, discipline="palla_8"
                )

                # Verify the configuration was found
                assert result == mock_config

    def test_get_configuration_for_match_not_found(self):
        """Test getting configuration for match when not found."""
        mock_match = Mock()
        mock_match.gara_id = None
        mock_match.gara = Mock()
        mock_match.gara.campionato_id = None

        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = mock_match

            with patch(
                "models.tiebreaker.services.TiebreakerConfiguration"
            ) as mock_config_class:
                mock_query = Mock()
                mock_config_class.query.filter_by.return_value = mock_query
                mock_query.first.return_value = None

                result = TiebreakerConfigurationService.get_configuration_for_match(
                    match_id=1, discipline="palla_8"
                )

                # Verify no configuration was found
                assert result is None

    def test_get_configuration_for_match_match_not_found(self):
        """Test getting configuration for match when match is not found."""
        with patch("models.tiebreaker.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with patch("flask.abort") as mock_abort:
                with pytest.raises(Exception):
                    TiebreakerConfigurationService.get_configuration_for_match(
                        match_id=1, discipline="palla_8"
                    )

                # Verify abort was called with 404
                mock_abort.assert_called_once_with(404)

    def test_get_tiebreaker_type_for_discipline_with_config(self):
        """Test getting tiebreaker type for discipline with configuration."""
        mock_config = Mock()
        mock_config.get_rule_for_discipline.return_value = {"type": "spot_shot"}

        result = TiebreakerConfigurationService.get_tiebreaker_type_for_discipline(
            discipline="palla_8", configuration=mock_config
        )

        # Verify the correct type was returned
        assert result == TiebreakerType.SPOT_SHOT

    def test_get_tiebreaker_type_for_discipline_palla_8(self):
        """Test getting tiebreaker type for palla_8 discipline."""
        result = TiebreakerConfigurationService.get_tiebreaker_type_for_discipline(
            discipline="palla_8"
        )

        # Verify spot shot type for palla_8
        assert result == TiebreakerType.SPOT_SHOT

    def test_get_tiebreaker_type_for_discipline_palla_9(self):
        """Test getting tiebreaker type for palla_9 discipline."""
        result = TiebreakerConfigurationService.get_tiebreaker_type_for_discipline(
            discipline="palla_9"
        )

        # Verify spot shot type for palla_9
        assert result == TiebreakerType.SPOT_SHOT

    def test_get_tiebreaker_type_for_discipline_straight_pool(self):
        """Test getting tiebreaker type for straight_pool discipline."""
        result = TiebreakerConfigurationService.get_tiebreaker_type_for_discipline(
            discipline="straight_pool"
        )

        # Verify rally type for straight_pool
        assert result == TiebreakerType.RALLY

    def test_get_tiebreaker_type_for_discipline_default(self):
        """Test getting tiebreaker type for unknown discipline (default)."""
        result = TiebreakerConfigurationService.get_tiebreaker_type_for_discipline(
            discipline="unknown_discipline"
        )

        # Verify playoff match type as default
        assert result == TiebreakerType.PLAYOFF_MATCH


if __name__ == "__main__":
    pytest.main([__file__])
