"""
Module: models/optimization/query_optimizer.py
Purpose: Database query optimization and performance monitoring
Requirements: Implement query analysis, N+1 detection, and optimization strategies
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
import logging
import time
import threading
from contextlib import contextmanager
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Query

from ..caching import cache_manager
from models.base import utc_now

# Setup logging
logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class QueryMetrics:
    """Metrics for database query performance."""

    query_hash: str
    sql_text: str
    execution_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    last_executed: Optional[datetime] = None
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    stack_traces: List[str] = field(default_factory=list)

    def add_execution(
        self,
        duration_ms: float,
        params: Optional[Dict] = None,
        stack_trace: Optional[str] = None,
    ):
        """Record a query execution."""
        self.execution_count += 1
        self.total_time_ms += duration_ms
        self.min_time_ms = min(self.min_time_ms, duration_ms)
        self.max_time_ms = max(self.max_time_ms, duration_ms)
        self.avg_time_ms = self.total_time_ms / self.execution_count
        self.last_executed = utc_now()

        if params and len(self.parameters) < 10:  # Keep sample of parameters
            self.parameters.append(params)

        if stack_trace and len(self.stack_traces) < 5:  # Keep sample of stack traces
            self.stack_traces.append(stack_trace)


@dataclass
class N1Problem:
    """Detected N+1 query problem."""

    parent_query: str
    child_queries: List[str]
    detection_time: datetime
    severity: str  # 'low', 'medium', 'high'
    suggested_solution: str
    affected_tables: Set[str]

    @property
    def query_count(self) -> int:
        return len(self.child_queries)


@dataclass
class OptimizationSuggestion:
    """Query optimization suggestion."""

    query_hash: str
    suggestion_type: str  # 'index', 'eager_loading', 'caching', 'query_rewrite'
    description: str
    expected_improvement: str
    implementation_difficulty: str  # 'easy', 'medium', 'hard'
    code_example: Optional[str] = None


class QueryAnalyzer:
    """Analyzes database queries for performance issues."""

    def __init__(self):
        self._query_metrics: Dict[str, QueryMetrics] = {}
        self._n1_problems: List[N1Problem] = []
        self._suggestions: List[OptimizationSuggestion] = []
        self._monitoring_enabled = True
        self._lock = threading.RLock()

        # Thresholds for analysis
        self.slow_query_threshold_ms = 100
        self.n1_detection_threshold = 3
        self.frequent_query_threshold = 10

    def record_query(
        self,
        query_hash: str,
        sql_text: str,
        duration_ms: float,
        params: Optional[Dict] = None,
        stack_trace: Optional[str] = None,
    ):
        """Record a query execution for analysis."""
        if not self._monitoring_enabled:
            return

        with self._lock:
            if query_hash not in self._query_metrics:
                self._query_metrics[query_hash] = QueryMetrics(
                    query_hash=query_hash, sql_text=sql_text
                )

            metrics = self._query_metrics[query_hash]
            metrics.add_execution(duration_ms, params, stack_trace)

            # Trigger analysis for slow or frequent queries
            if (
                duration_ms > self.slow_query_threshold_ms
                or metrics.execution_count % self.frequent_query_threshold == 0
            ):
                self._analyze_query(metrics)

    def detect_n1_problems(self, time_window_minutes: int = 5) -> List[N1Problem]:
        """Detect N+1 query problems in recent executions."""
        cutoff_time = utc_now() - timedelta(minutes=time_window_minutes)

        # Group queries by similarity and timing
        recent_queries = {
            hash_key: metrics
            for hash_key, metrics in self._query_metrics.items()
            if metrics.last_executed and metrics.last_executed > cutoff_time
        }

        # Look for patterns indicating N+1 problems
        potential_problems = []

        for parent_hash, parent_metrics in recent_queries.items():
            if parent_metrics.execution_count == 1:  # Potential parent query
                # Look for similar queries executed multiple times shortly after
                child_candidates = []

                for child_hash, child_metrics in recent_queries.items():
                    if (
                        child_hash != parent_hash
                        and child_metrics.execution_count >= self.n1_detection_threshold
                        and self._queries_are_similar(
                            parent_metrics.sql_text, child_metrics.sql_text
                        )
                    ):
                        child_candidates.append(child_metrics.sql_text)

                if child_candidates:
                    severity = self._calculate_n1_severity(len(child_candidates))
                    solution = self._suggest_n1_solution(
                        parent_metrics.sql_text, child_candidates
                    )

                    problem = N1Problem(
                        parent_query=parent_metrics.sql_text,
                        child_queries=child_candidates,
                        detection_time=utc_now(),
                        severity=severity,
                        suggested_solution=solution,
                        affected_tables=self._extract_tables(parent_metrics.sql_text),
                    )
                    potential_problems.append(problem)

        # Update stored problems
        with self._lock:
            self._n1_problems.extend(potential_problems)
            # Keep only recent problems
            self._n1_problems = [
                p
                for p in self._n1_problems
                if (utc_now() - p.detection_time).total_seconds()
                < 3600  # 1 hour
            ]

        return potential_problems

    def get_optimization_suggestions(
        self, limit: int = 10
    ) -> List[OptimizationSuggestion]:
        """Get optimization suggestions based on query analysis."""
        with self._lock:
            suggestions = []

            # Analyze slow queries
            slow_queries = [
                metrics
                for metrics in self._query_metrics.values()
                if metrics.avg_time_ms > self.slow_query_threshold_ms
            ]

            for metrics in sorted(
                slow_queries, key=lambda m: m.avg_time_ms, reverse=True
            )[:limit]:
                suggestion = self._generate_optimization_suggestion(metrics)
                if suggestion:
                    suggestions.append(suggestion)

            self._suggestions.extend(suggestions)
            return suggestions

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        with self._lock:
            total_queries = len(self._query_metrics)
            total_executions = sum(
                m.execution_count for m in self._query_metrics.values()
            )
            avg_execution_time = (
                sum(m.avg_time_ms for m in self._query_metrics.values()) / total_queries
                if total_queries > 0
                else 0
            )

            slow_queries = [
                m
                for m in self._query_metrics.values()
                if m.avg_time_ms > self.slow_query_threshold_ms
            ]

            frequent_queries = [
                m
                for m in self._query_metrics.values()
                if m.execution_count >= self.frequent_query_threshold
            ]

            return {
                "summary": {
                    "total_unique_queries": total_queries,
                    "total_executions": total_executions,
                    "average_execution_time_ms": round(avg_execution_time, 2),
                    "slow_queries_count": len(slow_queries),
                    "frequent_queries_count": len(frequent_queries),
                    "n1_problems_detected": len(self._n1_problems),
                },
                "slowest_queries": [
                    {
                        "sql": (
                            m.sql_text[:200] + "..."
                            if len(m.sql_text) > 200
                            else m.sql_text
                        ),
                        "avg_time_ms": round(m.avg_time_ms, 2),
                        "execution_count": m.execution_count,
                        "total_time_ms": round(m.total_time_ms, 2),
                    }
                    for m in sorted(
                        slow_queries, key=lambda x: x.avg_time_ms, reverse=True
                    )[:10]
                ],
                "most_frequent_queries": [
                    {
                        "sql": (
                            m.sql_text[:200] + "..."
                            if len(m.sql_text) > 200
                            else m.sql_text
                        ),
                        "execution_count": m.execution_count,
                        "avg_time_ms": round(m.avg_time_ms, 2),
                    }
                    for m in sorted(
                        frequent_queries, key=lambda x: x.execution_count, reverse=True
                    )[:10]
                ],
                "n1_problems": [
                    {
                        "parent_query": (
                            p.parent_query[:200] + "..."
                            if len(p.parent_query) > 200
                            else p.parent_query
                        ),
                        "child_query_count": p.query_count,
                        "severity": p.severity,
                        "suggested_solution": p.suggested_solution,
                    }
                    for p in self._n1_problems[-5:]  # Recent problems
                ],
                "optimization_suggestions": [
                    {
                        "type": s.suggestion_type,
                        "description": s.description,
                        "expected_improvement": s.expected_improvement,
                        "difficulty": s.implementation_difficulty,
                    }
                    for s in self._suggestions[-10:]  # Recent suggestions
                ],
            }

    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._query_metrics.clear()
            self._n1_problems.clear()
            self._suggestions.clear()

    def _analyze_query(self, metrics: QueryMetrics) -> None:
        """Analyze individual query for optimization opportunities."""
        # Check for potential issues
        if metrics.avg_time_ms > self.slow_query_threshold_ms * 2:
            logger.warning(
                f"Very slow query detected: {metrics.avg_time_ms:.2f}ms average"
            )

        if metrics.execution_count > self.frequent_query_threshold * 5:
            logger.info(f"Frequently executed query: {metrics.execution_count} times")

    def _queries_are_similar(self, query1: str, query2: str) -> bool:
        """Check if two queries are similar (likely N+1 pattern)."""
        # Simple heuristic: remove parameters and compare structure
        normalized1 = self._normalize_query(query1)
        normalized2 = self._normalize_query(query2)

        # Check if they have similar structure but different parameters
        return (
            len(normalized1) > 20
            and len(normalized2) > 20
            and self._calculate_similarity(normalized1, normalized2) > 0.8
        )

    def _normalize_query(self, query: str) -> str:
        """Normalize query by removing parameters and formatting."""
        import re

        # Remove parameter placeholders
        normalized = re.sub(r"\?|\$\d+|:\w+", "?", query)
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        return normalized.lower()

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings."""
        # Simple Jaccard similarity on words
        words1 = set(str1.split())
        words2 = set(str2.split())

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0

    def _calculate_n1_severity(self, child_count: int) -> str:
        """Calculate severity of N+1 problem."""
        if child_count < 5:
            return "low"
        elif child_count < 20:
            return "medium"
        else:
            return "high"

    def _suggest_n1_solution(self, parent_query: str, child_queries: List[str]) -> str:
        """Suggest solution for N+1 problem."""
        if "select" in parent_query.lower() and "from" in parent_query.lower():
            return "Consider using eager loading (joinedload or selectinload) to fetch related data in a single query"
        return "Optimize query to reduce the number of database round trips"

    def _extract_tables(self, query: str) -> Set[str]:
        """Extract table names from SQL query."""
        import re

        # Simple pattern to find table names after FROM and JOIN
        tables = set()

        # Find tables after FROM
        from_matches = re.findall(r"from\s+(\w+)", query.lower())
        tables.update(from_matches)

        # Find tables after JOIN
        join_matches = re.findall(r"join\s+(\w+)", query.lower())
        tables.update(join_matches)

        return tables

    def _generate_optimization_suggestion(
        self, metrics: QueryMetrics
    ) -> Optional[OptimizationSuggestion]:
        """Generate optimization suggestion for a query."""
        sql_lower = metrics.sql_text.lower()

        # Index suggestions
        if "where" in sql_lower and "order by" in sql_lower:
            return OptimizationSuggestion(
                query_hash=metrics.query_hash,
                suggestion_type="index",
                description="Consider adding composite index for WHERE and ORDER BY columns",
                expected_improvement="30-60% faster execution",
                implementation_difficulty="easy",
                code_example="CREATE INDEX idx_table_col1_col2 ON table (col1, col2);",
            )

        # Eager loading suggestions
        if metrics.execution_count > 20 and "select" in sql_lower:
            return OptimizationSuggestion(
                query_hash=metrics.query_hash,
                suggestion_type="eager_loading",
                description="High frequency query - consider eager loading or caching",
                expected_improvement="Reduce query count by 50-90%",
                implementation_difficulty="medium",
                code_example="query.options(joinedload(Model.relationship))",
            )

        # Caching suggestions
        if metrics.avg_time_ms > 200:
            return OptimizationSuggestion(
                query_hash=metrics.query_hash,
                suggestion_type="caching",
                description="Slow query - consider result caching",
                expected_improvement="Near-instant response for cached results",
                implementation_difficulty="easy",
                code_example="@cached(ttl_seconds=300, tags=['model'])",
            )

        return None


class QueryOptimizer:
    """Main query optimization coordinator."""

    def __init__(self):
        self.analyzer = QueryAnalyzer()
        self._optimization_enabled = True
        self._setup_sqlalchemy_monitoring()

    def _setup_sqlalchemy_monitoring(self):
        """Setup SQLAlchemy event listeners for query monitoring."""

        @event.listens_for(Engine, "before_cursor_execute")
        def receive_before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            context._query_start_time = time.time()

        @event.listens_for(Engine, "after_cursor_execute")
        def receive_after_cursor_execute(
            conn, cursor, statement, parameters, context, executemany
        ):
            if not self._optimization_enabled:
                return

            total_time = time.time() - context._query_start_time
            total_time_ms = total_time * 1000

            # Generate query hash
            query_hash = self._generate_query_hash(statement)

            # Record the query
            self.analyzer.record_query(
                query_hash=query_hash,
                sql_text=statement,
                duration_ms=total_time_ms,
                params=parameters,
            )

    def _generate_query_hash(self, statement: str) -> str:
        """Generate hash for query statement."""
        import hashlib

        normalized = self.analyzer._normalize_query(statement)
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    @contextmanager
    def monitoring_disabled(self):
        """Context manager to temporarily disable monitoring."""
        old_value = self._optimization_enabled
        self._optimization_enabled = False
        try:
            yield
        finally:
            self._optimization_enabled = old_value

    def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data."""
        return {
            "query_analysis": self.analyzer.get_performance_report(),
            "cache_stats": cache_manager.get_comprehensive_stats(),
            "recommendations": self.get_optimization_recommendations(),
        }

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get prioritized optimization recommendations."""
        recommendations = []

        # N+1 problems (highest priority)
        n1_problems = self.analyzer.detect_n1_problems()
        for problem in n1_problems:
            recommendations.append(
                {
                    "priority": "critical" if problem.severity == "high" else "high",
                    "type": "n1_problem",
                    "title": f"N+1 Query Problem Detected ({problem.query_count} queries)",
                    "description": problem.suggested_solution,
                    "estimated_impact": "High - Reduce database load significantly",
                }
            )

        # Optimization suggestions
        suggestions = self.analyzer.get_optimization_suggestions()
        for suggestion in suggestions:
            priority = (
                "medium"
                if suggestion.suggestion_type in ["index", "caching"]
                else "low"
            )
            recommendations.append(
                {
                    "priority": priority,
                    "type": suggestion.suggestion_type,
                    "title": suggestion.description,
                    "description": suggestion.code_example
                    or "See implementation guide",
                    "estimated_impact": suggestion.expected_improvement,
                }
            )

        return sorted(
            recommendations,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}[
                x["priority"]
            ],
        )


# Global query optimizer instance
query_optimizer = QueryOptimizer()


def optimized_query(
    eager_load: Optional[List[str]] = None,
    cache_ttl: Optional[int] = None,
    cache_tags: Optional[List[str]] = None,
):
    """Decorator for optimized database queries."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            cache_key = None

            # Apply caching if specified
            if cache_ttl:
                cache_key = (
                    f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
                )
                cached_result = cache_manager.get(cache_key)
                if cached_result is not None:
                    return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result if specified
            if cache_ttl and cache_key is not None:
                cache_manager.set(
                    key=cache_key,
                    value=result,
                    ttl_seconds=cache_ttl,
                    tags=cache_tags or [],
                )

            return result

        return wrapper

    return decorator


def bulk_load_relationships(query: Query, *relationships) -> Query:
    """Helper to bulk load relationships and avoid N+1 problems.

    Args:
        query: SQLAlchemy Query object
        *relationships: Relationship attributes (not strings) or option objects

    Example:
        query = bulk_load_relationships(
            session.query(User),
            User.profile,
            User.orders
        )
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy.orm.attributes import InstrumentedAttribute

    for relationship in relationships:
        if isinstance(relationship, InstrumentedAttribute):
            # SQLAlchemy relationship attribute
            query = query.options(selectinload(relationship))
        elif hasattr(relationship, "_sa_class_manager"):
            # Another type of SQLAlchemy attribute
            query = query.options(selectinload(relationship))
        else:
            # Assume it's already an option object (joinedload, selectinload, etc.)
            query = query.options(relationship)

    return query
