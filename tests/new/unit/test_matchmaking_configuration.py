"""Unit tests for matchmaking configuration.

Tests the strategy configuration system including classification compatibility.
"""

import pytest

from models.matchmaking.configuration import (
    MatchmakingStrategy,
    STRATEGY_CONSTRAINTS,
    get_strategies_for_classification_system,
    get_classification_compatibility_map,
)


@pytest.mark.unit
class TestStrategyConstraints:
    """Tests for STRATEGY_CONSTRAINTS structure."""

    def test_all_strategies_have_compatible_classification_systems(self):
        """Every strategy must define compatible_classification_systems.

        Regression: Missing this field caused UndefinedError in wizard template.
        """
        for strategy in MatchmakingStrategy:
            constraints = STRATEGY_CONSTRAINTS.get(strategy)
            assert constraints is not None, f"Missing constraints for {strategy}"
            assert "compatible_classification_systems" in constraints, (
                f"Missing compatible_classification_systems for {strategy}"
            )
            assert isinstance(
                constraints["compatible_classification_systems"], list
            ), f"compatible_classification_systems must be a list for {strategy}"
            assert len(constraints["compatible_classification_systems"]) > 0, (
                f"compatible_classification_systems cannot be empty for {strategy}"
            )

    def test_classification_systems_are_valid_values(self):
        """Classification systems must be WINS, RACK, or POSITION."""
        valid_systems = {"WINS", "RACK", "POSITION"}

        for strategy, constraints in STRATEGY_CONSTRAINTS.items():
            for system in constraints["compatible_classification_systems"]:
                assert system in valid_systems, (
                    f"Invalid classification system '{system}' for {strategy}"
                )


@pytest.mark.unit
class TestGetStrategiesForClassificationSystem:
    """Tests for get_strategies_for_classification_system function."""

    def test_wins_returns_non_elimination_strategies(self):
        """WINS system should return strategies that support match-based ranking."""
        strategies = get_strategies_for_classification_system("WINS")

        assert "amalfi" in strategies
        assert "random" in strategies
        # Elimination strategies don't support WINS
        assert "direct_elimination" not in strategies
        assert "double_knockout" not in strategies

    def test_rack_returns_non_elimination_strategies(self):
        """RACK system should return strategies that support rack-based ranking."""
        strategies = get_strategies_for_classification_system("RACK")

        assert "amalfi" in strategies
        assert "random" in strategies
        # Elimination strategies don't support RACK
        assert "direct_elimination" not in strategies
        assert "double_knockout" not in strategies

    def test_position_returns_elimination_strategies(self):
        """POSITION system should return bracket-based elimination strategies."""
        strategies = get_strategies_for_classification_system("POSITION")

        assert "direct_elimination" in strategies
        assert "double_knockout" in strategies
        # Non-elimination strategies don't support POSITION
        assert "amalfi" not in strategies
        assert "random" not in strategies

    def test_unknown_system_returns_empty_list(self):
        """Unknown classification system should return empty list."""
        strategies = get_strategies_for_classification_system("UNKNOWN")
        assert strategies == []

    def test_returns_strategy_values_not_enums(self):
        """Function should return string values, not enum objects."""
        strategies = get_strategies_for_classification_system("WINS")

        for strategy in strategies:
            assert isinstance(strategy, str)
            assert not isinstance(strategy, MatchmakingStrategy)


@pytest.mark.unit
class TestGetClassificationCompatibilityMap:
    """Tests for get_classification_compatibility_map function."""

    def test_returns_dict_with_all_classification_systems(self):
        """Map should include all classification systems used in constraints."""
        compat_map = get_classification_compatibility_map()

        assert "WINS" in compat_map
        assert "RACK" in compat_map
        assert "POSITION" in compat_map

    def test_map_values_are_lists_of_strings(self):
        """Each value should be a list of strategy string values."""
        compat_map = get_classification_compatibility_map()

        for system, strategies in compat_map.items():
            assert isinstance(strategies, list), f"{system} value is not a list"
            for strategy in strategies:
                assert isinstance(strategy, str), (
                    f"Strategy '{strategy}' for {system} is not a string"
                )

    def test_map_is_inverse_of_constraints(self):
        """Map should be the inverse of STRATEGY_CONSTRAINTS."""
        compat_map = get_classification_compatibility_map()

        # Verify inverse relationship
        for strategy, constraints in STRATEGY_CONSTRAINTS.items():
            for system in constraints["compatible_classification_systems"]:
                assert strategy.value in compat_map.get(system, []), (
                    f"{strategy.value} should be in {system} but isn't"
                )

    def test_map_usable_for_json_serialization(self):
        """Map should be JSON-serializable for template use.

        Regression: Template uses |tojson filter on this data.
        """
        import json

        compat_map = get_classification_compatibility_map()

        # Should not raise
        json_str = json.dumps(compat_map)
        assert isinstance(json_str, str)

        # Should round-trip correctly
        parsed = json.loads(json_str)
        assert parsed == compat_map


@pytest.mark.unit
class TestClassificationStrategyCompatibilityRegression:
    """Regression tests for wizard template rendering.

    Bug: /admin/campionato/wizard returned 500 error with
    'matchmaking_systems' is undefined

    Root cause: Template used variable not passed by route handler.

    Fix: Added compatible_classification_systems to STRATEGY_CONSTRAINTS
    and created get_classification_compatibility_map() to derive inverse
    mapping as single source of truth.
    """

    def test_wins_and_rack_have_same_strategies(self):
        """WINS and RACK should support the same strategies.

        This matches the original hardcoded JS behavior before the fix.
        """
        wins_strategies = set(get_strategies_for_classification_system("WINS"))
        rack_strategies = set(get_strategies_for_classification_system("RACK"))

        assert wins_strategies == rack_strategies

    def test_position_has_different_strategies(self):
        """POSITION should have different strategies than WINS/RACK.

        POSITION is for bracket-based tournaments (elimination).
        """
        wins_strategies = set(get_strategies_for_classification_system("WINS"))
        position_strategies = set(get_strategies_for_classification_system("POSITION"))

        # No overlap between WINS and POSITION
        assert wins_strategies.isdisjoint(position_strategies)

    def test_amalfi_and_random_in_wizard_default_strategies(self):
        """Wizard shows Amalfi and Random - both must be in WINS/RACK.

        The wizard currently only shows Amalfi and Random strategies.
        Both must be compatible with WINS and RACK classification systems.
        """
        wins_strategies = get_strategies_for_classification_system("WINS")
        rack_strategies = get_strategies_for_classification_system("RACK")

        assert "amalfi" in wins_strategies
        assert "random" in wins_strategies
        assert "amalfi" in rack_strategies
        assert "random" in rack_strategies
