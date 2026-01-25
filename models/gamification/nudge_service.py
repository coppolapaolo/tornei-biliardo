"""
Nudge Service - Encourage Feature Discovery

Identifies features that a user has unlocked but not yet used, and triggers specific
"Nudge" notifications to encourage exploration.

Strategies:
- Prioritize newly unlocked features.
- Don't spam: One nudge per session or day.
- Stop nudging once used.
"""

from __future__ import annotations
from typing import List, Optional
import logging
from datetime import datetime

from models.base import db
from models.user.models import User
from models.gamification.feature_models import FeatureConfig, UserFeatureUsage
from models.gamification.unlock_engine import UnlockEngine
from models.gamification.frontend_bridge import GamificationFrontendBridge

logger = logging.getLogger(__name__)

class NudgeService:
    
    # Features that are always available (base features) - don't show nudges for these
    EXCLUDED_FROM_NUDGE = {
        "view_global_stats",
        "view_dashboard",
        "view_challenges",
        # Add other base features here
    }
    
    @staticmethod
    def check_login_nudges(user_id: int) -> None:
        """
        Check for pending nudges on user login.
        If a nudge is found, trigger a frontend event.
        """
        # Find all active, potentially restricted features
        features = FeatureConfig.query.filter_by(is_active=True).all()
        
        pending_nudge: Optional[FeatureConfig] = None
        
        for feature in features:
            # Skip base features that shouldn't show nudges
            if feature.code in NudgeService.EXCLUDED_FROM_NUDGE:
                continue
            
            # Check if user has already used it
            usage = UserFeatureUsage.query.filter_by(
                user_id=user_id, feature_code=feature.code
            ).first()
            
            if usage and usage.usage_count > 0:
                continue # Already used, skip
                
            # Check if unlocked
            if UnlockEngine.check_eligibility(user_id, feature.code):
                # Unlocked AND Unused!
                # Prioritize logic could go here (e.g. random or importance)
                pending_nudge = feature
                break
        
        if pending_nudge:
            # Trigger Nudge Event
            GamificationFrontendBridge.handle_nudge_event(user_id, pending_nudge)
            logger.info(f"Triggered nudge for user {user_id} feature {pending_nudge.code}")

    @staticmethod
    def mark_feature_used(user_id: int, feature_code: str) -> None:
        """
        Mark a feature as used, stopping future nudges.
        Call this from the controller when the action is performed.
        """
        usage = UserFeatureUsage.query.filter_by(
            user_id=user_id, feature_code=feature_code
        ).first()
        
        if not usage:
            usage = UserFeatureUsage(user_id=user_id, feature_code=feature_code)
            db.session.add(usage)
        
        usage.usage_count += 1
        usage.last_used_at = datetime.utcnow()
        # db.session.commit() should be handled by caller/request lifecycle
        logger.debug(f"User {user_id} used feature {feature_code}")
