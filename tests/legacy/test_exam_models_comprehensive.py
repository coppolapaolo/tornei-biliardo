"""
Comprehensive tests for models/exam/models.py
Targeting 130 statements with 0% coverage for maximum impact toward 90% goal.
"""

import pytest
import json
from unittest.mock import Mock, patch, PropertyMock
from datetime import datetime, timedelta

from models.exam.models import Exam, ExamChallenge, ExamAttempt, ExamChallengeResult


class TestExamModel:
    """Comprehensive tests for Exam model."""

    def test_exam_creation(self):
        """Test basic exam creation."""
        exam = Exam(
            name="Test Exam",
            description="Test Description",
            director_id=1,
            grading_criteria='{"A": 90, "B": 80, "C": 70}',
            is_active=True,
            time_limit_minutes=60
        )
        
        assert exam.name == "Test Exam"
        assert exam.description == "Test Description"
        assert exam.director_id == 1
        assert exam.is_active is True
        assert exam.time_limit_minutes == 60

    def test_get_grading_criteria_valid_json(self):
        """Test get_grading_criteria with valid JSON."""
        criteria = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}
        exam = Exam(grading_criteria=json.dumps(criteria))
        
        result = exam.get_grading_criteria()
        
        assert result == criteria

    def test_get_grading_criteria_invalid_json(self):
        """Test get_grading_criteria with invalid JSON."""
        exam = Exam(grading_criteria="invalid json")
        
        result = exam.get_grading_criteria()
        
        assert result == {}

    def test_get_grading_criteria_none(self):
        """Test get_grading_criteria with None value."""
        exam = Exam(grading_criteria=None)
        
        result = exam.get_grading_criteria()
        
        assert result == {}

    def test_set_grading_criteria(self):
        """Test set_grading_criteria method."""
        exam = Exam()
        criteria = {"A": 95, "B": 85, "C": 75, "D": 65, "F": 0}
        
        exam.set_grading_criteria(criteria)
        
        assert exam.grading_criteria == json.dumps(criteria)
        assert exam.get_grading_criteria() == criteria

    def test_calculate_grade_zero_max_score(self):
        """Test calculate_grade with zero max possible score."""
        exam = Exam(grading_criteria='{"A": 90, "B": 80}')
        
        grade = exam.calculate_grade(50, 0)
        
        assert grade == "F"

    def test_calculate_grade_with_custom_criteria(self):
        """Test calculate_grade with custom grading criteria."""
        criteria = {"A": 95, "B": 85, "C": 75, "D": 65, "F": 0}
        exam = Exam(grading_criteria=json.dumps(criteria))
        
        # Test A grade (100%)
        assert exam.calculate_grade(100, 100) == "A"
        
        # Test B grade (90%)
        assert exam.calculate_grade(90, 100) == "B"
        
        # Test C grade (80%)
        assert exam.calculate_grade(80, 100) == "C"
        
        # Test D grade (70%)
        assert exam.calculate_grade(70, 100) == "D"
        
        # Test F grade (50%)
        assert exam.calculate_grade(50, 100) == "F"

    def test_calculate_grade_with_default_criteria(self):
        """Test calculate_grade with default criteria when not configured."""
        exam = Exam(grading_criteria='{}')  # Empty criteria, should use default
        
        # Test with default scale: A=90, B=80, C=70, D=60, F=0
        assert exam.calculate_grade(95, 100) == "A"
        assert exam.calculate_grade(85, 100) == "B"
        assert exam.calculate_grade(75, 100) == "C"
        assert exam.calculate_grade(65, 100) == "D"
        assert exam.calculate_grade(55, 100) == "F"

    def test_calculate_grade_exact_thresholds(self):
        """Test calculate_grade at exact threshold values."""
        exam = Exam(grading_criteria='{"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}')
        
        # Test exact threshold values
        assert exam.calculate_grade(90, 100) == "A"
        assert exam.calculate_grade(80, 100) == "B"
        assert exam.calculate_grade(70, 100) == "C"
        assert exam.calculate_grade(60, 100) == "D"

    @patch.object(Exam, 'attempts')
    def test_get_statistics_no_attempts(self, mock_attempts):
        """Test get_statistics when no attempts exist."""
        mock_attempts.filter_by.return_value.count.return_value = 0
        mock_attempts.count.return_value = 0
        
        exam = Exam()
        
        stats = exam.get_statistics()
        
        expected = {
            "total_attempts": 0,
            "unique_students": 0,
            "average_grade": "N/A",
            "grade_distribution": {},
            "completion_rate": 0,
        }
        assert stats == expected

    @patch.object(Exam, 'attempts')
    def test_get_statistics_with_attempts(self, mock_attempts):
        """Test get_statistics with completed attempts."""
        # Mock completed attempts
        mock_attempt1 = Mock()
        mock_attempt1.final_grade = "A"
        mock_attempt2 = Mock()
        mock_attempt2.final_grade = "B"
        mock_attempt3 = Mock()
        mock_attempt3.final_grade = "A"
        
        mock_completed = Mock()
        mock_completed.count.return_value = 3
        mock_completed.with_entities.return_value.distinct.return_value.count.return_value = 2
        mock_completed.all.return_value = [mock_attempt1, mock_attempt2, mock_attempt3]
        
        mock_attempts.filter_by.return_value = mock_completed
        mock_attempts.count.return_value = 4  # 4 started, 3 completed
        
        exam = Exam()
        
        stats = exam.get_statistics()
        
        assert stats["total_attempts"] == 3
        assert stats["unique_students"] == 2
        assert stats["average_grade"] == "A"  # (4+3+4)/3 = 3.67 ≈ A
        assert stats["grade_distribution"] == {"A": 2, "B": 1}
        assert stats["completion_rate"] == 75.0  # 3/4 * 100

    @patch.object(Exam, 'attempts')
    def test_get_statistics_edge_cases(self, mock_attempts):
        """Test get_statistics edge cases."""
        # Mock with F grades and unknown grades
        mock_attempt1 = Mock()
        mock_attempt1.final_grade = "F"
        mock_attempt2 = Mock()
        mock_attempt2.final_grade = "X"  # Unknown grade
        
        mock_completed = Mock()
        mock_completed.count.return_value = 2
        mock_completed.with_entities.return_value.distinct.return_value.count.return_value = 2
        mock_completed.all.return_value = [mock_attempt1, mock_attempt2]
        
        mock_attempts.filter_by.return_value = mock_completed
        mock_attempts.count.return_value = 2
        
        exam = Exam()
        
        stats = exam.get_statistics()
        
        assert stats["total_attempts"] == 2
        assert stats["average_grade"] == "F"  # (0+0)/2 = 0 = F
        assert stats["grade_distribution"] == {"F": 1, "X": 1}

    @patch.object(Exam, 'challenges')
    def test_get_max_possible_score(self, mock_challenges):
        """Test get_max_possible_score calculation."""
        # Mock exam challenges
        mock_challenge1 = Mock()
        mock_challenge1.challenge.max_score = 100
        mock_challenge2 = Mock()
        mock_challenge2.challenge.max_score = 50
        mock_challenge3 = Mock()
        mock_challenge3.challenge.max_score = 75
        
        mock_challenges.all.return_value = [mock_challenge1, mock_challenge2, mock_challenge3]
        
        exam = Exam()
        
        total = exam.get_max_possible_score()
        
        assert total == 225  # 100 + 50 + 75

    @patch.object(Exam, 'challenges')
    def test_get_max_possible_score_no_challenges(self, mock_challenges):
        """Test get_max_possible_score with no challenges."""
        mock_challenges.all.return_value = []
        
        exam = Exam()
        
        total = exam.get_max_possible_score()
        
        assert total == 0

    def test_exam_repr(self):
        """Test Exam __repr__ method."""
        exam = Exam(name="Physics Exam")
        
        repr_str = repr(exam)
        
        assert repr_str == "<Exam Physics Exam>"


class TestExamChallengeModel:
    """Comprehensive tests for ExamChallenge model."""

    def test_exam_challenge_creation(self):
        """Test basic ExamChallenge creation."""
        exam_challenge = ExamChallenge(
            exam_id=1,
            challenge_id=2,
            order=1,
            weight=1.5
        )
        
        assert exam_challenge.exam_id == 1
        assert exam_challenge.challenge_id == 2
        assert exam_challenge.order == 1
        assert exam_challenge.weight == 1.5

    def test_exam_challenge_default_weight(self):
        """Test ExamChallenge with default weight."""
        exam_challenge = ExamChallenge(
            exam_id=1,
            challenge_id=2,
            order=1
        )
        
        assert exam_challenge.weight == 1.0

    def test_get_weighted_max_score(self):
        """Test get_weighted_max_score calculation."""
        mock_challenge = Mock()
        mock_challenge.max_score = 100
        
        exam_challenge = ExamChallenge(weight=1.5)
        exam_challenge.challenge = mock_challenge
        
        weighted_score = exam_challenge.get_weighted_max_score()
        
        assert weighted_score == 150  # 100 * 1.5 = 150

    def test_get_weighted_max_score_default_weight(self):
        """Test get_weighted_max_score with default weight."""
        mock_challenge = Mock()
        mock_challenge.max_score = 80
        
        exam_challenge = ExamChallenge(weight=1.0)
        exam_challenge.challenge = mock_challenge
        
        weighted_score = exam_challenge.get_weighted_max_score()
        
        assert weighted_score == 80

    def test_exam_challenge_repr(self):
        """Test ExamChallenge __repr__ method."""
        mock_exam = Mock()
        mock_exam.name = "Physics Exam"
        mock_challenge = Mock()
        mock_challenge.name = "Mechanics Challenge"
        
        exam_challenge = ExamChallenge(order=2)
        exam_challenge.exam = mock_exam
        exam_challenge.challenge = mock_challenge
        
        repr_str = repr(exam_challenge)
        
        assert repr_str == "<ExamChallenge Physics Exam -> Mechanics Challenge (2)>"


class TestExamAttemptModel:
    """Comprehensive tests for ExamAttempt model."""

    def test_exam_attempt_creation(self):
        """Test basic ExamAttempt creation."""
        now = datetime.now()
        exam_attempt = ExamAttempt(
            exam_id=1,
            user_id=2,
            started_at=now,
            completed=False,
            total_score=85,
            max_possible_score=100,
            final_grade="B",
            notes="Good performance"
        )
        
        assert exam_attempt.exam_id == 1
        assert exam_attempt.user_id == 2
        assert exam_attempt.started_at == now
        assert exam_attempt.completed is False
        assert exam_attempt.total_score == 85
        assert exam_attempt.max_possible_score == 100
        assert exam_attempt.final_grade == "B"
        assert exam_attempt.notes == "Good performance"

    @patch('models.exam.models.datetime')
    @patch('models.exam.models.db')
    @patch.object(ExamAttempt, 'exam')
    def test_start_exam(self, mock_exam, mock_db, mock_datetime):
        """Test start_exam method."""
        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        # Mock exam challenges
        mock_challenge1 = Mock()
        mock_challenge1.id = 1
        mock_challenge2 = Mock() 
        mock_challenge2.id = 2
        mock_exam.challenges.all.return_value = [mock_challenge1, mock_challenge2]
        
        exam_attempt = ExamAttempt(id=1)
        
        exam_attempt.start_exam()
        
        assert exam_attempt.started_at == mock_now
        # Should create 2 ExamChallengeResult objects
        assert mock_db.session.add.call_count == 2

    @patch('models.exam.models.datetime')
    @patch.object(ExamAttempt, 'challenge_results')
    @patch.object(ExamAttempt, 'exam')
    def test_complete_exam_with_notes(self, mock_exam, mock_challenge_results, mock_datetime):
        """Test complete_exam method with notes."""
        mock_now = datetime(2024, 1, 1, 14, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        # Mock challenge results
        mock_result1 = Mock()
        mock_result1.score = 80
        mock_result1.exam_challenge.weight = 1.0
        mock_result1.exam_challenge.get_weighted_max_score.return_value = 100
        
        mock_result2 = Mock()
        mock_result2.score = 90
        mock_result2.exam_challenge.weight = 1.5
        mock_result2.exam_challenge.get_weighted_max_score.return_value = 150
        
        mock_challenge_results.all.return_value = [mock_result1, mock_result2]
        
        # Mock exam grade calculation
        mock_exam.calculate_grade.return_value = "B"
        
        exam_attempt = ExamAttempt()
        
        exam_attempt.complete_exam("Excellent work!")
        
        assert exam_attempt.completed is True
        assert exam_attempt.completed_at == mock_now
        assert exam_attempt.notes == "Excellent work!"
        assert exam_attempt.total_score == 215  # 80*1.0 + 90*1.5 = 80 + 135 = 215
        assert exam_attempt.max_possible_score == 250  # 100 + 150
        assert exam_attempt.final_grade == "B"
        mock_exam.calculate_grade.assert_called_once_with(215, 250)

    @patch('models.exam.models.datetime')
    @patch.object(ExamAttempt, 'challenge_results')
    @patch.object(ExamAttempt, 'exam')
    def test_complete_exam_without_notes(self, mock_exam, mock_challenge_results, mock_datetime):
        """Test complete_exam method without notes."""
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 14, 0, 0)
        
        # Mock challenge results with None score
        mock_result1 = Mock()
        mock_result1.score = None
        mock_result1.exam_challenge.get_weighted_max_score.return_value = 100
        
        mock_challenge_results.all.return_value = [mock_result1]
        mock_exam.calculate_grade.return_value = "F"
        
        exam_attempt = ExamAttempt()
        
        exam_attempt.complete_exam()
        
        assert exam_attempt.completed is True
        assert exam_attempt.notes is None
        assert exam_attempt.total_score == 0  # None score doesn't count
        assert exam_attempt.max_possible_score == 100
        assert exam_attempt.final_grade == "F"

    @patch.object(ExamAttempt, 'exam')
    @patch.object(ExamAttempt, 'challenge_results')
    def test_get_progress_complete(self, mock_challenge_results, mock_exam):
        """Test get_progress when all challenges completed."""
        mock_exam.challenges.count.return_value = 3
        mock_challenge_results.filter.return_value.count.return_value = 3
        
        exam_attempt = ExamAttempt()
        
        progress = exam_attempt.get_progress()
        
        expected = {
            "total_challenges": 3,
            "completed_challenges": 3,
            "progress_percentage": 100.0,
            "is_complete": True,
        }
        assert progress == expected

    @patch.object(ExamAttempt, 'exam')
    @patch.object(ExamAttempt, 'challenge_results')
    def test_get_progress_partial(self, mock_challenge_results, mock_exam):
        """Test get_progress with partial completion."""
        mock_exam.challenges.count.return_value = 5
        mock_challenge_results.filter.return_value.count.return_value = 2
        
        exam_attempt = ExamAttempt()
        
        progress = exam_attempt.get_progress()
        
        expected = {
            "total_challenges": 5,
            "completed_challenges": 2,
            "progress_percentage": 40.0,
            "is_complete": False,
        }
        assert progress == expected

    @patch.object(ExamAttempt, 'exam')
    @patch.object(ExamAttempt, 'challenge_results')
    def test_get_progress_no_challenges(self, mock_challenge_results, mock_exam):
        """Test get_progress with no challenges."""
        mock_exam.challenges.count.return_value = 0
        mock_challenge_results.filter.return_value.count.return_value = 0
        
        exam_attempt = ExamAttempt()
        
        progress = exam_attempt.get_progress()
        
        expected = {
            "total_challenges": 0,
            "completed_challenges": 0,
            "progress_percentage": 0,
            "is_complete": False,
        }
        assert progress == expected

    def test_exam_attempt_repr(self):
        """Test ExamAttempt __repr__ method."""
        mock_exam = Mock()
        mock_exam.name = "Chemistry Exam"
        
        exam_attempt = ExamAttempt(user_id=42, final_grade="A")
        exam_attempt.exam = mock_exam
        
        repr_str = repr(exam_attempt)
        
        assert repr_str == "<ExamAttempt 42 -> Chemistry Exam: A>"


class TestExamChallengeResultModel:
    """Comprehensive tests for ExamChallengeResult model."""

    def test_exam_challenge_result_creation(self):
        """Test basic ExamChallengeResult creation."""
        now = datetime.now()
        result = ExamChallengeResult(
            exam_attempt_id=1,
            exam_challenge_id=2,
            score=85,
            passed=True,
            attempted_at=now,
            notes="Well done"
        )
        
        assert result.exam_attempt_id == 1
        assert result.exam_challenge_id == 2
        assert result.score == 85
        assert result.passed is True
        assert result.attempted_at == now
        assert result.notes == "Well done"

    @patch('models.exam.models.datetime')
    def test_complete_challenge_with_all_params(self, mock_datetime):
        """Test complete_challenge with all parameters."""
        mock_now = datetime(2024, 1, 1, 15, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        result = ExamChallengeResult()
        
        result.complete_challenge(score=95, passed=True, notes="Perfect execution")
        
        assert result.score == 95
        assert result.passed is True
        assert result.attempted_at == mock_now
        assert result.notes == "Perfect execution"

    @patch('models.exam.models.datetime')
    def test_complete_challenge_minimal_params(self, mock_datetime):
        """Test complete_challenge with minimal parameters."""
        mock_now = datetime(2024, 1, 1, 15, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        result = ExamChallengeResult()
        
        result.complete_challenge()
        
        assert result.score is None
        assert result.passed is None
        assert result.attempted_at == mock_now
        assert result.notes is None

    @patch('models.exam.models.datetime')
    def test_complete_challenge_without_notes(self, mock_datetime):
        """Test complete_challenge without notes."""
        mock_now = datetime(2024, 1, 1, 15, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        result = ExamChallengeResult()
        
        result.complete_challenge(score=70, passed=False)
        
        assert result.score == 70
        assert result.passed is False
        assert result.attempted_at == mock_now
        assert result.notes is None

    def test_exam_challenge_result_repr(self):
        """Test ExamChallengeResult __repr__ method."""
        mock_exam_attempt = Mock()
        mock_exam_attempt.user_id = 123
        mock_exam_challenge = Mock()
        mock_exam_challenge.challenge.name = "Quantum Physics"
        
        result = ExamChallengeResult(score=88)
        result.exam_attempt = mock_exam_attempt
        result.exam_challenge = mock_exam_challenge
        
        repr_str = repr(result)
        
        assert repr_str == "<ExamChallengeResult 123 -> Quantum Physics: 88>"