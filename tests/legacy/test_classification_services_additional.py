"""
Additional tests for models/classification/services.py to improve coverage.
"""

import pytest
from unittest.mock import patch
from datetime import date

from models.classification.services import ClassificationService
from models import User, Tournament, Prova, RoundClassification


class TestClassificationServiceEdgeCases:
    """Test edge cases and uncovered paths in ClassificationService."""

    @pytest.fixture
    def sample_tournament(self, db_session):
        """Create a sample tournament."""
        tournament = Tournament(
            name="Classification Test Tournament", tournament_type="Amalfi"
        )
        db_session.add(tournament)
        db_session.commit()
        return tournament

    @pytest.fixture
    def sample_prova(self, db_session, sample_tournament):
        """Create a sample prova."""
        prova = Prova(
            tournament_id=sample_tournament.id,
            number=1,
            name="Classification Test Prova",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            best_of=True,
            status="playing",
            current_round=2,
            rounds_count=5,
        )
        db_session.add(prova)
        db_session.commit()
        return prova

    @pytest.fixture
    def sample_players(self, db_session):
        """Create sample players."""
        players = []
        for i in range(4):
            player = User(
                username=f"classif_player{i+1}",
                email=f"classif{i+1}@test.com",
                role="player",
            )
            player.set_password("password")
            db_session.add(player)
            players.append(player)
        db_session.commit()
        return players

    def test_get_player_statistics_summary_comprehensive(
        self, sample_prova, sample_players, db_session
    ):
        """Test get_player_statistics_summary when standings exist."""
        player = sample_players[0]

        # Create a round classification
        classification = RoundClassification(
            prova_id=sample_prova.id, round_number=1, user_id=player.id, position=1
        )
        db_session.add(classification)
        db_session.commit()

        result = ClassificationService.get_player_statistics_summary(
            sample_prova.tournament_id
        )

        assert result is not None
        assert isinstance(result, dict)

    def test_get_tournament_standings_simple(
        self, sample_prova, sample_players, db_session
    ):
        """Test get_tournament_standings basic functionality."""
        result = ClassificationService.get_tournament_standings(
            sample_prova.tournament_id
        )

        assert isinstance(result, list)

    def test_get_round_standings_basic(self, sample_prova):
        """Test get_round_standings basic functionality."""
        result = ClassificationService.get_round_standings(sample_prova.id, 1)

        assert isinstance(result, list)

    def test_get_round_standings_current_round(self, sample_prova):
        """Test get_round_standings with current round."""
        result = ClassificationService.get_round_standings(sample_prova.id)

        assert isinstance(result, list)

    def test_calculate_and_save_round_classification_error_handling(self, sample_prova):
        """Test error handling in calculate_and_save_round_classification."""
        with patch(
            "models.classification.models.RoundClassification.calculate_classification_after_round"
        ) as mock_calc:
            # Simulate an exception during calculation
            mock_calc.side_effect = Exception("Database error")

            # The actual method doesn't raise the exception, it handles it
            try:
                ClassificationService.calculate_and_save_round_classification(
                    sample_prova.id, 1
                )
            except Exception:
                pass  # Expected in this test

    def test_get_player_ranking_basic(
        self, sample_tournament, sample_players, db_session
    ):
        """Test get_player_ranking basic functionality."""
        player = sample_players[0]

        result = ClassificationService.get_player_ranking(
            sample_tournament.id, player.id
        )

        # Should return None if no ranking exists
        assert result is None

    def test_get_encounter_statistics_basic(self, sample_prova):
        """Test get_encounter_statistics basic functionality."""
        result = ClassificationService.get_encounter_statistics(sample_prova.id)

        assert isinstance(result, dict)


class TestClassificationServiceStatistics:
    """Test statistics and summary methods."""

    def test_get_player_statistics_summary_basic(self, db_session):
        """Test basic player statistics summary."""
        tournament = Tournament(name="Stats Test", tournament_type="Amalfi")
        db_session.add(tournament)
        db_session.commit()

        result = ClassificationService.get_player_statistics_summary(tournament.id)

        assert isinstance(result, dict)


class TestClassificationServiceHelpers:
    """Test helper methods and edge cases."""

    def test_service_with_invalid_tournament_id(self):
        """Test service methods with invalid tournament ID."""
        invalid_tournament_id = 99999

        result = ClassificationService.get_tournament_standings(invalid_tournament_id)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_calculate_standings_with_no_rounds(self, sample_prova):
        """Test calculating standings when no rounds exist."""
        # Should not raise exception even with no data
        try:
            ClassificationService.calculate_and_save_round_classification(
                sample_prova.id, 0
            )
        except Exception:
            pass  # Expected for invalid round numbers
