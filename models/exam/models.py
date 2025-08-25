"""
Module: models/exam/models.py
Purpose: Exam domain models for director-created examinations
Requirements: SPECIFICHE.md - Exam system with multiple challenges and grading
Data Structures: Exam, ExamChallenge, ExamAttempt
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy.orm import backref
from sqlalchemy import func

from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    from ..user.models import User
    from ..challenge.models import Challenge


class Exam(BaseModel, TimestampMixin):
    """An exam consisting of multiple challenges with grading criteria."""
    
    __tablename__ = "exam"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Exam configuration
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    grading_criteria = db.Column(db.Text, nullable=False)  # JSON string
    
    # Metadata
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    time_limit_minutes = db.Column(db.Integer, nullable=True)  # Optional time limit
    
    # Relationships
    challenges = db.relationship(
        "ExamChallenge", 
        back_populates="exam", 
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ExamChallenge.order"
    )
    
    attempts = db.relationship(
        "ExamAttempt", 
        back_populates="exam", 
        lazy="dynamic",
        cascade="all, delete-orphan"
    )
    
    director = db.relationship("User", foreign_keys=[director_id])
    
    def get_grading_criteria(self) -> Dict[str, Any]:
        """Parse grading criteria from JSON."""
        try:
            return json.loads(self.grading_criteria)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_grading_criteria(self, criteria: Dict[str, Any]) -> None:
        """Set grading criteria as JSON."""
        self.grading_criteria = json.dumps(criteria)
    
    def calculate_grade(self, total_score: int, max_possible_score: int) -> str:
        """Calculate letter grade based on score and grading criteria."""
        if max_possible_score == 0:
            return "F"
        
        percentage = (total_score / max_possible_score) * 100
        criteria = self.get_grading_criteria()
        
        # Default grading scale if not configured
        default_scale = {
            "A": 90,
            "B": 80,
            "C": 70,
            "D": 60,
            "F": 0
        }
        
        scale = criteria.get("grade_scale", default_scale)
        
        # Sort grades by threshold (descending)
        sorted_grades = sorted(scale.items(), key=lambda x: x[1], reverse=True)
        
        for grade, threshold in sorted_grades:
            if percentage >= threshold:
                return grade
        
        return "F"
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get exam statistics for director/admin view."""
        attempts_query = self.attempts.filter_by(completed=True)
        
        total_attempts = attempts_query.count()
        unique_students = attempts_query.with_entities(ExamAttempt.user_id).distinct().count()
        
        if total_attempts == 0:
            return {
                "total_attempts": 0,
                "unique_students": 0,
                "average_grade": "N/A",
                "grade_distribution": {},
                "completion_rate": 0
            }
        
        # Calculate grade distribution
        grades = [attempt.final_grade for attempt in attempts_query.all()]
        grade_distribution = {}
        for grade in set(grades):
            grade_distribution[grade] = grades.count(grade)
        
        # Calculate average (convert grades to numeric for averaging)
        grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        numeric_grades = [grade_values.get(grade, 0) for grade in grades]
        avg_numeric = sum(numeric_grades) / len(numeric_grades)
        
        # Convert back to letter grade
        avg_grade = "F"
        for letter, value in sorted(grade_values.items(), key=lambda x: x[1], reverse=True):
            if avg_numeric >= value:
                avg_grade = letter
                break
        
        # Completion rate (started vs completed)
        total_started = self.attempts.count()
        completion_rate = (total_attempts / total_started * 100) if total_started > 0 else 0
        
        return {
            "total_attempts": total_attempts,
            "unique_students": unique_students,
            "average_grade": avg_grade,
            "grade_distribution": grade_distribution,
            "completion_rate": round(completion_rate, 1)
        }
    
    def get_max_possible_score(self) -> int:
        """Calculate maximum possible score for this exam."""
        total = 0
        for exam_challenge in self.challenges.all():
            total += exam_challenge.challenge.max_score
        return total
    
    def __repr__(self) -> str:
        return f"<Exam {self.name}>"


class ExamChallenge(BaseModel):
    """Association between an exam and its challenges with ordering."""
    
    __tablename__ = "exam_challenge"
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id", ondelete="CASCADE"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False)
    order = db.Column(db.Integer, nullable=False)  # Order within the exam
    
    # Optional: different weight/multiplier for this challenge in this exam
    weight = db.Column(db.Float, nullable=False, default=1.0)
    
    # Relationships
    exam = db.relationship("Exam", back_populates="challenges")
    challenge = db.relationship("Challenge")
    
    # Unique constraint: challenge can only appear once in an exam
    __table_args__ = (
        db.UniqueConstraint('exam_id', 'challenge_id', name='uq_exam_challenge'),
        db.UniqueConstraint('exam_id', 'order', name='uq_exam_order'),
    )
    
    def get_weighted_max_score(self) -> int:
        """Get maximum score for this challenge with weight applied."""
        return int(self.challenge.max_score * self.weight)
    
    def __repr__(self) -> str:
        return f"<ExamChallenge {self.exam.name} -> {self.challenge.name} ({self.order})>"


class ExamAttempt(BaseModel, TimestampMixin):
    """A student's attempt at an exam."""
    
    __tablename__ = "exam_attempt"
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    
    # Attempt details
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    
    # Results
    total_score = db.Column(db.Integer, nullable=True)
    max_possible_score = db.Column(db.Integer, nullable=True)
    final_grade = db.Column(db.String(2), nullable=True)  # A, B, C, D, F
    
    # Optional: notes from director
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    exam = db.relationship("Exam", back_populates="attempts")
    user = db.relationship("User")
    
    # Individual challenge results within this exam attempt
    challenge_results = db.relationship(
        "ExamChallengeResult",
        back_populates="exam_attempt",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )
    
    def start_exam(self) -> None:
        """Initialize exam attempt with challenge placeholders."""
        self.started_at = datetime.utcnow()
        
        # Create placeholder results for each challenge in the exam
        for exam_challenge in self.exam.challenges.all():
            result = ExamChallengeResult(
                exam_attempt_id=self.id,
                exam_challenge_id=exam_challenge.id
            )
            db.session.add(result)
    
    def complete_exam(self, notes: Optional[str] = None) -> None:
        """Mark exam as completed and calculate final grade."""
        self.completed = True
        self.completed_at = datetime.utcnow()
        
        if notes:
            self.notes = notes
        
        # Calculate total score
        total = 0
        max_total = 0
        
        for result in self.challenge_results.all():
            if result.score is not None:
                total += int(result.score * result.exam_challenge.weight)
            max_total += result.exam_challenge.get_weighted_max_score()
        
        self.total_score = total
        self.max_possible_score = max_total
        self.final_grade = self.exam.calculate_grade(total, max_total)
    
    def get_progress(self) -> Dict[str, Any]:
        """Get exam progress information."""
        total_challenges = self.exam.challenges.count()
        completed_challenges = self.challenge_results.filter(
            ExamChallengeResult.score != None
        ).count()
        
        return {
            "total_challenges": total_challenges,
            "completed_challenges": completed_challenges,
            "progress_percentage": (completed_challenges / total_challenges * 100) if total_challenges > 0 else 0,
            "is_complete": completed_challenges == total_challenges
        }
    
    def __repr__(self) -> str:
        return f"<ExamAttempt {self.user_id} -> {self.exam.name}: {self.final_grade}>"


class ExamChallengeResult(BaseModel, TimestampMixin):
    """Result of a specific challenge within an exam attempt."""
    
    __tablename__ = "exam_challenge_result"
    
    id = db.Column(db.Integer, primary_key=True)
    exam_attempt_id = db.Column(db.Integer, db.ForeignKey("exam_attempt.id", ondelete="CASCADE"), nullable=False)
    exam_challenge_id = db.Column(db.Integer, db.ForeignKey("exam_challenge.id", ondelete="CASCADE"), nullable=False)
    
    # Result details
    score = db.Column(db.Integer, nullable=True)
    passed = db.Column(db.Boolean, nullable=True)
    attempted_at = db.Column(db.DateTime, nullable=True)
    
    # Optional: specific notes for this challenge result
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    exam_attempt = db.relationship("ExamAttempt", back_populates="challenge_results")
    exam_challenge = db.relationship("ExamChallenge")
    
    def complete_challenge(self, score: Optional[int] = None, passed: Optional[bool] = None, notes: Optional[str] = None) -> None:
        """Complete this challenge within the exam."""
        self.score = score
        self.passed = passed
        self.attempted_at = datetime.utcnow()
        if notes:
            self.notes = notes
    
    def __repr__(self) -> str:
        return f"<ExamChallengeResult {self.exam_attempt.user_id} -> {self.exam_challenge.challenge.name}: {self.score}>"