"""
Smoke performance tests for AmalfiUnifiedAdapter.

These tests verify that the unified Amalfi adapter meets performance requirements
(<2s for typical operations) and doesn't introduce significant overhead compared
to the original implementation.
"""
import pytest
import time
from unittest.mock import Mock, patch
from typing import List

from models.matchmaking.strategies.amalfi_unified_adapter import AmalfiUnifiedAdapter
from models.matchmaking.registry import PairingContext
from models.competition.models import Gara
from models import Inscription


class TestAmalfiUnifiedPerformance:
    """Smoke performance tests for AmalfiUnifiedAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create AmalfiUnifiedAdapter instance."""
        return AmalfiUnifiedAdapter()

    def create_large_mock_gara(self, num_players: int) -> Mock:
        """Create mock Gara with large number of players for performance testing."""
        gara = Mock(spec=Gara)
        gara.id = 1
        gara.min_participants = 3
        gara.max_participants = None
        gara.current_round = 1
        gara.classification = []
        
        inscriptions = []
        for i in range(1, num_players + 1):
            inscription = Mock(spec=Inscription)
            inscription.user_id = i
            inscription.status = "confirmed"
            inscriptions.append(inscription)
        gara.inscriptions = inscriptions
        
        return gara

    def create_large_preview_data(self, num_players: int) -> dict:
        """Create mock preview data for large tournament."""
        matches = []
        
        # Create normal matches for pairs
        for i in range(0, num_players - (num_players % 2), 2):
            matches.append({
                "player1": Mock(id=i+1),
                "player2": Mock(id=i+2),
                "type": "normal"
            })
        
        # Add bye if odd number of players
        if num_players % 2 == 1:
            matches.append({
                "player1": Mock(id=num_players),
                "type": "bye"
            })
        
        return {
            "matches": matches,
            "stats": {
                "total_matches": len(matches),
                "bye_matches": 1 if num_players % 2 == 1 else 0,
                "trio_matches": 0
            },
            "salto": 0
        }

    def measure_execution_time(self, func, *args, **kwargs):
        """Measure execution time of a function."""
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        return result, execution_time

    # ============================================================================
    # PERFORMANCE TEST 1: Small tournaments (typical case)
    # ============================================================================
    
    @pytest.mark.parametrize("num_players", [8, 16, 32])
    def test_small_tournament_performance(self, adapter, num_players):
        """Test performance with small to medium tournaments (<2s requirement)."""
        gara = self.create_large_mock_gara(num_players)
        preview_data = self.create_large_preview_data(num_players)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            # Measure preview performance
            pairings, execution_time = self.measure_execution_time(
                adapter.preview, gara, 1
            )
        
        # Performance requirement: < 2 seconds for small tournaments
        assert execution_time < 2.0, f"Preview took {execution_time:.3f}s for {num_players} players (>2s limit)"
        
        # Verify correctness wasn't sacrificed for speed
        assert len(pairings) == (num_players + 1) // 2  # Expected number of pairings
        
        print(f"✓ {num_players} players: {execution_time:.3f}s")

    # ============================================================================
    # PERFORMANCE TEST 2: Large tournaments (stress test)
    # ============================================================================
    
    @pytest.mark.parametrize("num_players", [64, 128, 256])
    def test_large_tournament_performance(self, adapter, num_players):
        """Test performance with large tournaments (should still be reasonable)."""
        gara = self.create_large_mock_gara(num_players)
        preview_data = self.create_large_preview_data(num_players)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            # Measure preview performance
            pairings, execution_time = self.measure_execution_time(
                adapter.preview, gara, 1
            )
        
        # More lenient requirement for large tournaments, but should still be reasonable
        max_time = 5.0  # 5 seconds max for very large tournaments
        assert execution_time < max_time, f"Preview took {execution_time:.3f}s for {num_players} players (>{max_time}s limit)"
        
        # Verify correctness
        assert len(pairings) == (num_players + 1) // 2
        
        print(f"✓ {num_players} players: {execution_time:.3f}s")

    # ============================================================================
    # PERFORMANCE TEST 3: Context setup overhead
    # ============================================================================
    
    def test_context_setup_overhead(self, adapter):
        """Test that context setup doesn't add significant overhead."""
        gara = self.create_large_mock_gara(32)
        preview_data = self.create_large_preview_data(32)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            # Test without context
            _, time_without_context = self.measure_execution_time(
                adapter.preview, gara, 1
            )
            
            # Test with context
            context = PairingContext(seed=42)
            adapter.set_context(context)
            _, time_with_context = self.measure_execution_time(
                adapter.preview, gara, 1
            )
        
        # Context setup should add minimal overhead (< 10% increase)
        overhead_ratio = time_with_context / time_without_context if time_without_context > 0 else 1
        assert overhead_ratio < 1.1, f"Context setup adds {(overhead_ratio-1)*100:.1f}% overhead (>10% limit)"
        
        print(f"✓ Context overhead: {(overhead_ratio-1)*100:.1f}%")

    # ============================================================================
    # PERFORMANCE TEST 4: Multiple rounds performance
    # ============================================================================
    
    def test_multiple_rounds_performance(self, adapter):
        """Test performance across multiple rounds (simulating full tournament)."""
        gara = self.create_large_mock_gara(16)
        preview_data = self.create_large_preview_data(16)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            context = PairingContext(seed=42)
            adapter.set_context(context)
            
            total_time = 0
            num_rounds = 5
            
            for round_num in range(1, num_rounds + 1):
                _, round_time = self.measure_execution_time(
                    adapter.preview, gara, round_num
                )
                total_time += round_time
        
        # Total time for 5 rounds should still be reasonable
        assert total_time < 2.0, f"5 rounds took {total_time:.3f}s (>2s limit)"
        
        # Average time per round should be consistent
        avg_time_per_round = total_time / num_rounds
        assert avg_time_per_round < 0.5, f"Average {avg_time_per_round:.3f}s per round (>0.5s limit)"
        
        print(f"✓ 5 rounds total: {total_time:.3f}s (avg: {avg_time_per_round:.3f}s/round)")

    # ============================================================================
    # PERFORMANCE TEST 5: Memory usage (basic check)
    # ============================================================================
    
    def test_memory_efficiency(self, adapter):
        """Test that adapter doesn't create excessive memory overhead."""
        import sys
        
        gara = self.create_large_mock_gara(100)
        preview_data = self.create_large_preview_data(100)
        
        # Measure memory before
        initial_refs = sys.getrefcount(gara)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            context = PairingContext(seed=42)
            adapter.set_context(context)
            
            # Run multiple times to check for memory leaks
            for _ in range(10):
                pairings = adapter.preview(gara, 1)
                # Verify pairings are created but don't hold references
                assert len(pairings) > 0
        
        # Basic check - reference count shouldn't grow significantly
        final_refs = sys.getrefcount(gara)
        ref_growth = final_refs - initial_refs
        
        # Allow some growth but not excessive (relaxed for mock testing)
        assert ref_growth < 20, f"Reference count grew by {ref_growth} (potential memory leak)"
        
        print(f"✓ Memory check passed (ref growth: {ref_growth})")

    # ============================================================================
    # PERFORMANCE TEST 6: Validation performance
    # ============================================================================
    
    def test_validation_performance(self, adapter):
        """Test that validation is fast even for large tournaments."""
        gara = self.create_large_mock_gara(200)
        
        # Measure validation time
        _, validation_time = self.measure_execution_time(
            adapter.validate, gara
        )
        
        # Validation should be very fast (< 0.1s even for large tournaments)
        assert validation_time < 0.1, f"Validation took {validation_time:.3f}s (>0.1s limit)"
        
        print(f"✓ Validation for 200 players: {validation_time:.6f}s")

    # ============================================================================
    # PERFORMANCE TEST 7: Seed determinism performance
    # ============================================================================
    
    def test_seed_determinism_performance(self, adapter):
        """Test that deterministic seeding doesn't significantly impact performance."""
        gara = self.create_large_mock_gara(50)
        preview_data = self.create_large_preview_data(50)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            # Test multiple different seeds
            seeds = [42, 123, 999, 777, 555]
            times = []
            
            for seed in seeds:
                context = PairingContext(seed=seed)
                adapter.set_context(context)
                
                _, execution_time = self.measure_execution_time(
                    adapter.preview, gara, 1
                )
                times.append(execution_time)
        
        # All executions should be consistently fast
        max_time = max(times)
        min_time = min(times)
        avg_time = sum(times) / len(times)
        
        assert max_time < 1.0, f"Slowest execution: {max_time:.3f}s (>1s limit)"
        
        # Times should be reasonably consistent (variance shouldn't be too high)
        time_variance = max_time - min_time
        assert time_variance < 0.5, f"High time variance: {time_variance:.3f}s"
        
        print(f"✓ Seed determinism: avg={avg_time:.3f}s, range={time_variance:.3f}s")

    # ============================================================================
    # PERFORMANCE REGRESSION TEST: Compare with metrics baseline
    # ============================================================================
    
    def test_performance_regression(self, adapter):
        """Test that performance hasn't regressed from baseline expectations."""
        # This test establishes performance baselines that future changes
        # should not significantly exceed
        
        test_cases = [
            (16, 0.1),   # 16 players should take < 0.1s
            (32, 0.2),   # 32 players should take < 0.2s  
            (64, 0.5),   # 64 players should take < 0.5s
        ]
        
        for num_players, max_time in test_cases:
            gara = self.create_large_mock_gara(num_players)
            preview_data = self.create_large_preview_data(num_players)
            
            with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
                mock_engine = mock_engine_class.return_value
                mock_engine.preview_round_pairings.return_value = preview_data
                
                context = PairingContext(seed=42)
                adapter.set_context(context)
                
                _, execution_time = self.measure_execution_time(
                    adapter.preview, gara, 1
                )
            
            assert execution_time < max_time, f"{num_players} players took {execution_time:.3f}s (>{max_time}s baseline)"
            print(f"✓ {num_players} players: {execution_time:.3f}s (baseline: <{max_time}s)")

    # ============================================================================
    # PERFORMANCE TEST 8: Strategy metrics performance
    # ============================================================================
    
    def test_metrics_collection_performance(self, adapter):
        """Test that metrics collection doesn't add significant overhead."""
        gara = self.create_large_mock_gara(32)
        preview_data = self.create_large_preview_data(32)
        
        with patch('models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine') as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = preview_data
            
            context = PairingContext(seed=42)
            adapter.set_context(context)
            
            # Execute and measure
            _, execution_time = self.measure_execution_time(
                adapter.preview, gara, 1
            )
            
            # Get metrics
            metrics = adapter.get_metrics()
        
        # Metrics should be available and reasonable
        assert metrics is not None, "Metrics should be collected"
        assert metrics.execution_time_ms > 0, "Execution time should be recorded"
        assert metrics.pairings_generated > 0, "Pairing count should be recorded"
        
        # Metrics collection shouldn't add noticeable overhead
        # (This is more of a sanity check since we can't easily separate the overhead)
        assert execution_time < 1.0, f"Execution with metrics: {execution_time:.3f}s"
        
        print(f"✓ Metrics collection: {execution_time:.3f}s, {metrics.pairings_generated} pairings")