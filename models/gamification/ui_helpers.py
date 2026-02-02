"""
UI Helpers for Gamification.
Provides utilities for templates to check feature access easily.
"""
from typing import Dict, List, Union
from models.gamification.unlock_engine import UnlockEngine
from models.user.models import User

class GamificationUIHelper:
    """Helper for UI-related gamification checks."""

    @staticmethod
    def get_user_features(user: User) -> Dict[str, bool]:
        """
        Get a dictionary of feature flags for the user.
        Useful for passing to templates.
        
        Note: Currently we check specific known features. 
        In a more dynamic system, we might query all active FeatureConfigs.
        """
        # List of features we care about in UI
        features = [
            "match_proposals",
            "tournament_creation",
            "view_ratings" 
        ]
        
        results = {}
        if not user or not user.is_authenticated:
            for f in features:
                results[f] = False
            return results

        for feature_code in features:
            results[feature_code] = UnlockEngine.check_eligibility(user.id, feature_code)
            
        return results

    @staticmethod
    def can_view_ratings(user: User) -> bool:
        """Specific helper for rating visibility."""
        if not user or not user.is_authenticated:
            return False
            
        # Admin always bypass? Or respect gamification? 
        # Typically admins want to see everything, but let's stick to the engine rules 
        # unless engine checks admin role explicitly (which it does via ROLE rule type).
        # However, for simple level checks, admin might be level 1.
        # Let's trust UnlockEngine.
        return UnlockEngine.check_eligibility(user.id, "view_ratings")
