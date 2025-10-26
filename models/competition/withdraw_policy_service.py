"""
WithdrawPolicyService - Handles forfait and withdrawal policies for competitions.

This service centralizes the logic for handling player forfeits based on
the competition's withdraw_policy setting.
"""

from datetime import datetime
from typing import Optional

from models.base import db
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

        Args:
            gara_id: ID of the gara
            user_id: ID of player who forfeited

        Returns:
            Policy action taken ("forfeit_marked" or "excluded")

        Raises:
            ValueError: If gara not found or user not inscribed
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id, is_withdrawn=False)
            .first()
        )
        if not inscription:
            raise ValueError(f"User {user_id} not inscribed or already withdrawn from gara {gara_id}")

        if gara.withdraw_policy == WithdrawPolicy.FORFEIT.value:
            # Policy FORFEIT: Mark as forfeit but keep in inscriptions
            inscription.is_forfeit = True
            inscription.forfeit_at = datetime.utcnow()
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
        return (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id,
                is_withdrawn=False,
                is_waitlist=False
            )
            .all()
        )

    @staticmethod
    def get_forfeit_inscriptions(gara_id: int) -> list[Inscription]:
        """
        Get inscriptions marked as forfeit (for auto-completion logic).
        """
        return (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id,
                is_withdrawn=False,
                is_forfeit=True
            )
            .all()
        )

    @staticmethod
    def is_player_forfeit(gara_id: int, user_id: int) -> bool:
        """
        Check if a specific player is marked as forfeit in this gara.
        """
        inscription = (
            db.session.query(Inscription)
            .filter_by(
                user_id=user_id,
                gara_id=gara_id,
                is_withdrawn=False,
                is_forfeit=True
            )
            .first()
        )
        return inscription is not None