"""
Module: models/individual_match/match_lifecycle_service.py
Purpose: Match lifecycle management service (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import Optional

from ..base import db
from ..transaction.manager import transactional
from .models import IndividualMatch, MatchProposal


class MatchLifecycleService:
    """Service for individual match lifecycle management."""

    @staticmethod
    @transactional(domain="individual_match")
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort
            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can start the match")

        match.start_match()
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Confirm match result by a player (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort
            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can confirm the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.confirm_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def reject_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Reject match result - removes last rack (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort
            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can reject the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.reject_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match - legacy method for backward compatibility."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort
            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can complete the match")

        match.complete_match(winner_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Complete an individual match - alias for complete_match."""
        return MatchLifecycleService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort
            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can cancel the match")

        match.cancel_match(reason)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def report_result(
        match_id: int,
        reporter_id: int,
        winner_id: int,
        player1_racks: int,
        player2_racks: int,
    ) -> None:
        """Report final match result."""
        proposal = db.session.get(MatchProposal, match_id)
        if not proposal:
            raise ValueError(f"Match proposal {match_id} not found")

        if proposal.status.value == "pending":
            individual_match = proposal.accept(reporter_id)
        else:
            individual_match = IndividualMatch.query.filter_by(
                proposal_id=match_id
            ).first()
            if not individual_match:
                raise ValueError("No individual match found for this proposal")

        MatchLifecycleService.complete_match(
            match_id=individual_match.id,
            winner_id=winner_id,
            user_id=reporter_id,
        )
