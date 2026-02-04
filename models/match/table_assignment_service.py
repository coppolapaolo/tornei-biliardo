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
    def _get_free_tables(gara_id: int) -> List[str]:
        """Get list of tables that are currently free (not assigned to PLAYING matches).

        A table is "free" if:
        1. It's in the gara's configured available tables list
        2. It's NOT currently assigned to any PLAYING match in this gara

        Args:
            gara_id: ID of the gara

        Returns:
            List of table names that are currently available for assignment
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []

        all_tables = set(gara.get_available_tables())
        if not all_tables:
            return []

        # Find tables currently assigned to PLAYING matches
        occupied_tables = set(
            row[0]
            for row in db.session.query(Match.table_assignment)
            .filter(
                Match.gara_id == gara_id,
                Match.status == MatchStatus.PLAYING.value,
                Match.table_assignment.isnot(None),
            )
            .all()
        )

        # Return tables that are configured but not occupied
        return list(all_tables - occupied_tables)

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

        # Assign tables only to matches where both players are free
        assigned_count = 0
        table_index = 0

        for match in matches:
            if table_index >= len(table_names):
                break  # No more tables available

            # Skip bye matches - they don't need tables
            if match.is_bye:
                continue

            # Check if both players are free
            player1_busy = TableAssignmentService._is_player_busy(
                gara_id, match.player1_id
            )
            player2_busy = TableAssignmentService._is_player_busy(
                gara_id, match.player2_id
            )

            if not player1_busy and not player2_busy:
                match.table_assignment = table_names[table_index]
                MatchService.to_playing(match.id)
                assigned_count += 1
                table_index += 1

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
    def _is_player_busy(gara_id: int, player_id: int) -> bool:
        """Check if a player is currently busy in another match.

        A player is busy if they have a match with status PLAYING in the gara.
        """
        if not player_id:
            return False

        busy_match = (
            Match.query.filter_by(gara_id=gara_id, status=MatchStatus.PLAYING.value)
            .filter((Match.player1_id == player_id) | (Match.player2_id == player_id))
            .first()
        )
        return busy_match is not None

    @staticmethod
    @transactional(domain="match")
    def assign_available_tables(gara_id: int) -> int:
        """Assign all free tables to eligible pending matches.

        This is the core "pull" strategy method. It:
        1. Gets all tables that are configured but not assigned to PLAYING matches
        2. Gets all PENDING matches (excluding byes), ordered by round + ID
        3. For each pending match where both players are free, assigns a free table

        This method should be called after any match completes to ensure
        freed tables are reassigned, even if they couldn't be assigned immediately
        when they were first freed.

        Args:
            gara_id: ID of the gara

        Returns:
            Number of matches that received table assignments
        """
        from models.match.services import MatchService

        # Get all currently free tables
        free_tables = TableAssignmentService._get_free_tables(gara_id)
        if not free_tables:
            return 0

        # Get pending matches without table (exclude bye matches)
        # Order by round_number, then match.id for consistent assignment
        pending_matches = (
            Match.query.filter_by(
                gara_id=gara_id,
                table_assignment=None,
                status=MatchStatus.PENDING.value,
            )
            .filter(Match.is_bye == False)  # noqa: E712
            .order_by(Match.round_number, Match.id)
            .all()
        )

        assigned_count = 0
        table_index = 0

        for waiting_match in pending_matches:
            if table_index >= len(free_tables):
                break  # No more free tables

            # Check if both players are free
            player1_busy = TableAssignmentService._is_player_busy(
                gara_id, waiting_match.player1_id
            )
            player2_busy = TableAssignmentService._is_player_busy(
                gara_id, waiting_match.player2_id
            )

            if not player1_busy and not player2_busy:
                # Both players are free - assign table
                waiting_match.table_assignment = free_tables[table_index]
                waiting_match.status = MatchStatus.PLAYING.value
                db.session.add(waiting_match)
                assigned_count += 1
                table_index += 1

        return assigned_count

    @staticmethod
    @transactional(domain="match")
    def release_and_reassign_table(match_id: int) -> Optional[Match]:
        """Release table from completed match and reassign free tables to waiting matches.

        This method uses a "pull" strategy:
        1. Removes the table from the completed match
        2. Calls assign_available_tables() to assign ALL free tables to eligible matches

        This ensures that tables "lost" in previous completions (when no eligible
        match existed) are recovered when players become available.

        Business Rule: A match can only receive a table if BOTH players are not
        currently playing in another match. This prevents a player from being
        assigned to two matches simultaneously.

        Args:
            match_id: ID of the completed match

        Returns:
            The first match that received a table (now PLAYING), or None if no eligible match
        """
        completed_match = db.session.get(Match, match_id)
        if not completed_match:
            raise ValueError(f"Match {match_id} not found")

        # Accept both COMPLETED (admin validation) and VALIDATED (bilateral player confirmation)
        if completed_match.status not in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]:
            raise ValueError("Can only release tables from completed matches")

        # Store gara_id before potentially clearing table
        gara_id = completed_match.gara_id

        # Remove table from completed match (if any)
        if completed_match.table_assignment:
            completed_match.table_assignment = None
            db.session.add(completed_match)

        # Use pull strategy: assign ALL available tables to eligible matches
        # This recovers any tables that were "lost" in previous completions
        assigned_count = TableAssignmentService.assign_available_tables(gara_id)

        if assigned_count > 0:
            # Return the first match that was assigned (for backwards compatibility)
            first_assigned = (
                Match.query.filter_by(
                    gara_id=gara_id,
                    status=MatchStatus.PLAYING.value,
                )
                .filter(Match.table_assignment.isnot(None))
                .order_by(Match.round_number, Match.id)
                .first()
            )
            return first_assigned

        return None

    @staticmethod
    @transactional(domain="match")
    def reassign_table(
        match_id: int, new_table: Optional[str]
    ) -> Tuple[bool, str, Optional[int]]:
        """Reassign a match to a different table with automatic swap if needed.

        Business Rules:
        - Validates round locking before allowing reassignment
        - If new_table is occupied by another PLAYING match → other match loses table (eviction)
        - If new_table is free → simple assignment
        - If new_table is None → removes table assignment
        - A table can only host ONE playing match at a time (physical constraint)

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
        from models.match.services import MatchService, RackService

        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato", None

        # Validate modification permission (respects round locking)
        can_modify, reason = AdvancedRoundManager.can_modify_match(match_id)
        if not can_modify:
            return False, reason, None

        old_table = match.table_assignment

        # Check if players are busy in another match (when assigning a table)
        # This only applies when assigning a new table, not when removing
        if new_table is not None and not old_table:
            player1_busy = TableAssignmentService._is_player_busy(
                match.gara_id, match.player1_id
            )
            player2_busy = TableAssignmentService._is_player_busy(
                match.gara_id, match.player2_id
            )
            if player1_busy or player2_busy:
                from models.user.models import User
                if player1_busy:
                    player = db.session.get(User, match.player1_id)
                else:
                    player = db.session.get(User, match.player2_id)
                name = player.username if player else "Un giocatore"
                return False, f"{name} è già impegnato in un'altra partita", None

        # Case 1: Remove table assignment
        if new_table is None:
            match.table_assignment = None
            RackService.reset_match_complete(match.id)
            db.session.add(match)
            return True, f"Tavolo '{old_table}' rimosso dal match", None

        # Case 2: No change
        if old_table == new_table:
            return True, "Nessuna modifica necessaria", None

        # Case 3: Check if new_table is occupied by ANY PLAYING match in same gara
        # (a table can only host one playing match at a time - physical constraint)
        occupying_match = (
            Match.query.filter_by(
                gara_id=match.gara_id,
                table_assignment=new_table,
                status=MatchStatus.PLAYING.value,
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
                RackService.reset_match_complete(occupying_match.id)

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
