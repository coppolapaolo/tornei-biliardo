"""
Module: models/exam/services.py
Purpose: Exam domain services for business logic
Requirements: SPECIFICHE.md - Exam management and grading
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from sqlalchemy import text

from ..base import db
from .models import Exam, ExamChallenge, ExamAttempt, ExamChallengeResult
from ..transaction.manager import transactional


class ExamService:
    """Service for exam management and business logic."""

    @staticmethod
    @transactional(domain="exam")
    def create_exam(
        name: str,
        director_id: int,
        description: Optional[str] = None,
        grading_criteria: Optional[Dict[str, Any]] = None,
        time_limit_minutes: Optional[int] = None,
    ) -> Exam:
        """Create a new exam with automatic transaction management.

        Creates an exam with default grading criteria if none provided.
        Transaction handled by @transactional decorator.
        """
        # Set default grading criteria if not provided (A=90%, B=80%, C=70%, D=60%, F=0%)
        if grading_criteria is None:
            grading_criteria = {
                "grade_scale": {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}
            }

        exam = Exam(
            name=name,
            director_id=director_id,
            description=description,
            time_limit_minutes=time_limit_minutes,
        )

        # Set grading criteria before adding to session (grading_criteria is NOT NULL)
        exam.set_grading_criteria(grading_criteria)

        db.session.add(exam)
        return exam

    @staticmethod
    @transactional(domain="exam")
    def add_challenge_to_exam(
        exam_id: int,
        challenge_id: int,
        order: Optional[int] = None,
        weight: float = 1.0,
    ) -> ExamChallenge:
        """Add a challenge to an exam with automatic order assignment.

        Auto-assigns order if not provided (next sequential number).
        Transaction handled by @transactional decorator.
        """
        exam = db.session.get(Exam, exam_id)
        if exam is None:
            from flask import abort

            abort(404)

        # Auto-assign order if not provided - finds max existing order and increments by 1
        if order is None:
            max_order = (
                db.session.query(db.func.max(ExamChallenge.order))
                .filter_by(exam_id=exam_id)
                .scalar()
            )
            order = (max_order or 0) + 1

        exam_challenge = ExamChallenge(
            exam_id=exam_id, challenge_id=challenge_id, order=order, weight=weight
        )

        db.session.add(exam_challenge)
        return exam_challenge

    @staticmethod
    @transactional(domain="exam")
    def remove_challenge_from_exam(exam_id: int, challenge_id: int) -> None:
        """Remove a challenge from an exam.

        Uses first_or_404() for automatic 404 handling if challenge not found.
        Transaction handled by @transactional decorator.
        """
        exam_challenge = ExamChallenge.query.filter_by(
            exam_id=exam_id, challenge_id=challenge_id
        ).first_or_404()

        db.session.delete(exam_challenge)

    @staticmethod
    @transactional(domain="exam")
    def reorder_exam_challenges(
        exam_id: int, challenge_orders: List[Dict[str, int]]
    ) -> None:
        """Reorder challenges in an exam with bulk update.

        Updates the order field for multiple challenges in a single transaction.
        Skips challenges that don't exist (graceful handling).
        Transaction handled by @transactional decorator.

        WARNING: Does not handle order swapping properly due to unique constraint.
        May fail if new order values conflict with existing orders during update.
        TODO: Implement proper order swapping with temporary values.

        Args:
            exam_id: ID of the exam
            challenge_orders: List of {"challenge_id": int, "order": int}
        """
        for item in challenge_orders:
            exam_challenge = ExamChallenge.query.filter_by(
                exam_id=exam_id, challenge_id=item["challenge_id"]
            ).first()

            if exam_challenge:
                exam_challenge.order = item["order"]

    @staticmethod
    def get_director_exams(director_id: int) -> List[Exam]:
        """Get all active exams created by a specific director.

        Only returns exams with is_active=True.
        Read-only operation, no transaction needed.
        """
        return Exam.query.filter_by(director_id=director_id, is_active=True).all()

    @staticmethod
    def get_available_exams() -> List[Exam]:
        """Get all active exams available for student enrollment.

        Returns all exams with is_active=True across all directors.
        Read-only operation, no transaction needed.
        """
        return Exam.query.filter_by(is_active=True).all()

    @staticmethod
    @transactional(domain="exam")
    def start_exam_attempt(user_id: int, exam_id: int) -> ExamAttempt:
        """Start a new exam attempt for a user with duplicate prevention.

        Returns existing active attempt if found, otherwise creates new one.
        Automatically initializes challenge results through ExamAttempt.start_exam().
        Transaction handled by @transactional decorator.
        """
        # Prevent duplicate active attempts - return existing if found
        existing_attempt = ExamAttempt.query.filter_by(
            user_id=user_id, exam_id=exam_id, completed=False
        ).first()

        if existing_attempt:
            return existing_attempt

        # Create new attempt and flush to get ID for challenge initialization
        attempt = ExamAttempt(user_id=user_id, exam_id=exam_id)

        db.session.add(attempt)
        db.session.flush()  # Get the ID

        # Initialize ExamChallengeResult records for all challenges in exam
        attempt.start_exam()

        return attempt

    @staticmethod
    @transactional(domain="exam")
    def complete_exam_challenge(
        exam_attempt_id: int,
        exam_challenge_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ExamChallengeResult:
        """Complete a specific challenge within an exam attempt.

        Updates challenge result and auto-completes exam if all challenges done.
        Transaction handled by @transactional decorator.
        """
        result = ExamChallengeResult.query.filter_by(
            exam_attempt_id=exam_attempt_id, exam_challenge_id=exam_challenge_id
        ).first_or_404()

        result.complete_challenge(score=score, passed=passed, notes=notes)

        # Auto-complete exam if all challenges are now complete
        attempt = db.session.get(ExamAttempt, exam_attempt_id)
        if attempt is None:
            from flask import abort

            abort(404)
        progress = attempt.get_progress()

        if progress["is_complete"] and not attempt.completed:
            attempt.complete_exam()

        return result

    @staticmethod
    @transactional(domain="exam")
    def complete_exam_attempt(
        exam_attempt_id: int, notes: Optional[str] = None
    ) -> ExamAttempt:
        """Manually complete an exam attempt by director/admin.

        Allows forced completion even if not all challenges are done.
        Transaction handled by @transactional decorator.
        """
        attempt = db.session.get(ExamAttempt, exam_attempt_id)
        if attempt is None:
            from flask import abort

            abort(404)

        if not attempt.completed:
            attempt.complete_exam(notes=notes)

        return attempt

    @staticmethod
    def get_user_exam_attempts(user_id: int) -> List[ExamAttempt]:
        """Get all exam attempts for a user, ordered by most recent first.

        Read-only operation, no transaction needed.
        """
        return (
            ExamAttempt.query.filter_by(user_id=user_id)
            .order_by(text("started_at DESC"))
            .all()
        )

    @staticmethod
    def get_exam_statistics(exam_id: int) -> Dict[str, Any]:
        """Get detailed statistics for a specific exam.

        Delegates to Exam.get_statistics() for calculation logic.
        Read-only operation, no transaction needed.
        """
        exam = db.session.get(Exam, exam_id)
        if exam is None:
            from flask import abort

            abort(404)
        return exam.get_statistics()

    @staticmethod
    def get_director_statistics(director_id: int) -> Dict[str, Any]:
        """Get aggregated statistics across all exams created by a director.

        Calculates total exams, attempts, grade distribution, and per-exam stats.
        Read-only operation, no transaction needed.
        """
        exams = ExamService.get_director_exams(director_id)

        total_exams = len(exams)
        total_attempts = sum(
            exam.attempts.filter_by(completed=True).count() for exam in exams
        )

        # Collect all final grades from completed attempts across director's exams
        all_grades = []
        for exam in exams:
            for attempt in exam.attempts.filter_by(completed=True):
                if attempt.final_grade:
                    all_grades.append(attempt.final_grade)

        grade_distribution = {}
        for grade in set(all_grades):
            grade_distribution[grade] = all_grades.count(grade)

        return {
            "total_exams": total_exams,
            "total_attempts": total_attempts,
            "grade_distribution": grade_distribution,
            "exams": [{"exam": exam, "stats": exam.get_statistics()} for exam in exams],
        }

    @staticmethod
    @transactional(domain="exam")
    def update_exam(
        exam_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        grading_criteria: Optional[Dict[str, Any]] = None,
        time_limit_minutes: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Exam:
        """Update exam details with selective field updates.

        Only updates provided fields (None values are ignored).
        Transaction handled by @transactional decorator.
        """
        exam = db.session.get(Exam, exam_id)
        if exam is None:
            from flask import abort

            abort(404)

        if name is not None:
            exam.name = name
        if description is not None:
            exam.description = description
        if grading_criteria is not None:
            exam.set_grading_criteria(grading_criteria)
        if time_limit_minutes is not None:
            exam.time_limit_minutes = time_limit_minutes
        if is_active is not None:
            exam.is_active = is_active

        return exam

    @staticmethod
    @transactional(domain="exam")
    def delete_exam(exam_id: int) -> None:
        """Delete an exam via soft delete (marks as inactive).

        Sets is_active=False instead of hard delete to preserve data integrity.
        Transaction handled by @transactional decorator.
        """
        exam = db.session.get(Exam, exam_id)
        if exam is None:
            from flask import abort

            abort(404)
        exam.is_active = False

    @staticmethod
    def can_user_take_exam(user_id: int, exam_id: int) -> bool:
        """Check if a user can take an exam.

        Currently allows unlimited retakes. Future enhancement could add
        time restrictions or attempt limits based on exam configuration.
        Read-only operation, no transaction needed.
        """
        # TODO: Implement configurable retake policies (time restrictions, attempt limits)
        # For now, allow unlimited retakes for maximum flexibility
        return True
