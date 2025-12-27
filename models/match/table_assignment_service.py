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

from typing import Optional, List, Tuple

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

        DEPRECATED: Use get_table_names_for_gara() instead, which respects
        gara-specific table configuration.

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
    def get_table_names_for_gara(gara_id: int) -> List[str]:
        """Get list of table names for a specific gara.

        Uses gara.get_available_tables() which handles the priority:
        1. gara.available_tables if set
        2. venue.get_table_names() if venue exists
        3. Empty list

        Args:
            gara_id: ID of the gara

        Returns:
            List of table names available for this gara
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []
        return gara.get_available_tables()

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
        from models.match.services import MatchService

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return 0

        # Get available table names (uses gara.available_tables if set,
        # otherwise falls back to venue's tables)
        table_names = gara.get_available_tables()
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
                MatchService.to_playing(match.id)
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
    def release_and_reassign_table(match_id: int) -> Optional[Match]:
        """Release table from completed match and reassign to first waiting match.

        This method:
        1. Removes the table from the completed match
        2. Finds the first pending match in the same round without a table
        3. Assigns the freed table to the waiting match
        4. Transitions the waiting match to PLAYING status

        Args:
            match_id: ID of the completed match

        Returns:
            The match that received the freed table (now PLAYING), or None if no waiting match
        """
        from models.match.services import MatchService

        completed_match = db.session.get(Match, match_id)
        if not completed_match:
            raise ValueError(f"Match {match_id} not found")

        if completed_match.status != MatchStatus.COMPLETED.value:
            raise ValueError("Can only release tables from completed matches")

        if not completed_match.table_assignment:
            return None  # No table to release

        freed_table = completed_match.table_assignment

        # Remove table from completed match
        completed_match.table_assignment = None
        db.session.add(completed_match)

        # Find first pending match in SAME round without table (exclude bye matches)
        waiting_match = (
            Match.query.filter_by(
                gara_id=completed_match.gara_id,
                round_number=completed_match.round_number,
                table_assignment=None,
                status=MatchStatus.PENDING.value,
            )
            .filter(Match.is_bye == False)  # noqa: E712
            .order_by(Match.id)
            .first()
        )

        if waiting_match:
            # Assign freed table to waiting match and set to PLAYING
            waiting_match.table_assignment = freed_table
            waiting_match.status = MatchStatus.PLAYING.value
            db.session.add(waiting_match)

            return waiting_match

        return None

    @staticmethod
    @transactional(domain="match")
    def reassign_table(
        match_id: int, new_table: Optional[str]
    ) -> Tuple[bool, str, Optional[int]]:
        """Reassign a match to a different table with automatic swap if needed.

        Business Rules:
        - Validates round locking before allowing reassignment
        - If new_table is occupied by another match in same round → other match table is removed
        - If new_table is free → simple assignment
        - If new_table is None → removes table assignment
        - Cross-round table sharing is allowed (same table, different rounds)

        Args:
            match_id: ID of the match to reassign
            new_table: New table name, or None to remove assignment

        Returns:
            Tuple[bool, str, Optional[int]]: (success, message, removed_match_id)
            - success: True if operation succeeded
            - message: Human-readable result message
            - removed_match_id: ID of match whose table is removed, or None
        """
        from models.competition.round_manager import AdvancedRoundManager
        from models.match.services import MatchService

        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato", None

        # Validate modification permission (respects round locking)
        can_modify, reason = AdvancedRoundManager.can_modify_match(match_id)
        if not can_modify:
            return False, reason, None

        old_table = match.table_assignment

        # Case 1: Remove table assignment
        if new_table is None:
            match.table_assignment = None
            MatchService.reset_to_pending(match.id)
            db.session.add(match)
            return True, f"Tavolo '{old_table}' rimosso dal match", None

        # Case 2: No change
        if old_table == new_table:
            return True, "Nessuna modifica necessaria", None

        # Case 3: Check if new_table is occupied in SAME round
        occupying_match = (
            Match.query.filter_by(
                gara_id=match.gara_id,
                round_number=match.round_number,
                table_assignment=new_table,
            )
            .filter(Match.id != match_id)
            .first()
        )

        if occupying_match:
            # Automatic swap/eviction with occupying match
            swapped = False
            if old_table:
                occupying_match.table_assignment = old_table
                # Ensure occupying match status is correct if it now has a table
                if (occupying_match.status or MatchStatus.PENDING.value) != MatchStatus.PLAYING.value:
                    try:
                        MatchService.to_playing(occupying_match.id)
                    except Exception:
                        pass
                swapped = True
            else:
                occupying_match.table_assignment = None
                MatchService.reset_to_pending(occupying_match.id)

            match.table_assignment = new_table
            if (match.status or MatchStatus.PENDING.value) != MatchStatus.PLAYING.value:
                try:
                    MatchService.to_playing(match.id)
                except Exception:
                    pass

            db.session.add(occupying_match)
            db.session.add(match)

            if swapped:
                msg = (
                    f"Tavolo scambiato: Match #{match_id} → '{new_table}', "
                    f"Match #{occupying_match.id} → '{old_table}'"
                )
            else:
                msg = (
                    f"Tavolo assegnato: Match #{match_id} → '{new_table}', "
                    f"Match #{occupying_match.id} → senza tavolo"
                )

            return True, msg, occupying_match.id
        else:
            # Simple assignment (table is free in this round)
            match.table_assignment = new_table
            if (match.status or MatchStatus.PENDING.value) != MatchStatus.PLAYING.value:
                try:
                    MatchService.to_playing(match.id)
                except Exception:
                    pass
            db.session.add(match)

            msg = f"Tavolo assegnato: Match #{match_id} → '{new_table}'"
            return True, msg, None
