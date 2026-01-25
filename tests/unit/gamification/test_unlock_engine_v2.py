"""
Tests for Gamification Unlock Engine (ABAC) - Standard Unittest Version
"""
import unittest
import json
from unittest.mock import MagicMock, patch

from models.gamification.unlock_engine import UnlockEngine
from models.gamification.feature_models import FeatureConfig
from models.user.models import User
from models.gamification.models import UserLevel

class TestUnlockEngine(unittest.TestCase):
    
    def setUp(self):
        # Patching DB session
        self.patcher_db = patch("models.base.db.session")
        self.mock_db_session = self.patcher_db.start()
        
        # Patching User Metrics
        self.patcher_metrics = patch("models.kpi.user_metrics.UserMetricService.get_metric")
        self.mock_metrics = self.patcher_metrics.start()
        
    def tearDown(self):
        self.patcher_db.stop()
        self.patcher_metrics.stop()

    def test_check_eligibility_no_config(self):
        """Test feature is open if no config exists."""
        self.mock_db_session.get.return_value = None
        self.assertTrue(UnlockEngine.check_eligibility(1, "unknown_feature"))

    def test_check_eligibility_disabled(self):
        """Test feature is locked if disabled."""
        config = FeatureConfig(code="test", is_active=False)
        self.mock_db_session.get.side_effect = lambda model, id: config if model == FeatureConfig else None
        self.assertFalse(UnlockEngine.check_eligibility(1, "test"))

    def test_rule_level_requirement(self):
        """Test simple level requirement."""
        rules = [
            {
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]
            }
        ]
        config = FeatureConfig(code="level_feat", is_active=True, rules=json.dumps(rules))
        user = MagicMock(spec=User)
        user.id = 1
        user_level = UserLevel(user_id=1, current_level=5)
        
        def side_effect(model, id):
            if model == FeatureConfig: return config
            if model == User: return user
            if model == UserLevel: return user_level
            return None
            
        self.mock_db_session.get.side_effect = side_effect
        
        self.assertTrue(UnlockEngine.check_eligibility(1, "level_feat"))

    def test_rule_level_fail(self):
        """Test simple level fail."""
        rules = [{"conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]}]
        config = FeatureConfig(code="level_feat", is_active=True, rules=json.dumps(rules))
        user = MagicMock(spec=User)
        user.id = 1
        user_level = UserLevel(user_id=1, current_level=3)
        
        def side_effect(model, id):
            if model == FeatureConfig: return config
            if model == User: return user
            if model == UserLevel: return user_level
            return None
        self.mock_db_session.get.side_effect = side_effect
        
        self.assertFalse(UnlockEngine.check_eligibility(1, "level_feat"))

    def test_or_logic(self):
        """Test OR logic (multiple rule sets)."""
        rules = [
            {"conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]},
            {"conditions": [{"type": "METRIC", "metric": "total_matches", "operator": "gte", "value": 10}]}
        ]
        config = FeatureConfig(code="or_feat", is_active=True, rules=json.dumps(rules))
        user = MagicMock(spec=User)
        user.id = 1
        user_level = UserLevel(user_id=1, current_level=3) # Level Fail

        def side_effect(model, id):
            if model == FeatureConfig: return config
            if model == User: return user
            if model == UserLevel: return user_level
            return None
        self.mock_db_session.get.side_effect = side_effect
        
        # Case 1: Metrics Fail
        self.mock_metrics.return_value = 5
        self.assertFalse(UnlockEngine.check_eligibility(1, "or_feat"))
        
        # Case 2: Metrics Pass
        self.mock_metrics.return_value = 15
        self.assertTrue(UnlockEngine.check_eligibility(1, "or_feat"))

if __name__ == '__main__':
    unittest.main()
