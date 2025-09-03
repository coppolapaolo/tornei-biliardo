"""
Comprehensive tests for matchmaking strategies to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date

from models.matchmaking.strategies.base import BaseStrategy
from models.matchmaking.strategies.direct_elimination import DirectEliminationStrategy
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy
from models.matchmaking.strategies.random_anti_rematch import RandomAntiRematchStrategy
from models.matchmaking.strategies.round_robin import RoundRobinStrategy
from models import User, Campionato, Gara, Inscription


class TestBaseStrategy:
    """Test base strategy functionality."""

    def test_base_strategy_initialization(self):
        """Test base strategy can be initialized."""
        gara = Mock()
        strategy = BaseStrategy(gara)
        assert strategy.gara == gara

    def test_base_strategy_abstract_methods(self):
        """Test abstract methods raise NotImplementedError."""
        gara = Mock()
        strategy = BaseStrategy(gara)

        with pytest.raises(NotImplementedError):
            strategy.create_round_matches(1)

        with pytest.raises(NotImplementedError):
            strategy.validate_round(1)

    def test_get_active_players_basic(self):
        """Test get_active_players method."""
        gara = Mock()
        strategy = BaseStrategy(gara)

        with patch.object(strategy, "_get_inscriptions") as mock_inscriptions:
            mock_inscription = Mock()
            mock_inscription.is_withdrawn = False
            mock_inscription.user = Mock()
            mock_inscriptions.return_value = [mock_inscription]

            result = strategy.get_active_players()

            assert len(result) == 1
            assert result[0] == mock_inscription.user


class TestDirectEliminationStrategy:
    """Test direct elimination strategy."""

    @pytest.fixture
    def sample_gara(self, db_session):
        """Create a sample gara for testing."""
        campionato = Campionato(name="Direct Test", campionato_type="Elimination")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Direct Elimination Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
            current_round=1,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_direct_elimination_initialization(self, sample_gara):
        """Test direct elimination strategy initialization."""
        strategy = DirectEliminationStrategy(sample_gara)
        assert strategy.gara == sample_gara

    def test_create_first_round_even_players(self, sample_gara, db_session):
        """Test first round creation with even number of players."""
        # Create 4 players
        players = []
        for i in range(4):
            user = User(
                username=f"direct_player{i}", email=f"direct{i}@test.com", role="player"
            )
            user.set_password("password")
            db_session.add(user)
            players.append(user)

        # Create inscriptions
        for player in players:
            inscription = Inscription(
                gara_id=sample_gara.id, user_id=player.id, is_withdrawn=False
            )
            db_session.add(inscription)

        db_session.commit()

        strategy = DirectEliminationStrategy(sample_gara)

        with patch.object(strategy, "_create_match") as mock_create:
            mock_create.return_value = Mock()

            result = strategy.create_round_matches(1)

            # Should create 2 matches for 4 players
            assert mock_create.call_count == 2
            assert len(result) == 2

    def test_create_round_matches_subsequent_round(self, sample_gara):
        """Test creating matches for subsequent rounds."""
        strategy = DirectEliminationStrategy(sample_gara)

        with patch.object(strategy, "_get_round_winners") as mock_winners, patch.object(
            strategy, "_create_match"
        ) as mock_create:

            # Mock 2 winners from previous round
            winner1 = Mock()
            winner2 = Mock()
            mock_winners.return_value = [winner1, winner2]
            mock_create.return_value = Mock()

            result = strategy.create_round_matches(2)

            # Should create 1 match for 2 winners
            assert mock_create.call_count == 1
            assert len(result) == 1

    def test_validate_round_success(self, sample_gara):
        """Test successful round validation."""
        strategy = DirectEliminationStrategy(sample_gara)

        result = strategy.validate_round(1)

        assert result["is_valid"] is True
        assert "warnings" in result
        assert "errors" in result


class TestDoubleKnockoutStrategy:
    """Test double knockout strategy."""

    @pytest.fixture
    def sample_gara_double(self, db_session):
        """Create a sample gara for double knockout testing."""
        campionato = Campionato(name="Double KO Test", campionato_type="DoubleKnockout")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Double Knockout Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
            current_round=1,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_double_knockout_initialization(self, sample_gara_double):
        """Test double knockout strategy initialization."""
        strategy = DoubleKnockoutStrategy(sample_gara_double)
        assert strategy.gara == sample_gara_double

    def test_create_round_matches_first_round(self, sample_gara_double):
        """Test first round creation in double knockout."""
        strategy = DoubleKnockoutStrategy(sample_gara_double)

        with patch.object(strategy, "get_active_players") as mock_players, patch.object(
            strategy, "_create_winner_bracket_matches"
        ) as mock_winner_matches:

            # Mock 4 active players
            mock_players.return_value = [Mock() for _ in range(4)]
            mock_winner_matches.return_value = [Mock(), Mock()]

            result = strategy.create_round_matches(1)

            mock_winner_matches.assert_called_once()
            assert len(result) == 2

    def test_create_round_matches_subsequent_round(self, sample_gara_double):
        """Test subsequent round creation in double knockout."""
        strategy = DoubleKnockoutStrategy(sample_gara_double)

        with patch.object(
            strategy, "_create_winner_bracket_matches"
        ) as mock_winner, patch.object(
            strategy, "_create_loser_bracket_matches"
        ) as mock_loser:

            mock_winner.return_value = [Mock()]
            mock_loser.return_value = [Mock()]

            result = strategy.create_round_matches(2)

            mock_winner.assert_called_once()
            mock_loser.assert_called_once()
            assert len(result) == 2

    def test_validate_round_double_knockout(self, sample_gara_double):
        """Test round validation for double knockout."""
        strategy = DoubleKnockoutStrategy(sample_gara_double)

        result = strategy.validate_round(1)

        assert "is_valid" in result
        assert "warnings" in result
        assert "errors" in result


class TestRandomAntiRematchStrategy:
    """Test random anti-rematch strategy."""

    @pytest.fixture
    def sample_gara_random(self, db_session):
        """Create a sample gara for random anti-rematch testing."""
        campionato = Campionato(name="Random Test", campionato_type="RandomAntiRematch")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Random Anti-Rematch Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
            current_round=1,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_random_anti_rematch_initialization(self, sample_gara_random):
        """Test random anti-rematch strategy initialization."""
        strategy = RandomAntiRematchStrategy(sample_gara_random)
        assert strategy.gara == sample_gara_random

    def test_create_round_matches_basic(self, sample_gara_random):
        """Test basic round creation with anti-rematch logic."""
        strategy = RandomAntiRematchStrategy(sample_gara_random)

        with patch.object(strategy, "get_active_players") as mock_players, patch.object(
            strategy, "_get_previous_encounters"
        ) as mock_encounters, patch.object(
            strategy, "_create_optimal_pairings"
        ) as mock_pairings:

            # Mock 4 active players
            mock_players.return_value = [Mock() for _ in range(4)]
            mock_encounters.return_value = set()
            mock_pairings.return_value = [Mock(), Mock()]

            result = strategy.create_round_matches(1)

            mock_pairings.assert_called_once()
            assert len(result) == 2

    def test_validate_round_anti_rematch(self, sample_gara_random):
        """Test round validation for anti-rematch strategy."""
        strategy = RandomAntiRematchStrategy(sample_gara_random)

        result = strategy.validate_round(1)

        assert "is_valid" in result
        assert "warnings" in result
        assert "errors" in result


class TestRoundRobinStrategy:
    """Test round robin strategy."""

    @pytest.fixture
    def sample_gara_robin(self, db_session):
        """Create a sample gara for round robin testing."""
        campionato = Campionato(name="Round Robin Test", campionato_type="RoundRobin")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Round Robin Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
            current_round=1,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_round_robin_initialization(self, sample_gara_robin):
        """Test round robin strategy initialization."""
        strategy = RoundRobinStrategy(sample_gara_robin)
        assert strategy.gara == sample_gara_robin

    def test_create_round_matches_robin(self, sample_gara_robin):
        """Test round creation in round robin."""
        strategy = RoundRobinStrategy(sample_gara_robin)

        with patch.object(strategy, "get_active_players") as mock_players, patch.object(
            strategy, "_get_round_pairings"
        ) as mock_pairings:

            # Mock 4 active players
            mock_players.return_value = [Mock() for _ in range(4)]
            mock_pairings.return_value = [(Mock(), Mock()), (Mock(), Mock())]

            with patch.object(strategy, "_create_match") as mock_create:
                mock_create.return_value = Mock()

                result = strategy.create_round_matches(1)

                mock_pairings.assert_called_once_with(1)
                assert mock_create.call_count == 2
                assert len(result) == 2

    def test_validate_round_robin(self, sample_gara_robin):
        """Test round validation for round robin."""
        strategy = RoundRobinStrategy(sample_gara_robin)

        result = strategy.validate_round(1)

        assert "is_valid" in result
        assert "warnings" in result
        assert "errors" in result

    def test_calculate_total_rounds_robin(self, sample_gara_robin):
        """Test total rounds calculation for round robin."""
        strategy = RoundRobinStrategy(sample_gara_robin)

        with patch.object(strategy, "get_active_players") as mock_players:
            # Mock 4 players should need 3 rounds (each plays each other once)
            mock_players.return_value = [Mock() for _ in range(4)]

            total_rounds = strategy.calculate_total_rounds()

            # For 4 players in round robin: n-1 = 3 rounds
            assert total_rounds == 3


class TestStrategyUtilities:
    """Test utility functions across strategies."""

    def test_strategy_factory_pattern(self):
        """Test that all strategies follow the same interface."""
        gara = Mock()

        strategies = [
            DirectEliminationStrategy(gara),
            DoubleKnockoutStrategy(gara),
            RandomAntiRematchStrategy(gara),
            RoundRobinStrategy(gara),
        ]

        for strategy in strategies:
            # All should have these methods
            assert hasattr(strategy, "create_round_matches")
            assert hasattr(strategy, "validate_round")
            assert hasattr(strategy, "get_active_players")

            # Test that methods exist and are callable
            assert callable(getattr(strategy, "create_round_matches"))
            assert callable(getattr(strategy, "validate_round"))
            assert callable(getattr(strategy, "get_active_players"))
