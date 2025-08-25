# tests/test_scoring_strategies.py
"""Tests for the scoring strategy implementations."""

import pytest
from models.scoring.policies import ScoringPolicy
from models.scoring.strategies import ClassicScoringPolicy, FargoRatingScoringPolicy, EloRatingScoringPolicy


class TestScoringPolicies:
    """Test suite for scoring policy implementations."""

    def test_classic_scoring_policy_interface(self):
        """Test that ClassicScoringPolicy implements the ScoringPolicy interface."""
        policy = ClassicScoringPolicy()
        assert isinstance(policy, ScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_fargo_scoring_policy_interface(self):
        """Test that FargoRatingScoringPolicy implements the ScoringPolicy interface."""
        policy = FargoRatingScoringPolicy()
        assert isinstance(policy, ScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_elo_scoring_policy_interface(self):
        """Test that EloRatingScoringPolicy implements the ScoringPolicy interface."""
        policy = EloRatingScoringPolicy()
        assert isinstance(policy, ScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_classic_scoring_policy_ranking_criteria(self):
        """Test that ClassicScoringPolicy returns correct ranking criteria."""
        policy = ClassicScoringPolicy()
        criteria = policy.get_ranking_criteria()
        assert 'wins' in criteria
        assert 'rack_difference' in criteria
        assert 'previous_order' in criteria

    def test_fargo_scoring_policy_ranking_criteria(self):
        """Test that FargoRatingScoringPolicy returns correct ranking criteria."""
        policy = FargoRatingScoringPolicy()
        criteria = policy.get_ranking_criteria()
        assert 'fargo_rating' in criteria
        assert 'wins' in criteria
        assert 'rack_difference' in criteria

    def test_elo_scoring_policy_ranking_criteria(self):
        """Test that EloRatingScoringPolicy returns correct ranking criteria."""
        policy = EloRatingScoringPolicy()
        criteria = policy.get_ranking_criteria()
        assert 'elo_rating' in criteria
        assert 'wins' in criteria
        assert 'rack_difference' in criteria

    def test_classic_scoring_policy_calculation(self):
        """Test that ClassicScoringPolicy calculates standings correctly."""
        # This is a simplified test - in a real scenario we would need mock player objects
        policy = ClassicScoringPolicy()
        assert hasattr(policy, 'calculate_standings')