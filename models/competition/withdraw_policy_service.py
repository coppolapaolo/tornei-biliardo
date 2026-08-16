"""
WithdrawPolicyService - Handles forfait and withdrawal policies for competitions.

This service centralizes the logic for handling player forfeits based on
the competition's withdraw_policy setting.
"""

from models.base import db, utc_now
from models.transaction.manager import transactional
from .models import Gara, Inscription, WithdrawPolicy
from .inscription_service import InscriptionService


class WithdrawPolicyService:
    """Service for handling forfait and withdrawal policies."""

    @staticmethod
    @transactional(domain="competition")
    def handle_forfeit(gara_id: int, user_id: int) -> str:
        """
        Handle player forfeit according to gara's withdraw policy.

        When a player forfeits, ALL their remaining pending/playing matches
        in this gara are also completed with the opponent as winner.

        Args:
            gara_id: ID of the gara
            user_id: ID of player who forfeited

        Returns:
            Policy action taken ("forfeit_marked" or "excluded")

        Raises:
            ValueError: If gara not found or user not inscribed
        """
        from sqlalchemy import or_
        from models.match.models import Match
        from models.status_enum import MatchStatus

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id, is_withdrawn=False)
            .first()
        )
        if not inscription:
            raise ValueError(
                f"User {user_id} not inscribed or already withdrawn from gara {gara_id}"
            )

        # Complete ALL pending/playing matches for this player in this gara
        # (The match that triggered the forfeit is already completed)
        from models.match.models import TrioMatch

        # Query 1: Regular matches (player is player1 or player2)
        pending_regular_matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                or_(Match.player1_id == user_id, Match.player2_id == user_id),
                Match.is_bye == False,  # noqa: E712  Skip bye matches
                Match.is_trio == False,  # noqa: E712  Skip trio matches
            )
            .all()
        )

        # Query 2: Trio matches where player is player3 (not in Match table)
        # These won't be found by Query 1
        pending_trio_matches_as_player3 = (
            db.session.query(Match)
            .join(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                Match.is_trio == True,  # noqa: E712
                TrioMatch.player3_id == user_id,
            )
            .all()
        )

        # Query 3: Trio matches where player is player1 or player2
        # (found by player1_id/player2_id but need special handling)
        pending_trio_matches_as_player12 = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.status.in_(
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                Match.is_trio == True,  # noqa: E712
                or_(Match.player1_id == user_id, Match.player2_id == user_id),
            )
            .all()
        )

        # Handle regular matches
        for match in pending_regular_matches:
            # Determine winner (the opponent)
            # Use match_distance if set, otherwise fall back to gara.distance
            winning_score = match.match_distance or gara.distance
            if match.player1_id == user_id:
                winner_id = match.player2_id
                match.player1_score = 0
                match.player2_score = winning_score
            else:
                winner_id = match.player1_id
                match.player1_score = winning_score
                match.player2_score = 0

            match.winner_id = winner_id
            match.status = MatchStatus.COMPLETED.value

        # Handle trio matches (all of them - player3, player1, or player2)
        # Combine unique trio matches from both queries
        all_trio_matches = set(
            pending_trio_matches_as_player3 + pending_trio_matches_as_player12
        )
        for match in all_trio_matches:
            trio = match.trio_match
            if trio and not trio.is_completed:
                # Use TrioMatch's forfeit handler for proper round-robin completion
                trio.handle_forfeit(user_id)

        if gara.withdraw_policy == WithdrawPolicy.FORFEIT.value:
            # Policy FORFEIT: Mark as forfeit but keep in inscriptions
            inscription.is_forfeit = True
            inscription.forfeit_at = utc_now()
            return "forfeit_marked"

        elif gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            # Policy EXCLUDE: Remove from inscriptions completely
            InscriptionService.uninscribe_user(user_id=user_id, gara_id=gara_id)
            return "excluded"

        else:
            raise ValueError(f"Unknown withdraw policy: {gara.withdraw_policy}")

    @staticmethod
    def get_active_inscriptions(gara_id: int) -> list[Inscription]:
        """
        Get active inscriptions (not withdrawn, not waitlist).

        Includes forfeit players as they still participate in matchmaking.
        """
        return Inscription.active_for_gara(gara_id)

    @staticmethod
    def get_forfeit_inscriptions(gara_id: int) -> list[Inscription]:
        """
        Get inscriptions marked as forfeit (for auto-completion logic).

        Excludes waitlist entries: a waitlisted player cannot have matches to
        forfeit, and promotion to active must clear `is_forfeit` — filtering
        here is defense-in-depth so a promoted-but-still-forfeit inscription
        never reaches matchmaking as a forfeit target.
        """
        return (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id, is_withdrawn=False, is_waitlist=False, is_forfeit=True
            )
            .all()
        )

    @staticmethod
    def get_forfeit_user_ids(gara_id: int) -> set[int]:
        """
        Return forfeit player user_ids as a set — canonical source for the
        `forfeit_user_ids` parameter consumed by `create_matches_from_pairings`.
        """
        return {
            ins.user_id
            for ins in WithdrawPolicyService.get_forfeit_inscriptions(gara_id)
        }

    @staticmethod
    def is_player_forfeit(gara_id: int, user_id: int) -> bool:
        """
        Check if a specific player is marked as forfeit in this gara.
        """
        inscription = (
            db.session.query(Inscription)
            .filter_by(
                user_id=user_id, gara_id=gara_id, is_withdrawn=False, is_forfeit=True
            )
            .first()
        )
        return inscription is not None
