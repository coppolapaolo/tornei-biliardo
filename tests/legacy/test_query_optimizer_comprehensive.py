"""
Comprehensive tests for models/optimization/query_optimizer.py
Testing all classes and functions to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from models.optimization.query_optimizer import (
    QueryMetrics,
    N1Problem,
    OptimizationSuggestion,
    QueryAnalyzer,
    QueryOptimizer,
    query_optimizer,
    optimized_query,
    bulk_load_relationships,
)


class TestQueryMetrics:
    """Test QueryMetrics dataclass functionality."""

    def test_query_metrics_initialization(self):
        """Test QueryMetrics initialization."""
        metrics = QueryMetrics(query_hash="abc123", sql_text="SELECT * FROM users")

        assert metrics.query_hash == "abc123"
        assert metrics.sql_text == "SELECT * FROM users"
        assert metrics.execution_count == 0
        assert metrics.total_time_ms == 0.0
        assert metrics.min_time_ms == float("inf")
        assert metrics.max_time_ms == 0.0
        assert metrics.avg_time_ms == 0.0
        assert metrics.last_executed is None
        assert metrics.parameters == []
        assert metrics.stack_traces == []

    def test_add_execution_basic(self):
        """Test basic add_execution functionality."""
        metrics = QueryMetrics("hash1", "SELECT 1")

        metrics.add_execution(50.5)

        assert metrics.execution_count == 1
        assert metrics.total_time_ms == 50.5
        assert metrics.min_time_ms == 50.5
        assert metrics.max_time_ms == 50.5
        assert metrics.avg_time_ms == 50.5
        assert metrics.last_executed is not None

    def test_add_execution_multiple(self):
        """Test multiple executions with different durations."""
        metrics = QueryMetrics("hash1", "SELECT 1")

        metrics.add_execution(100.0)
        metrics.add_execution(50.0)
        metrics.add_execution(200.0)

        assert metrics.execution_count == 3
        assert metrics.total_time_ms == 350.0
        assert metrics.min_time_ms == 50.0
        assert metrics.max_time_ms == 200.0
        assert metrics.avg_time_ms == 350.0 / 3

    def test_add_execution_with_parameters(self):
        """Test add_execution with parameters."""
        metrics = QueryMetrics("hash1", "SELECT * FROM users WHERE id = ?")

        params1 = {"id": 1}
        params2 = {"id": 2}

        metrics.add_execution(10.0, params1)
        metrics.add_execution(15.0, params2)

        assert len(metrics.parameters) == 2
        assert params1 in metrics.parameters
        assert params2 in metrics.parameters

    def test_add_execution_parameters_limit(self):
        """Test that parameters are limited to 10."""
        metrics = QueryMetrics("hash1", "SELECT 1")

        # Add more than 10 parameters
        for i in range(15):
            metrics.add_execution(10.0, {"param": i})

        assert len(metrics.parameters) == 10

    def test_add_execution_with_stack_trace(self):
        """Test add_execution with stack trace."""
        metrics = QueryMetrics("hash1", "SELECT 1")

        stack_trace = "line 1\nline 2\nline 3"
        metrics.add_execution(10.0, stack_trace=stack_trace)

        assert len(metrics.stack_traces) == 1
        assert metrics.stack_traces[0] == stack_trace

    def test_add_execution_stack_traces_limit(self):
        """Test that stack traces are limited to 5."""
        metrics = QueryMetrics("hash1", "SELECT 1")

        # Add more than 5 stack traces
        for i in range(8):
            metrics.add_execution(10.0, stack_trace=f"trace {i}")

        assert len(metrics.stack_traces) == 5


class TestN1Problem:
    """Test N1Problem dataclass functionality."""

    def test_n1_problem_initialization(self):
        """Test N1Problem initialization."""
        detection_time = datetime.utcnow()
        affected_tables = {"users", "orders"}

        problem = N1Problem(
            parent_query="SELECT * FROM users",
            child_queries=[
                "SELECT * FROM orders WHERE user_id = 1",
                "SELECT * FROM orders WHERE user_id = 2",
            ],
            detection_time=detection_time,
            severity="medium",
            suggested_solution="Use eager loading",
            affected_tables=affected_tables,
        )

        assert problem.parent_query == "SELECT * FROM users"
        assert len(problem.child_queries) == 2
        assert problem.detection_time == detection_time
        assert problem.severity == "medium"
        assert problem.suggested_solution == "Use eager loading"
        assert problem.affected_tables == affected_tables

    def test_query_count_property(self):
        """Test query_count property."""
        problem = N1Problem(
            parent_query="SELECT * FROM users",
            child_queries=["query1", "query2", "query3"],
            detection_time=datetime.utcnow(),
            severity="high",
            suggested_solution="Use join",
            affected_tables=set(),
        )

        assert problem.query_count == 3


class TestOptimizationSuggestion:
    """Test OptimizationSuggestion dataclass functionality."""

    def test_optimization_suggestion_initialization(self):
        """Test OptimizationSuggestion initialization."""
        suggestion = OptimizationSuggestion(
            query_hash="abc123",
            suggestion_type="index",
            description="Add index on user_id column",
            expected_improvement="50% faster",
            implementation_difficulty="easy",
            code_example="CREATE INDEX idx_user_id ON table (user_id);",
        )

        assert suggestion.query_hash == "abc123"
        assert suggestion.suggestion_type == "index"
        assert suggestion.description == "Add index on user_id column"
        assert suggestion.expected_improvement == "50% faster"
        assert suggestion.implementation_difficulty == "easy"
        assert suggestion.code_example is not None

    def test_optimization_suggestion_optional_code_example(self):
        """Test OptimizationSuggestion with no code example."""
        suggestion = OptimizationSuggestion(
            query_hash="abc123",
            suggestion_type="caching",
            description="Cache this query",
            expected_improvement="90% faster",
            implementation_difficulty="medium",
        )

        assert suggestion.code_example is None


class TestQueryAnalyzer:
    """Test QueryAnalyzer class functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create a QueryAnalyzer instance for testing."""
        return QueryAnalyzer()

    def test_analyzer_initialization(self):
        """Test QueryAnalyzer initialization."""
        analyzer = QueryAnalyzer()

        assert analyzer._query_metrics == {}
        assert analyzer._n1_problems == []
        assert analyzer._suggestions == []
        assert analyzer._monitoring_enabled is True
        assert hasattr(analyzer, "_lock")
        assert analyzer.slow_query_threshold_ms == 100
        assert analyzer.n1_detection_threshold == 3
        assert analyzer.frequent_query_threshold == 10

    def test_record_query_basic(self, analyzer):
        """Test basic query recording."""
        analyzer.record_query("hash1", "SELECT 1", 50.0)

        assert "hash1" in analyzer._query_metrics
        metrics = analyzer._query_metrics["hash1"]
        assert metrics.query_hash == "hash1"
        assert metrics.sql_text == "SELECT 1"
        assert metrics.execution_count == 1
        assert metrics.total_time_ms == 50.0

    def test_record_query_monitoring_disabled(self, analyzer):
        """Test query recording when monitoring is disabled."""
        analyzer._monitoring_enabled = False
        analyzer.record_query("hash1", "SELECT 1", 50.0)

        assert "hash1" not in analyzer._query_metrics

    def test_record_query_multiple_executions(self, analyzer):
        """Test recording multiple executions of the same query."""
        analyzer.record_query("hash1", "SELECT 1", 50.0)
        analyzer.record_query("hash1", "SELECT 1", 75.0)

        metrics = analyzer._query_metrics["hash1"]
        assert metrics.execution_count == 2
        assert metrics.total_time_ms == 125.0
        assert metrics.avg_time_ms == 62.5

    @patch.object(QueryAnalyzer, "_analyze_query")
    def test_record_query_triggers_analysis_slow(self, mock_analyze, analyzer):
        """Test that slow queries trigger analysis."""
        analyzer.slow_query_threshold_ms = 50
        analyzer.record_query("hash1", "SELECT 1", 100.0)  # Slow query

        mock_analyze.assert_called_once()

    @patch.object(QueryAnalyzer, "_analyze_query")
    def test_record_query_triggers_analysis_frequent(self, mock_analyze, analyzer):
        """Test that frequent queries trigger analysis."""
        analyzer.frequent_query_threshold = 2

        # Record query multiple times
        analyzer.record_query("hash1", "SELECT 1", 10.0)
        mock_analyze.assert_not_called()

        analyzer.record_query("hash1", "SELECT 1", 10.0)  # Should trigger analysis
        mock_analyze.assert_called_once()

    def test_detect_n1_problems_no_problems(self, analyzer):
        """Test N+1 detection when no problems exist."""
        analyzer.record_query("hash1", "SELECT * FROM users", 10.0)

        problems = analyzer.detect_n1_problems()

        assert problems == []

    def test_detect_n1_problems_with_problems(self, analyzer):
        """Test N+1 detection with actual problems."""
        # Use real datetime instead of mocking to avoid recursion
        from datetime import datetime

        now = datetime.utcnow()

        # Setup analyzer with mocked methods
        analyzer._queries_are_similar = Mock(return_value=True)
        analyzer._calculate_n1_severity = Mock(return_value="medium")
        analyzer._suggest_n1_solution = Mock(return_value="Use eager loading")
        analyzer._extract_tables = Mock(return_value={"users", "orders"})

        # Create parent query (executed once)
        parent_metrics = QueryMetrics("parent_hash", "SELECT * FROM users")
        parent_metrics.add_execution(10.0)
        parent_metrics.last_executed = now

        # Create child queries (executed multiple times)
        child_metrics = QueryMetrics(
            "child_hash", "SELECT * FROM orders WHERE user_id = ?"
        )
        for _ in range(5):  # Execute 5 times (above threshold of 3)
            child_metrics.add_execution(5.0)
        child_metrics.last_executed = now

        analyzer._query_metrics = {
            "parent_hash": parent_metrics,
            "child_hash": child_metrics,
        }

        problems = analyzer.detect_n1_problems()

        assert len(problems) == 1
        problem = problems[0]
        assert problem.parent_query == "SELECT * FROM users"
        assert len(problem.child_queries) == 1
        assert problem.severity == "medium"

    def test_get_optimization_suggestions_empty(self, analyzer):
        """Test getting optimization suggestions when none exist."""
        suggestions = analyzer.get_optimization_suggestions()

        assert suggestions == []

    @patch.object(QueryAnalyzer, "_generate_optimization_suggestion")
    def test_get_optimization_suggestions_with_suggestions(
        self, mock_generate, analyzer
    ):
        """Test getting optimization suggestions."""
        # Create slow query
        analyzer.slow_query_threshold_ms = 50
        analyzer.record_query("hash1", "SELECT * FROM users", 100.0)

        # Mock suggestion generation
        mock_suggestion = OptimizationSuggestion(
            query_hash="hash1",
            suggestion_type="index",
            description="Add index",
            expected_improvement="50% faster",
            implementation_difficulty="easy",
        )
        mock_generate.return_value = mock_suggestion

        suggestions = analyzer.get_optimization_suggestions()

        assert len(suggestions) == 1
        assert suggestions[0] == mock_suggestion

    def test_get_performance_report(self, analyzer):
        """Test getting performance report."""
        # Add some queries
        analyzer.record_query("hash1", "SELECT 1", 50.0)
        analyzer.record_query("hash2", "SELECT 2", 150.0)  # Slow query

        # Record frequent query
        for _ in range(15):
            analyzer.record_query("hash3", "SELECT 3", 20.0)

        report = analyzer.get_performance_report()

        assert "summary" in report
        assert "slowest_queries" in report
        assert "most_frequent_queries" in report
        assert "n1_problems" in report
        assert "optimization_suggestions" in report

        summary = report["summary"]
        assert summary["total_unique_queries"] == 3
        assert summary["slow_queries_count"] == 1
        assert summary["frequent_queries_count"] == 1

    def test_clear_metrics(self, analyzer):
        """Test clearing all metrics."""
        # Add some data
        analyzer.record_query("hash1", "SELECT 1", 50.0)
        analyzer._n1_problems.append(Mock())
        analyzer._suggestions.append(Mock())

        analyzer.clear_metrics()

        assert analyzer._query_metrics == {}
        assert analyzer._n1_problems == []
        assert analyzer._suggestions == []

    def test_normalize_query(self, analyzer):
        """Test query normalization."""
        query = "SELECT * FROM users WHERE id = ? AND name = $1"
        normalized = analyzer._normalize_query(query)

        assert "?" in normalized
        assert "$1" not in normalized
        assert normalized.islower()

    def test_calculate_similarity(self, analyzer):
        """Test similarity calculation."""
        str1 = "SELECT * FROM users WHERE id = ?"
        str2 = "SELECT * FROM users WHERE name = ?"

        similarity = analyzer._calculate_similarity(str1, str2)

        assert 0.0 <= similarity <= 1.0
        assert similarity > 0.5  # Should be quite similar

    def test_calculate_n1_severity(self, analyzer):
        """Test N+1 severity calculation."""
        assert analyzer._calculate_n1_severity(3) == "low"
        assert analyzer._calculate_n1_severity(10) == "medium"
        assert analyzer._calculate_n1_severity(25) == "high"

    def test_suggest_n1_solution(self, analyzer):
        """Test N+1 solution suggestion."""
        parent_query = "SELECT * FROM users"
        child_queries = ["SELECT * FROM orders WHERE user_id = ?"]

        solution = analyzer._suggest_n1_solution(parent_query, child_queries)

        assert "eager loading" in solution.lower()

    def test_extract_tables(self, analyzer):
        """Test table extraction from SQL."""
        query = "SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id"
        tables = analyzer._extract_tables(query)

        assert "users" in tables
        assert "orders" in tables

    def test_generate_optimization_suggestion_index(self, analyzer):
        """Test optimization suggestion for index."""
        metrics = QueryMetrics(
            "hash1", "SELECT * FROM users WHERE id = 1 ORDER BY name"
        )
        metrics.add_execution(150.0)  # Slow query

        suggestion = analyzer._generate_optimization_suggestion(metrics)

        assert suggestion is not None
        assert suggestion.suggestion_type == "index"

    def test_generate_optimization_suggestion_eager_loading(self, analyzer):
        """Test optimization suggestion for eager loading."""
        metrics = QueryMetrics("hash1", "SELECT * FROM users")
        # Execute many times
        for _ in range(25):
            metrics.add_execution(10.0)

        suggestion = analyzer._generate_optimization_suggestion(metrics)

        assert suggestion is not None
        assert suggestion.suggestion_type == "eager_loading"

    def test_generate_optimization_suggestion_caching(self, analyzer):
        """Test optimization suggestion for caching."""
        metrics = QueryMetrics("hash1", "SELECT * FROM users")
        metrics.add_execution(250.0)  # Very slow query

        suggestion = analyzer._generate_optimization_suggestion(metrics)

        assert suggestion is not None
        assert suggestion.suggestion_type == "caching"

    def test_generate_optimization_suggestion_none(self, analyzer):
        """Test no optimization suggestion for fast, infrequent queries."""
        metrics = QueryMetrics("hash1", "SELECT 1")
        metrics.add_execution(10.0)  # Fast query, executed only once

        suggestion = analyzer._generate_optimization_suggestion(metrics)

        assert suggestion is None


class TestQueryOptimizer:
    """Test QueryOptimizer class functionality."""

    @pytest.fixture
    def optimizer(self):
        """Create a QueryOptimizer instance for testing."""
        return QueryOptimizer()

    def test_optimizer_initialization(self, optimizer):
        """Test QueryOptimizer initialization."""
        assert isinstance(optimizer.analyzer, QueryAnalyzer)
        assert optimizer._optimization_enabled is True

    def test_generate_query_hash(self, optimizer):
        """Test query hash generation."""
        statement = "SELECT * FROM users WHERE id = ?"
        hash1 = optimizer._generate_query_hash(statement)
        hash2 = optimizer._generate_query_hash(statement)

        assert hash1 == hash2  # Same query should produce same hash
        assert len(hash1) == 12  # Should be 12 characters

    def test_monitoring_disabled_context_manager(self, optimizer):
        """Test monitoring disabled context manager."""
        assert optimizer._optimization_enabled is True

        with optimizer.monitoring_disabled():
            assert optimizer._optimization_enabled is False

        assert optimizer._optimization_enabled is True

    def test_get_performance_dashboard(self, optimizer):
        """Test getting performance dashboard."""
        with patch("models.caching.cache_manager") as mock_cache_manager:
            mock_cache_manager.get_comprehensive_stats.return_value = {"hit_rate": 0.85}

            dashboard = optimizer.get_performance_dashboard()

            assert "query_analysis" in dashboard
            assert "cache_stats" in dashboard
            assert "recommendations" in dashboard

    @patch.object(QueryAnalyzer, "detect_n1_problems")
    @patch.object(QueryAnalyzer, "get_optimization_suggestions")
    def test_get_optimization_recommendations(
        self, mock_suggestions, mock_n1, optimizer
    ):
        """Test getting optimization recommendations."""
        # Mock N+1 problems
        mock_n1_problem = N1Problem(
            parent_query="SELECT * FROM users",
            child_queries=["SELECT * FROM orders WHERE user_id = 1"] * 10,
            detection_time=datetime.utcnow(),
            severity="high",
            suggested_solution="Use eager loading",
            affected_tables=set(),
        )
        mock_n1.return_value = [mock_n1_problem]

        # Mock suggestions
        mock_suggestion = OptimizationSuggestion(
            query_hash="hash1",
            suggestion_type="index",
            description="Add index",
            expected_improvement="50% faster",
            implementation_difficulty="easy",
        )
        mock_suggestions.return_value = [mock_suggestion]

        recommendations = optimizer.get_optimization_recommendations()

        assert len(recommendations) >= 2  # At least N+1 problem and suggestion
        # Verify critical priority comes first
        critical_rec = next(
            (r for r in recommendations if r["priority"] == "critical"), None
        )
        assert critical_rec is not None


class TestOptimizedQueryDecorator:
    """Test optimized_query decorator functionality."""

    def test_optimized_query_no_cache(self):
        """Test optimized_query decorator without caching."""
        with patch("models.caching.cache_manager") as mock_cache_manager:

            @optimized_query()
            def test_function():
                return "result"

            result = test_function()

            assert result == "result"
            mock_cache_manager.get.assert_not_called()
            mock_cache_manager.set.assert_not_called()

    def test_optimized_query_with_cache_miss(self):
        """Test optimized_query decorator with cache miss."""
        with patch("models.caching.cache_manager") as mock_cache_manager:
            mock_cache_manager.get.return_value = None

            @optimized_query(cache_ttl=300, cache_tags=["test"])
            def test_function():
                return "result"

            result = test_function()

            assert result == "result"
            mock_cache_manager.get.assert_called_once()
            mock_cache_manager.set.assert_called_once()

    def test_optimized_query_with_cache_hit(self):
        """Test optimized_query decorator with cache hit."""
        with patch("models.caching.cache_manager") as mock_cache_manager:
            mock_cache_manager.get.return_value = "cached_result"

            @optimized_query(cache_ttl=300)
            def test_function():
                return "result"

            result = test_function()

            assert result == "cached_result"
            mock_cache_manager.get.assert_called_once()
            mock_cache_manager.set.assert_not_called()

    def test_optimized_query_with_args_kwargs(self):
        """Test optimized_query decorator with function arguments."""
        with patch("models.caching.cache_manager") as mock_cache_manager:
            mock_cache_manager.get.return_value = None

            @optimized_query(cache_ttl=300)
            def test_function(arg1, arg2, kwarg1=None):
                return f"{arg1}-{arg2}-{kwarg1}"

            result = test_function("a", "b", kwarg1="c")

            assert result == "a-b-c"
            mock_cache_manager.get.assert_called_once()
            mock_cache_manager.set.assert_called_once()


class TestBulkLoadRelationships:
    """Test bulk_load_relationships function."""

    def test_bulk_load_relationships_basic(self):
        """Test bulk_load_relationships basic functionality."""
        # Create a simple mock query that just tracks options calls
        mock_query = Mock()
        mock_query.options.return_value = mock_query

        # Test with a simple mock relationship that doesn't trigger SQLAlchemy
        mock_relationship = Mock()
        mock_relationship._sa_class_manager = (
            Mock()
        )  # Make it look like SQLAlchemy attribute

        result = bulk_load_relationships(mock_query, mock_relationship)

        assert result == mock_query
        assert mock_query.options.called


class TestGlobalQueryOptimizer:
    """Test global query optimizer instance."""

    def test_global_optimizer_exists(self):
        """Test that global query optimizer instance exists."""
        assert query_optimizer is not None
        assert isinstance(query_optimizer, QueryOptimizer)

    def test_global_optimizer_functionality(self):
        """Test basic functionality of global query optimizer."""
        # Test that we can access the analyzer
        assert hasattr(query_optimizer, "analyzer")
        assert isinstance(query_optimizer.analyzer, QueryAnalyzer)

        # Test that monitoring can be disabled
        with query_optimizer.monitoring_disabled():
            assert query_optimizer._optimization_enabled is False


class TestSQLAlchemyEventListeners:
    """Test SQLAlchemy event listener functionality."""

    def test_before_cursor_execute_event(self):
        """Test before_cursor_execute event listener functionality."""
        # Create a mock context
        mock_context = Mock()

        # Import the event listener function and test basic setup
        from models.optimization.query_optimizer import QueryOptimizer

        optimizer = QueryOptimizer()

        # We can't easily test the actual event listener, but we can test
        # that the setup doesn't cause errors
        assert optimizer._optimization_enabled is True

    def test_query_optimizer_integration(self):
        """Test integration of query optimizer components."""
        # Test that all components work together
        optimizer = QueryOptimizer()

        # Test basic functionality
        dashboard = optimizer.get_performance_dashboard()
        assert isinstance(dashboard, dict)

        recommendations = optimizer.get_optimization_recommendations()
        assert isinstance(recommendations, list)
