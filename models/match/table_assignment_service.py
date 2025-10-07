"""
Table Assignment Service - Match Domain

Service for managing table assignments to matches in competitions.
Implements automatic table allocation based on venue capacity.

Business Rules:
1. Tables are assigned in order when round starts
2. Matches without tables remain in PENDING state
3. When a match completes, its table can be reassigned to waiting matches
4. Table assignment respects venue's available tables (by name)
5. Only matches from the same round can use freed tables

Author: TDD Implementation - Table Management
Created: 2025-10-07
"""

from __future__ import annotations

from typing import Optional, List

from models.base import db, transactional
from models.match.models import Match
from models.location.models import BilliardHall
from models.status_enum import MatchStatus


class TableAssignmentService:
    """Service for managing table assignments to matches."""

    @staticmethod
    def get_available_tables_count(location: str) -> Optional[int]:
        """Get number of available tables for a venue.

        Args:
            location: Name of the billiard hall

        Returns:
            Number of tables if venue found, None otherwise
        """
        venue = BilliardHall.query.filter_by(name=location).first()
        if not venue:
            return None
        return venue.number_of_tables

    @staticmethod
    def get_table_names(location: str) -> List[str]:
        """Get list of table names for a venue.

        Args:
            location: Name of the billiard hall

        Returns:
            List of table names (custom or default ["1", "2", ...])
        """
        venue = BilliardHall.query.filter_by(name=location).first()
        if not venue:
            return []
        return venue.get_table_names()

    @staticmethod
    @transactional(domain="match")
    def assign_tables_to_round(gara_id: int, round_number: int) -> int:
        """Assign tables to all pending matches in a round.

        Tables are assigned in order (by match ID) to pending matches.
        If there are more matches than tables, remaining matches stay pending.

        Args:
            gara_id: ID of the gara
            round_number: Round number to assign tables to

        Returns:
            Number of matches that received table assignments
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara or not gara.location:
            return 0

        # Get available table names
        table_names = TableAssignmentService.get_table_names(gara.location)
        if not table_names:
            return 0

        # Get pending matches without tables, ordered by ID
        matches = (
            Match.query.filter_by(
                gara_id=gara_id, round_number=round_number, table_assignment=None
            )
            .order_by(Match.id)
            .all()
        )

        # Assign tables in order
        assigned_count = 0
        for i, match in enumerate(matches):
            if i < len(table_names):
                match.table_assignment = table_names[i]
                assigned_count += 1
            else:
                break  # No more tables available

        return assigned_count

    @staticmethod
    def start_match(match_id: int) -> Match:
        """Start a match (change status to PLAYING).

        A match can only start if it has a table assigned.

        Args:
            match_id: ID of the match to start

        Raises:
            ValueError: If match doesn't have table assigned

        Returns:
            The updated match
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        if not match.table_assignment:
            raise ValueError("Cannot start match without table")

        match.status = MatchStatus.PLAYING.value
        return match

    @staticmethod
    @transactional(domain="match")
    def free_table_and_reassign(match_id: int) -> Optional[Match]:
        """Free table from completed match and reassign to next waiting match.

        When a match completes, its table becomes available for the next
        pending match in the SAME round without a table.

        Args:
            match_id: ID of the completed match

        Returns:
            The match that received the freed table, or None if no match waiting
        """
        completed_match = db.session.get(Match, match_id)
        if not completed_match:
            raise ValueError(f"Match {match_id} not found")

        if completed_match.status != MatchStatus.COMPLETED.value:
            raise ValueError("Can only free tables from completed matches")

        if not completed_match.table_assignment:
            return None  # No table to free

        freed_table = completed_match.table_assignment

        # Find next waiting match from SAME round without table
        waiting_match = (
            Match.query.filter_by(
                gara_id=completed_match.gara_id,
                round_number=completed_match.round_number,
                table_assignment=None,
            )
            .order_by(Match.id)
            .first()
        )

        if waiting_match:
            waiting_match.table_assignment = freed_table
            return waiting_match

        return None
