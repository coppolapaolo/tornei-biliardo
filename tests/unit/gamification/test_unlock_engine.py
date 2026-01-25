"""
Tests for Gamification Unlock Engine (ABAC)
"""
import pytest
import json
from unittest.mock import MagicMock, patch

from models.gamification.unlock_engine import UnlockEngine
from models.gamification.feature_models import FeatureConfig
from models.user.models import User
from models.gamification.models import UserLevel

@pytest.fixture
def mock_db_session(mocker):
    return mocker.patch("models.base.db.session")

@pytest.fixture
def mock_user_metrics(mocker):
    return mocker.patch("models.kpi.user_metrics.UserMetricService.get_metric")

def test_check_eligibility_no_config(mock_db_session):
    """Test feature is open if no config exists."""
    mock_db_session.get.return_value = None
    assert UnlockEngine.check_eligibility(1, "unknown_feature") is True

def test_check_eligibility_disabled(mock_db_session):
    """Test feature is locked if disabled."""
    config = FeatureConfig(code="test", is_active=False)
    mock_db_session.get.side_effect = [config]
    assert UnlockEngine.check_eligibility(1, "test") is False

def test_rule_level_requirement(mock_db_session):
    """Test simple level requirement."""
    rules = [
        {
            "conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]
        }
    ]
    config = FeatureConfig(code="level_feat", is_active=True, rules=json.dumps(rules))
    
    user = MagicMock(spec=User)
    user.id = 1
    
    # Mock DB returns config then user then user_level
    user_level = UserLevel(user_id=1, current_level=5)
    mock_db_session.get.side_effect = [config, user, user_level]
    
    assert UnlockEngine.check_eligibility(1, "level_feat") is True

def test_rule_level_fail(mock_db_session):
    """Test simple level fail."""
    rules = [
        {
            "conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]
        }
    ]
    config = FeatureConfig(code="level_feat", is_active=True, rules=json.dumps(rules))
    
    user = MagicMock(spec=User)
    user.id = 1
    
    user_level = UserLevel(user_id=1, current_level=3) # Level 3 < 5
    mock_db_session.get.side_effect = [config, user, user_level]
    
    assert UnlockEngine.check_eligibility(1, "level_feat") is False

def test_or_logic(mock_db_session, mock_user_metrics):
    """Test OR logic (multiple rule sets)."""
    # Rule: Level >= 5 OR Matches >= 10
    rules = [
        {"conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]},
        {"conditions": [{"type": "METRIC", "metric": "total_matches", "operator": "gte", "value": 10}]}
    ]
    config = FeatureConfig(code="or_feat", is_active=True, rules=json.dumps(rules))
    
    user = MagicMock(spec=User)
    user.id = 1
    
    # Case 1: Low Level (3), Low Matches (5) -> Fail
    user_level = UserLevel(user_id=1, current_level=3)
    mock_db_session.get.side_effect = [config, user, user_level, config, user, user_level] # For multiple calls
    mock_user_metrics.return_value = 5
    
    assert UnlockEngine.check_eligibility(1, "or_feat") is False
    
    # Reset mocks for Case 2
    
    # Case 2: Low Level (3), High Matches (15) -> Pass
    mock_db_session.get.side_effect = [config, user, user_level]
    mock_user_metrics.return_value = 15
    
    assert UnlockEngine.check_eligibility(1, "or_feat") is True

def test_and_logic(mock_db_session, mock_user_metrics):
    """Test AND logic (multiple conditions in set)."""
    # Rule: Level >= 3 AND Matches >= 5
    rules = [
        {
            "conditions": [
                {"type": "LEVEL", "operator": "gte", "value": 3},
                {"type": "METRIC", "metric": "total_matches", "operator": "gte", "value": 5}
            ]
        }
    ]
    config = FeatureConfig(code="and_feat", is_active=True, rules=json.dumps(rules))
    
    user = MagicMock(spec=User)
    user.id = 1
    
    user_level = UserLevel(user_id=1, current_level=3) # Level OK
    mock_db_session.get.side_effect = [config, user, user_level]
    mock_user_metrics.return_value = 2 # Matches Fail
    
    assert UnlockEngine.check_eligibility(1, "and_feat") is False
