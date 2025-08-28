"""
Test module for models/exam/services.py
"""

import pytest
from unittest.mock import Mock, patch
from models.exam.services import ExamService


class TestExamService:
    """Test cases for ExamService class."""

    def test_create_exam(self, db_session):
        """Test creating a new exam."""
        with patch("models.exam.services.db") as mock_db:
            mock_exam = Mock()
            mock_exam.id = 1

            with patch("models.exam.services.Exam") as mock_exam_class:
                mock_exam_class.return_value = mock_exam

                result = ExamService.create_exam(
                    name="Test Exam",
                    director_id=1,
                    description="A test exam",
                    time_limit_minutes=60,
                )

                # Verify Exam was created with correct parameters
                mock_exam_class.assert_called_once()
                args, kwargs = mock_exam_class.call_args
                assert kwargs["name"] == "Test Exam"
                assert kwargs["director_id"] == 1
                assert kwargs["description"] == "A test exam"
                assert kwargs["time_limit_minutes"] == 60

                # Verify set_grading_criteria was called with default criteria
                mock_exam.set_grading_criteria.assert_called_once()
                args, kwargs = mock_exam.set_grading_criteria.call_args
                criteria = args[0]
                assert "grade_scale" in criteria
                assert criteria["grade_scale"]["A"] == 90

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_exam)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_exam

    def test_add_challenge_to_exam(self, db_session):
        """Test adding a challenge to an exam."""
        mock_exam = Mock()
        mock_exam.id = 1

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_exam

            # Mock the max order query
            mock_query = Mock()
            mock_db.session.query.return_value = mock_query
            mock_query.filter_by.return_value = mock_query
            mock_query.scalar.return_value = 5

            mock_exam_challenge = Mock()
            mock_exam_challenge.id = 1

            with patch(
                "models.exam.services.ExamChallenge"
            ) as mock_exam_challenge_class:
                mock_exam_challenge_class.return_value = mock_exam_challenge

                result = ExamService.add_challenge_to_exam(
                    exam_id=1, challenge_id=10, weight=1.5
                )

                # Verify ExamChallenge was created with correct parameters
                mock_exam_challenge_class.assert_called_once()
                args, kwargs = mock_exam_challenge_class.call_args
                assert kwargs["exam_id"] == 1
                assert kwargs["challenge_id"] == 10
                assert kwargs["order"] == 6  # 5 + 1
                assert kwargs["weight"] == 1.5

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_exam_challenge)
                mock_db.session.commit.assert_called_once()

                # Verify result
                assert result == mock_exam_challenge

    def test_remove_challenge_from_exam(self, db_session):
        """Test removing a challenge from an exam."""
        mock_exam_challenge = Mock()
        mock_exam_challenge.id = 1

        with patch("models.exam.services.ExamChallenge") as mock_exam_challenge_class:
            mock_query = Mock()
            mock_exam_challenge_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = mock_exam_challenge

            with patch("models.exam.services.db") as mock_db:
                ExamService.remove_challenge_from_exam(exam_id=1, challenge_id=10)

                # Verify database operations
                mock_db.session.delete.assert_called_once_with(mock_exam_challenge)
                mock_db.session.commit.assert_called_once()

    def test_reorder_exam_challenges(self, db_session):
        """Test reordering challenges in an exam."""
        mock_exam_challenge = Mock()
        mock_exam_challenge.id = 1

        with patch("models.exam.services.ExamChallenge") as mock_exam_challenge_class:
            mock_query = Mock()
            mock_exam_challenge_class.query.filter_by.return_value = mock_query
            mock_query.first.return_value = mock_exam_challenge

            with patch("models.exam.services.db") as mock_db:
                challenge_orders = [
                    {"challenge_id": 10, "order": 2},
                    {"challenge_id": 20, "order": 1},
                ]

                ExamService.reorder_exam_challenges(
                    exam_id=1, challenge_orders=challenge_orders
                )

                # Verify that each challenge's order was updated
                assert mock_exam_challenge.order == 1  # Last item in the list
                mock_db.session.commit.assert_called_once()

    def test_get_director_exams(self, db_session):
        """Test getting all exams created by a director."""
        mock_exam1 = Mock()
        mock_exam2 = Mock()

        with patch("models.exam.services.Exam") as mock_exam_class:
            mock_query = Mock()
            mock_exam_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_exam1, mock_exam2]

            result = ExamService.get_director_exams(director_id=1)

            # Verify query was called with correct parameters
            mock_exam_class.query.filter_by.assert_called_once_with(
                director_id=1, is_active=True
            )

            # Verify result
            assert len(result) == 2
            assert mock_exam1 in result
            assert mock_exam2 in result

    def test_get_available_exams(self, db_session):
        """Test getting all active exams."""
        mock_exam1 = Mock()
        mock_exam2 = Mock()

        with patch("models.exam.services.Exam") as mock_exam_class:
            mock_query = Mock()
            mock_exam_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = [mock_exam1, mock_exam2]

            result = ExamService.get_available_exams()

            # Verify query was called with correct parameters
            mock_exam_class.query.filter_by.assert_called_once_with(is_active=True)

            # Verify result
            assert len(result) == 2
            assert mock_exam1 in result
            assert mock_exam2 in result

    def test_start_exam_attempt_new(self, db_session):
        """Test starting a new exam attempt."""
        mock_attempt = Mock()
        mock_attempt.id = 1
        mock_attempt.completed = False

        with patch("models.exam.services.ExamAttempt") as mock_attempt_class:
            mock_attempt_class.return_value = mock_attempt

            # Mock the existing attempt query to return None (no existing attempt)
            with patch("models.exam.services.ExamAttempt.query") as mock_query_class:
                mock_query = Mock()
                mock_query_class.filter_by.return_value = mock_query
                mock_query.first.return_value = None

                with patch("models.exam.services.db") as mock_db:
                    result = ExamService.start_exam_attempt(user_id=1, exam_id=10)

                    # Verify ExamAttempt was created with correct parameters
                    mock_attempt_class.assert_called_once()
                    args, kwargs = mock_attempt_class.call_args
                    assert kwargs["user_id"] == 1
                    assert kwargs["exam_id"] == 10

                    # Verify database operations
                    mock_db.session.add.assert_called_once_with(mock_attempt)
                    mock_db.session.flush.assert_called_once()
                    mock_attempt.start_exam.assert_called_once()
                    mock_db.session.commit.assert_called_once()

                    # Verify result
                    assert result == mock_attempt

    def test_start_exam_attempt_existing(self, db_session):
        """Test starting an exam attempt when one already exists."""
        mock_existing_attempt = Mock()
        mock_existing_attempt.completed = False

        with patch("models.exam.services.ExamAttempt.query") as mock_query_class:
            mock_query = Mock()
            mock_query_class.filter_by.return_value = mock_query
            mock_query.first.return_value = mock_existing_attempt

            result = ExamService.start_exam_attempt(user_id=1, exam_id=10)

            # Verify existing attempt was returned
            assert result == mock_existing_attempt

    def test_complete_exam_challenge(self, db_session):
        """Test completing a specific challenge within an exam attempt."""
        mock_result = Mock()
        mock_result.id = 1

        mock_attempt = Mock()
        mock_attempt.id = 1
        mock_attempt.completed = False

        mock_progress = {"is_complete": True}
        mock_attempt.get_progress.return_value = mock_progress

        with patch("models.exam.services.ExamChallengeResult") as mock_result_class:
            mock_query = Mock()
            mock_result_class.query.filter_by.return_value = mock_query
            mock_query.first_or_404.return_value = mock_result

            with patch("models.exam.services.db") as mock_db:
                mock_db.session.get.return_value = mock_attempt

                result = ExamService.complete_exam_challenge(
                    exam_attempt_id=1,
                    exam_challenge_id=10,
                    score=85,
                    passed=True,
                    notes="Good work",
                )

                # Verify complete_challenge was called with correct parameters
                mock_result.complete_challenge.assert_called_once_with(
                    score=85, passed=True, notes="Good work"
                )

                # Verify database operations
                mock_db.session.commit.assert_called()

                # Verify attempt completion was triggered
                mock_attempt.complete_exam.assert_called_once()

                # Verify result
                assert result == mock_result

    def test_complete_exam_attempt(self, db_session):
        """Test manually completing an exam attempt."""
        mock_attempt = Mock()
        mock_attempt.id = 1
        mock_attempt.completed = False

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_attempt

            result = ExamService.complete_exam_attempt(
                exam_attempt_id=1, notes="Manual completion"
            )

            # Verify complete_exam was called with notes
            mock_attempt.complete_exam.assert_called_once_with(
                notes="Manual completion"
            )

            # Verify database commit
            mock_db.session.commit.assert_called_once()

            # Verify result
            assert result == mock_attempt

    def test_complete_exam_attempt_already_completed(self, db_session):
        """Test manually completing an exam attempt that is already completed."""
        mock_attempt = Mock()
        mock_attempt.id = 1
        mock_attempt.completed = True

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_attempt

            result = ExamService.complete_exam_attempt(exam_attempt_id=1)

            # Verify complete_exam was not called
            mock_attempt.complete_exam.assert_not_called()

            # Verify database commit was not called
            mock_db.session.commit.assert_not_called()

            # Verify result
            assert result == mock_attempt

    def test_get_user_exam_attempts(self, db_session):
        """Test getting all exam attempts for a user."""
        mock_attempt1 = Mock()
        mock_attempt2 = Mock()

        with patch("models.exam.services.ExamAttempt") as mock_attempt_class:
            mock_query = Mock()
            mock_attempt_class.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.all.return_value = [mock_attempt1, mock_attempt2]

            result = ExamService.get_user_exam_attempts(user_id=1)

            # Verify query was called with correct parameters
            mock_attempt_class.query.filter_by.assert_called_once_with(user_id=1)

            # Verify result
            assert len(result) == 2
            assert mock_attempt1 in result
            assert mock_attempt2 in result

    def test_get_exam_statistics(self, db_session):
        """Test getting detailed statistics for an exam."""
        mock_exam = Mock()
        mock_exam.id = 1

        mock_stats = {
            "total_attempts": 5,
            "unique_students": 3,
            "average_grade": "B",
            "grade_distribution": {"A": 2, "B": 2, "C": 1},
            "completion_rate": 80.0,
        }
        mock_exam.get_statistics.return_value = mock_stats

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_exam

            result = ExamService.get_exam_statistics(exam_id=1)

            # Verify get_statistics was called
            mock_exam.get_statistics.assert_called_once()

            # Verify result
            assert result == mock_stats

    def test_get_director_statistics(self, db_session):
        """Test getting statistics for all exams created by a director."""
        mock_exam1 = Mock()
        mock_exam1.id = 1
        mock_query1 = Mock()
        # Make the mock query iterable by setting its __iter__ method
        mock_query1.__iter__ = Mock(return_value=iter([]))
        # Mock the filter_by method to return the query mock when called
        # with completed=True
        mock_exam1.attempts.filter_by.side_effect = (
            lambda **kwargs: mock_query1 if kwargs.get("completed") is True else Mock()
        )
        mock_query1.count.return_value = 3

        # Mock the attempts query to return a mock that can be iterated
        mock_attempt1 = Mock()
        mock_attempt1.final_grade = "A"
        mock_attempt2 = Mock()
        mock_attempt2.final_grade = "B"
        mock_attempt3 = Mock()
        mock_attempt3.final_grade = "A"
        mock_query1.all.return_value = [mock_attempt1, mock_attempt2, mock_attempt3]
        # Make the mock query iterable with actual values
        mock_query1.__iter__.return_value = iter(
            [mock_attempt1, mock_attempt2, mock_attempt3]
        )

        mock_exam2 = Mock()
        mock_exam2.id = 2
        mock_query2 = Mock()
        # Make the mock query iterable by setting its __iter__ method
        mock_query2.__iter__ = Mock(return_value=iter([]))
        # Mock the filter_by method to return the query mock when called
        # with completed=True
        mock_exam2.attempts.filter_by.side_effect = (
            lambda **kwargs: mock_query2 if kwargs.get("completed") is True else Mock()
        )
        mock_query2.count.return_value = 2

        # Mock the attempts query to return a mock that can be iterated
        mock_attempt4 = Mock()
        mock_attempt4.final_grade = "C"
        mock_attempt5 = Mock()
        mock_attempt5.final_grade = "B"
        mock_query2.all.return_value = [mock_attempt4, mock_attempt5]
        # Make the mock query iterable with actual values
        mock_query2.__iter__.return_value = iter([mock_attempt4, mock_attempt5])

        mock_exams = [mock_exam1, mock_exam2]

        with patch.object(ExamService, "get_director_exams") as mock_get_exams:
            mock_get_exams.return_value = mock_exams

            result = ExamService.get_director_statistics(director_id=1)

            # Verify structure of result
            assert result["total_exams"] == 2
            assert result["total_attempts"] == 5
            assert "grade_distribution" in result
            assert len(result["exams"]) == 2

    def test_update_exam(self, db_session):
        """Test updating exam details."""
        mock_exam = Mock()
        mock_exam.id = 1

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_exam

            result = ExamService.update_exam(
                exam_id=1,
                name="Updated Exam",
                description="Updated description",
                grading_criteria={
                    "grade_scale": {"A": 95, "B": 85, "C": 75, "D": 65, "F": 0}
                },
                time_limit_minutes=90,
                is_active=False,
            )

            # Verify exam attributes were updated
            assert mock_exam.name == "Updated Exam"
            assert mock_exam.description == "Updated description"
            assert mock_exam.time_limit_minutes == 90
            assert mock_exam.is_active is False

            # Verify set_grading_criteria was called when grading_criteria is provided
            mock_exam.set_grading_criteria.assert_called_once_with(
                {"grade_scale": {"A": 95, "B": 85, "C": 75, "D": 65, "F": 0}}
            )

            # Verify database commit
            mock_db.session.commit.assert_called_once()

            # Verify result
            assert result == mock_exam

    def test_delete_exam(self, db_session):
        """Test deleting an exam (soft delete)."""
        mock_exam = Mock()
        mock_exam.id = 1
        mock_exam.is_active = True

        with patch("models.exam.services.db") as mock_db:
            mock_db.session.get.return_value = mock_exam

            ExamService.delete_exam(exam_id=1)

            # Verify exam was marked as inactive
            assert mock_exam.is_active is False

            # Verify database commit
            mock_db.session.commit.assert_called_once()

    def test_can_user_take_exam(self, db_session):
        """Test checking if a user can take an exam."""
        with patch("models.exam.services.ExamAttempt") as mock_attempt_class:
            mock_query = Mock()
            mock_attempt_class.query.filter_by.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = None  # No recent attempts

            result = ExamService.can_user_take_exam(user_id=1, exam_id=10)

            # For now, should always return True
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__])
