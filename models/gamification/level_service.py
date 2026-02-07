"""
Level Service - XP Award and Level Progression Logic

Core service for the gamification system handling:
- XP award with automatic level up detection
- Level progression calculation
- Feature unlock eligibility checking
- UI display data generation

All methods use @transactional decorator for automatic commit/rollback.
"""

from __future__ import annotations
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
import json
import logging

from models.base import db
from models.transaction.manager import transactional
from models.gamification.models import (
    UserLevel,
    XPTransaction,
    XPTransactionType,
)
from models.gamification.config_service import GamificationConfigService as ConfigService
from models.gamification.events import XPGainedEvent, LevelUpEvent
from models.events.base import EventBus

logger = logging.getLogger(__name__)


class LevelService:
    """
    Service for XP award and level progression management.
    
    Primary Methods:
    - award_xp(): Award XP with automatic level up detection
    - get_level_progress(): Get UI display data for level progress
    - check_unlock_eligibility(): Check if feature is unlocked
    """

    @staticmethod
    @transactional(domain="gamification")
    def award_xp(
        user_id: int,
        xp_amount: int,
        transaction_type: XPTransactionType,
        reason: Optional[str] = None,
        related_entities: Optional[Dict[str, Any]] = None
    ) -> Tuple[UserLevel, bool]:
        """
        Award XP to user with automatic level up detection.
        
        Handles:
        - Creating UserLevel if doesn't exist
        - Adding XP to current_xp and total_xp
        - Detecting and processing level ups (including multiple levels)
        - Creating XPTransaction for audit trail
        - Emitting XPGainedEvent and LevelUpEvent(s)
        
        Args:
            user_id: User to award XP to
            xp_amount: Amount of XP to award (can be negative for penalties)
            transaction_type: Type of XP transaction
            reason: Optional reason for audit trail
            related_entities: Optional dict of related entities (e.g., {"match_id": 123})
            
        Returns:
            Tuple of (UserLevel, did_level_up: bool)
            
        Emits:
            - XPGainedEvent: Always emitted after XP award
            - LevelUpEvent: Emitted if level up occurred (with unlocks)
            
        Example:
            user_level, leveled_up = LevelService.award_xp(
                user_id=42,
                xp_amount=50,
                transaction_type=XPTransactionType.MATCH_WIN,
                reason="Won match against Paolo",
                related_entities={"match_id": 123}
            )
            
            if leveled_up:
                print(f"User reached level {user_level.current_level}!")
        """
        # Skip gamification for admin users
        from models.user.models import User
        user = db.session.get(User, user_id)
        if user and user.is_admin:
            logger.debug(f"Skipping XP award for admin user {user_id}")
            return None, False  # type: ignore

        # Get or create UserLevel
        user_level = db.session.get(UserLevel, user_id)
        if user_level is None:
            user_level = UserLevel(user_id=user_id)
            db.session.add(user_level)
            db.session.flush()  # Get ID for transaction
        
        # Store old level for event and transaction
        old_level = user_level.current_level
        
        # Add XP
        user_level.current_xp += xp_amount
        user_level.total_xp += xp_amount
        
        # Check for level up(s)
        did_level_up = False
        unlocks: List[Dict[str, str]] = []
        
        # Get level unlocks dict for checking
        level_unlocks = ConfigService.get_all_level_unlocks_dict()

        while True:
            xp_needed = ConfigService.get_xp_for_next_level(user_level.current_level)

            if user_level.current_xp >= xp_needed:
                # Level up!
                user_level.current_level += 1
                user_level.current_xp -= xp_needed
                did_level_up = True

                # Update highest level if surpassed
                if user_level.current_level > user_level.highest_level_reached:
                    user_level.highest_level_reached = user_level.current_level

                # Check for unlocks at this level
                if user_level.current_level in level_unlocks:
                    unlocks.append(level_unlocks[user_level.current_level])

                logger.info(
                    f"User {user_id} leveled up to {user_level.current_level} "
                    f"(total XP: {user_level.total_xp})"
                )
            else:
                # No more level ups
                break
        
        new_level = user_level.current_level
        
        # Create XPTransaction for audit trail
        transaction = XPTransaction(
            user_id=user_id,
            transaction_type=transaction_type,
            xp_amount=xp_amount,
            reason=reason,
            level_before=old_level,
            level_after=new_level,
            related_entities=json.dumps(related_entities) if related_entities else None
        )
        db.session.add(transaction)
        
        # Emit XPGainedEvent
        EventBus.publish(XPGainedEvent(
            user_id=user_id,
            xp_amount=xp_amount,
            transaction_type=transaction_type,
            new_total_xp=user_level.total_xp,
            level_before=old_level,
            level_after=new_level,
            related_entities=related_entities
        ))
        
        # Emit LevelUpEvent if leveled up
        if did_level_up:
            EventBus.publish(LevelUpEvent(
                user_id=user_id,
                old_level=old_level,
                new_level=new_level,
                unlocks=unlocks,
                total_xp=user_level.total_xp
            ))
        
        logger.debug(
            f"Awarded {xp_amount} XP to user {user_id} "
            f"(type: {transaction_type.value}, new total: {user_level.total_xp})"
        )
        
        return user_level, did_level_up

    @staticmethod
    @transactional(domain="gamification")
    def reset_user_level(user_id: int) -> UserLevel:
        """Reset user level to 1, XP to 0. Keeps total_xp for historical record.

        Raises:
            ValueError: If user has no level data.
        """
        user_level = UserLevel.query.filter_by(user_id=user_id).first()
        if not user_level:
            raise ValueError("Utente non ha dati di livello")
        user_level.current_level = 1
        user_level.current_xp = 0
        logger.info(f"Reset user {user_id} level to 1")
        return user_level

    @staticmethod
    def get_level_progress(user_id: int) -> Dict[str, Any]:
        """
        Get UI display data for level progress.
        
        Returns all data needed to render level progress UI:
        - Current level and XP
        - XP needed for next level
        - Progress percentage
        - Next unlock information
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with:
            {
                "current_level": int,
                "current_xp": int,
                "total_xp": int,
                "xp_for_next_level": int,
                "progress_percentage": float (0-100),
                "next_unlock": Optional[Dict] with "level", "feature", "description"
            }
            
        Example:
            progress = LevelService.get_level_progress(user_id=42)
            # {
            #     "current_level": 8,
            #     "current_xp": 450,
            #     "total_xp": 3500,
            #     "xp_for_next_level": 600,
            #     "progress_percentage": 75.0,
            #     "next_unlock": {
            #         "level": 10,
            #         "feature": "tournament_creation",
            #         "description": "Puoi creare tornei standalone"
            #     }
            # }
        """
        user_level = db.session.get(UserLevel, user_id)

        if user_level is None:
            # User has no XP yet - return defaults
            return {
                "current_level": 1,
                "current_xp": 0,
                "total_xp": 0,
                "xp_for_next_level": ConfigService.get_xp_for_next_level(1),
                "progress_percentage": 0.0,
                "next_unlock": ConfigService.get_next_unlock(1)
            }

        xp_for_next = ConfigService.get_xp_for_next_level(user_level.current_level)
        progress_percentage = (user_level.current_xp / xp_for_next * 100) if xp_for_next > 0 else 0.0

        return {
            "current_level": user_level.current_level,
            "current_xp": user_level.current_xp,
            "total_xp": user_level.total_xp,
            "xp_for_next_level": xp_for_next,
            "progress_percentage": round(progress_percentage, 1),
            "next_unlock": ConfigService.get_next_unlock(user_level.current_level)
        }

        """
        Check if user has unlocked a specific feature.
        
        Used for permission checks (e.g., can user create tournaments?).
        
        Args:
            user_id: User ID
            feature: Feature identifier (e.g., "tournament_creation")
            
        Returns:
            True if feature is unlocked, False otherwise
        """
        from models.gamification.unlock_engine import UnlockEngine
        return UnlockEngine.check_eligibility(user_id, feature)

    @staticmethod
    def get_user_level_stats(user_id: int) -> Dict[str, Any]:
        """
        Get comprehensive level statistics for user profile.
        
        Returns detailed stats including:
        - Current level and XP
        - Highest level reached
        - XP from different sources
        - Recent level ups
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with comprehensive stats
        """
        user_level = db.session.get(UserLevel, user_id)
        
        if user_level is None:
            return {
                "current_level": 1,
                "total_xp": 0,
                "highest_level_reached": 1,
                "xp_by_type": {},
                "recent_transactions": []
            }
        
        # Calculate XP by transaction type
        xp_by_type_query = db.session.query(
            XPTransaction.transaction_type,
            db.func.sum(XPTransaction.xp_amount).label("total_xp")
        ).filter(
            XPTransaction.user_id == user_id
        ).group_by(
            XPTransaction.transaction_type
        ).all()
        
        xp_by_type = {
            txn_type.value: int(total_xp)
            for txn_type, total_xp in xp_by_type_query
        }
        
        # Get recent transactions (last 10)
        recent_transactions = XPTransaction.query.filter_by(
            user_id=user_id
        ).order_by(
            XPTransaction.created_at.desc()
        ).limit(10).all()
        
        return {
            "current_level": user_level.current_level,
            "total_xp": user_level.total_xp,
            "highest_level_reached": user_level.highest_level_reached,
            "xp_by_type": xp_by_type,
            "recent_transactions": [
                {
                    "type": txn.transaction_type.value,
                    "xp_amount": txn.xp_amount,
                    "reason": txn.reason,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None
                }
                for txn in recent_transactions
            ]
        }
