"""
Test module for models/classification/services.py
This module aims to improve test coverage for ClassificationService, RoundClassificationService, and PlayerEncounterService.
"""

import pytest
from unittest.mock import Mock, patch

from models.classification.services import (
    ClassificationService,
    RoundClassificationService,
    PlayerEncounterService,
)


class TestClassificationService:
    """Test cases for ClassificationService class."""

    def test_get_scoring_policy_classic(self):
        """Test getting classic scoring policy."""
        mock_tournament = Mock()
        mock_tournament.scoring_policy = "classic"

        result = ClassificationService._get_scoring_policy(mock_tournament)

        assert result.__class__.__name__ == "ClassicScoringPolicy"

    def test_get_scoring_policy_fargo(self):
        """Test getting Fargo scoring policy."""
        mock_tournament = Mock()
        mock_tournament.scoring_policy = "fargo"

        result = ClassificationService._get_scoring_policy(mock_tournament)

        assert result.__class__.__name__ == "FargoRatingScoringPolicy"

    def test_get_scoring_policy_elo(self):
        """Test getting Elo scoring policy."""
        mock_tournament = Mock()
        mock_tournament.scoring_policy = "elo"

        result = ClassificationService._get_scoring_policy(mock_tournament)

        assert result.__class__.__name__ == "EloRatingScoringPolicy"

    def test_get_scoring_policy_default(self):
        """Test getting default scoring policy for unknown policy."""
        mock_tournament = Mock()
        mock_tournament.scoring_policy = "unknown"

        result = ClassificationService._get_scoring_policy(mock_tournament)

        assert result.__class__.__name__ == "ClassicScoringPolicy"

    def test_update_tournament_classification_success(self):
        """Test updating tournament classification successfully."""
        with patch("models.classification.services.db") as mock_db:
            # Mock tournament
            mock_tournament = Mock()
            mock_tournament.scoring_policy = "classic"

            # Mock db.session.get
            mock_db.session.get.return_value = mock_tournament

            # Mock provas and matches
            mock_prova1 = Mock()
            mock_prova2 = Mock()
            mock_match1 = Mock()
            mock_match1.status = "completed"
            mock_match1.is_bye = False
            mock_match1.player1_id = 1
            mock_match1.player2_id = 2
            mock_match1.player1_score = 3
            mock_match1.player2_score = 1
            mock_match2 = Mock()
            mock_match2.status = "completed"
            mock_match2.is_bye = False
            mock_match2.player1_id = 2
            mock_match2.player2_id = 3
            mock_match2.player1_score = 2
            mock_match2.player2_score = 2

            mock_prova1.matches = [mock_match1]
            mock_prova2.matches = [mock_match2]

            # Mock bulk_load_relationships
            with patch(
                "models.classification.services.bulk_load_relationships"
            ) as mock_bulk_load:
                mock_bulk_query = Mock()
                mock_bulk_query.all.return_value = [mock_prova1, mock_prova2]
                mock_bulk_load.return_value = mock_bulk_query

                # Mock players
                mock_player1 = Mock()
                mock_player1.id = 1
                mock_player2 = Mock()
                mock_player2.id = 2
                mock_player3 = Mock()
                mock_player3.id = 3

                # Mock user query
                mock_user_query = Mock()
                mock_user_filtered_query = Mock()
                mock_db.session.query.return_value = mock_user_query
                mock_user_query.filter.return_value = mock_user_filtered_query
                mock_user_filtered_query.all.return_value = [
                    mock_player1,
                    mock_player2,
                    mock_player3,
                ]

                # Mock scoring policy
                with patch(
                    "models.classification.services.ClassicScoringPolicy"
                ) as mock_policy_class:
                    mock_policy = Mock()
                    mock_policy.calculate_standings.return_value = [
                        (
                            mock_player1,
                            {"matches_won": 1, "rack_diff": 2, "provas_played": [1]},
                        ),
                        (
                            mock_player2,
                            {"matches_won": 1, "rack_diff": 0, "provas_played": [1, 2]},
                        ),
                        (
                            mock_player3,
                            {"matches_won": 0, "rack_diff": -2, "provas_played": [2]},
                        ),
                    ]
                    mock_policy_class.return_value = mock_policy

                    # Mock existing classifications
                    mock_existing_classification = Mock()
                    mock_existing_classification.user_id = 1

                    mock_classification_query = Mock()
                    mock_classification_filtered_query = Mock()
                    mock_db.session.query.side_effect = [
                        mock_classification_query,
                        mock_user_query,
                        mock_classification_query,
                    ]
                    mock_classification_query.filter_by.return_value = (
                        mock_classification_filtered_query
                    )
                    mock_classification_filtered_query.all.return_value = [
                        mock_existing_classification
                    ]

                    # Mock db.session.add and commit
                    mock_db.session.add = Mock()
                    mock_db.session.commit = Mock()

                    # Call the method
                    result = ClassificationService.update_tournament_classification(1)

                    # Verify
                    assert len(result) == 3
                    mock_db.session.get.assert_called_once()

    def test_update_tournament_classification_not_found(self):
        """Test updating tournament classification when tournament doesn't exist."""
        # Patch the specific method at the correct location
        with patch("models.classification.services.db.session.get") as mock_get:
            mock_get.return_value = None

            # Call the method and expect ValueError
            with pytest.raises(ValueError, match="Tournament 1 not found"):
                ClassificationService.update_tournament_classification(1)

    def test_get_tournament_standings(self):
        """Test getting tournament standings."""
        mock_classifications = [Mock(), Mock(), Mock()]

        # Patch the specific method at the correct location
        with patch("models.classification.services.db.session.query") as mock_query:
            # Set up the mock chain
            mock_query_instance = Mock()
            mock_filter_by = Mock()
            mock_options = Mock()
            mock_order_by = Mock()

            mock_query.return_value = mock_query_instance
            mock_query_instance.filter_by.return_value = mock_filter_by
            mock_filter_by.options.return_value = mock_options
            mock_options.order_by.return_value = mock_order_by
            mock_order_by.all.return_value = mock_classifications

            result = ClassificationService.get_tournament_standings(1)

            # Check the result
            assert len(result) == 3
            # Verify the filter_by was called with correct arguments
            mock_query_instance.filter_by.assert_called_once_with(tournament_id=1)

    def test_get_player_statistics_summary_no_standings(self):
        """Test getting player statistics summary with no standings."""
        with patch.object(
            ClassificationService, "get_tournament_standings", return_value=[]
        ) as mock_get_standings:
            result = ClassificationService.get_player_statistics_summary(1)

            assert result["total_players"] == 0
            assert result["completed"] is False

    def test_invalidate_tournament_cache(self):
        """Test invalidating tournament cache."""
        with patch(
            "models.classification.services.cache_manager"
        ) as mock_cache_manager:
            ClassificationService.invalidate_tournament_cache(1)

            mock_cache_manager.invalidate_by_tags.assert_called_once_with(
                ["tournament:1"]
            )

    def test_get_player_statistics_summary_with_standings(self):
        """Test getting player statistics summary with standings."""
        mock_classification1 = Mock()
        mock_classification1.total_matches_won = 5
        mock_classification1.total_point_difference = 10
        mock_classification1.user_id = 1
        mock_user1 = Mock()
        mock_user1.username = "Player1"
        mock_classification1.user = mock_user1

        mock_classification2 = Mock()
        mock_classification2.total_matches_won = 3
        mock_classification2.total_point_difference = 5
        mock_classification2.user_id = 2
        mock_user2 = Mock()
        mock_user2.username = "Player2"
        mock_classification2.user = mock_user2

        mock_standings = [mock_classification1, mock_classification2]

        with patch(
            "models.classification.services.ClassificationService.get_tournament_standings"
        ) as mock_get_standings:
            mock_get_standings.return_value = mock_standings

            result = ClassificationService.get_player_statistics_summary(1)

            assert result["total_players"] == 2
            assert result["total_matches_played"] == 8
            assert result["average_matches_per_player"] == 4.0
            assert result["leader"]["user_id"] == 1
            assert result["leader"]["username"] == "Player1"
            assert result["leader"]["matches_won"] == 5
            assert result["leader"]["point_difference"] == 10

    def test_get_player_statistics_summary_no_standings(self):
        """Test getting player statistics summary with no standings."""
        with patch.object(
            ClassificationService, "get_tournament_standings"
        ) as mock_get_standings:
            mock_get_standings.return_value = []

            result = ClassificationService.get_player_statistics_summary(1)

            assert result["total_players"] == 0
            assert result["completed"] is False


class TestRoundClassificationService:
    """Test cases for RoundClassificationService class."""

    def test_get_round_standings(self):
        """Test getting round standings."""
        mock_classifications = [Mock(), Mock()]

        with patch("models.classification.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_options_query = Mock()
            mock_order_query = Mock()

            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.options.return_value = mock_options_query
            mock_options_query.order_by.return_value = mock_order_query
            mock_order_query.all.return_value = mock_classifications

            result = RoundClassificationService.get_round_standings(1, 2)

            assert result == mock_classifications
            mock_query.filter_by.assert_called_once_with(prova_id=1, round_number=2)

    def test_get_player_progression(self):
        """Test getting player progression."""
        mock_classifications = [Mock(), Mock(), Mock()]

        with patch("models.classification.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_order_query = Mock()

            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.order_by.return_value = mock_order_query
            mock_order_query.all.return_value = mock_classifications

            result = RoundClassificationService.get_player_progression(1, 1)

            assert result == mock_classifications
            mock_query.filter_by.assert_called_once_with(prova_id=1, user_id=1)

    def test_calculate_and_save_round_classification(self):
        """Test calculating and saving round classification."""
        mock_classifications = [Mock(), Mock()]

        with patch(
            "models.classification.services.RoundClassification"
        ) as mock_round_classification:
            mock_round_classification.calculate_classification_after_round = Mock()

            with patch(
                "models.classification.services.RoundClassificationService.get_round_standings"
            ) as mock_get_standings:
                mock_get_standings.return_value = mock_classifications

                result = (
                    RoundClassificationService.calculate_and_save_round_classification(
                        1, 2
                    )
                )

                assert result == mock_classifications
                mock_round_classification.calculate_classification_after_round.assert_called_once_with(
                    1, 2
                )


class TestPlayerEncounterService:
    """Test cases for PlayerEncounterService class."""

    def test_get_player_encounters(self):
        """Test getting player encounters."""
        mock_encounters = [Mock(), Mock()]

        with patch("models.classification.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()

            mock_db.session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = mock_encounters

            result = PlayerEncounterService.get_player_encounters(1, 1)

            assert result == mock_encounters

    def test_get_available_opponents_with_available(self):
        """Test getting available opponents with some available."""
        candidate_ids = [2, 3, 4]
        encounter_matrix = {(1, 2): True, (1, 3): False, (1, 4): True}

        with patch(
            "models.classification.services.PlayerEncounterService.get_encounter_matrix"
        ) as mock_get_matrix:
            mock_get_matrix.return_value = encounter_matrix

            result = PlayerEncounterService.get_available_opponents(1, 1, candidate_ids)

            assert result == [3]  # Only player 3 hasn't been played

    def test_get_available_opponents_no_available(self):
        """Test getting available opponents with none available."""
        candidate_ids = [2, 3]
        encounter_matrix = {(1, 2): True, (1, 3): True}

        with patch(
            "models.classification.services.PlayerEncounterService.get_encounter_matrix"
        ) as mock_get_matrix:
            mock_get_matrix.return_value = encounter_matrix

            result = PlayerEncounterService.get_available_opponents(1, 1, candidate_ids)

            assert result == []  # No available opponents

    def test_record_match_encounters_bye_match(self):
        """Test recording match encounters for a bye match."""
        mock_match = Mock()
        mock_match.is_bye = True
        mock_match.player2_id = None

        with patch(
            "models.classification.services.PlayerEncounter"
        ) as mock_player_encounter:
            PlayerEncounterService.record_match_encounters(mock_match)

            mock_player_encounter.record_encounter.assert_not_called()

    def test_record_match_encounters_regular_match(self):
        """Test recording match encounters for a regular match."""
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.player2_id = 2
        mock_match.prova_id = 1
        mock_match.player1_id = 1
        mock_match.round_number = 1

        with patch(
            "models.classification.services.PlayerEncounter"
        ) as mock_player_encounter:
            PlayerEncounterService.record_match_encounters(mock_match)

            mock_player_encounter.record_encounter.assert_called_once_with(
                prova_id=1, player1_id=1, player2_id=2, round_number=1
            )

    def test_get_encounter_matrix(self):
        """Test getting encounter matrix."""
        mock_encounter1 = Mock()
        mock_encounter1.player1_id = 1
        mock_encounter1.player2_id = 2

        mock_encounter2 = Mock()
        mock_encounter2.player1_id = 1
        mock_encounter2.player2_id = 3

        mock_encounters = [mock_encounter1, mock_encounter2]

        with patch("models.classification.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()

            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = mock_encounters

            result = PlayerEncounterService.get_encounter_matrix(1)

            # Should have both directions for each encounter
            assert (1, 2) in result
            assert (2, 1) in result
            assert (1, 3) in result
            assert (3, 1) in result
            assert result[(1, 2)] is True
            assert result[(2, 1)] is True
            assert result[(1, 3)] is True
            assert result[(3, 1)] is True

    def test_get_encounter_statistics_with_encounters(self):
        """Test getting encounter statistics with encounters."""
        mock_encounter1 = Mock()
        mock_encounter1.player1_id = 1
        mock_encounter1.player2_id = 2

        mock_encounter2 = Mock()
        mock_encounter2.player1_id = 1
        mock_encounter2.player2_id = 3

        mock_encounter3 = Mock()
        mock_encounter3.player1_id = 2
        mock_encounter3.player2_id = 3

        mock_encounters = [mock_encounter1, mock_encounter2, mock_encounter3]

        with patch("models.classification.services.db") as mock_db:
            mock_query = Mock()
            mock_filtered_query = Mock()

            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = mock_encounters

            result = PlayerEncounterService.get_encounter_statistics(1)

            assert result["total_encounters"] == 3
            assert result["unique_players"] == 3
            assert (
                result["total_possible_encounters"] == 3
            )  # 3 players can have 3 encounters
            assert result["completion_rate_percent"] == 100.0

    def test_get_encounter_statistics_no_encounters(self):
        """Test getting encounter statistics with no encounters."""
        # Patch the specific method at the correct location
        with patch("models.classification.services.db.session.query") as mock_query:
            # Set up the mock chain
            mock_query_instance = Mock()
            mock_filter_by = Mock()

            mock_query.return_value = mock_query_instance
            mock_query_instance.filter_by.return_value = mock_filter_by
            mock_filter_by.all.return_value = []

            result = PlayerEncounterService.get_encounter_statistics(1)

            assert result["total_encounters"] == 0
            assert result["unique_players"] == 0


if __name__ == "__main__":
    pytest.main([__file__])
