"""Test che falliscono quando milestone di refactoring sono raggiunte.

Questi test fungono da alert automatici che notificano quando specifici
obiettivi di refactoring sono stati raggiunti. Falliscono intenzionalmente
per attirare l'attenzione dello sviluppatore.

Usage:
    pytest tests/new/refactor/test_progress_milestones.py -v
"""

import pytest
from pathlib import Path
import sys

# Add scripts directory to path for imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

try:
    from refactor_progress import RefactorProgressDetector
except ImportError:
    RefactorProgressDetector = None


@pytest.mark.skipif(RefactorProgressDetector is None, reason="RefactorProgressDetector not available")
class TestRefactorMilestones:
    """Test che fungono da milestone per il refactoring."""

    def test_transaction_migration_complete_milestone(self):
        """MILESTONE: Fallisce quando migration transazioni è completa.

        Target: Ridurre chiamate dirette a db.session.commit() da 201 a <10.
        """
        detector = RefactorProgressDetector()
        data = detector.detect_transaction_migration()

        if data['total_commits'] <= 10:
            pytest.fail(
                f"🎉 MILESTONE RAGGIUNTO! "
                f"Transaction migration completa: {data['total_commits']} commits rimanenti "
                f"(era {data['baseline']}). "
                f"Aggiornare REFACTOR_PROGRESS.md e rimuovere questo test."
            )
        else:
            # This is expected during refactoring - test should pass
            print(f"Transaction migration progress: {data['progress_percent']:.1f}% "
                  f"({data['total_commits']}/{data['baseline']} remaining)")

    def test_gara_service_decomposition_milestone(self):
        """MILESTONE: Fallisce quando GaraService è sotto 500 righe.

        Target: Ridurre GaraService da 1766 righe a <500.
        """
        detector = RefactorProgressDetector()
        data = detector.detect_service_size('models/competition/services.py', 1695)

        if data and data['current_lines'] < 500:
            pytest.fail(
                f"🎉 MILESTONE RAGGIUNTO! "
                f"GaraService decomposition completa: {data['current_lines']} righe "
                f"(era {data['baseline_lines']}). "
                f"Aggiornare REFACTOR_PROGRESS.md e rimuovere questo test."
            )
        elif data:
            print(f"GaraService decomposition progress: {data['reduction_percent']:.1f}% "
                  f"({data['current_lines']}/{data['target_lines']} lines)")

    def test_user_service_decomposition_milestone(self):
        """MILESTONE: Fallisce quando UserService è sotto 500 righe.

        Target: Ridurre UserService da 1449 righe a <500.
        """
        detector = RefactorProgressDetector()
        data = detector.detect_service_size('models/user/services.py', 1449)

        if data and data['current_lines'] < 500:
            pytest.fail(
                f"🎉 MILESTONE RAGGIUNTO! "
                f"UserService decomposition completa: {data['current_lines']} righe "
                f"(era {data['baseline_lines']}). "
                f"Aggiornare REFACTOR_PROGRESS.md e rimuovere questo test."
            )
        elif data:
            print(f"UserService decomposition progress: {data['reduction_percent']:.1f}% "
                  f"({data['current_lines']}/{data['target_lines']} lines)")

    def test_amalfi_migration_milestone(self):
        """MILESTONE: Fallisce quando migration amalfi è completa.

        Target: Ridurre import diretti da amalfi/ da 15 file a 0.
        """
        detector = RefactorProgressDetector()
        data = detector.detect_amalfi_imports()

        if data['files_with_direct_imports'] == 0:
            pytest.fail(
                f"🎉 MILESTONE RAGGIUNTO! "
                f"Amalfi directory migration completa: 0 import diretti rimanenti "
                f"(erano {data['baseline']}). "
                f"Aggiornare REFACTOR_PROGRESS.md e rimuovere questo test."
            )
        else:
            print(f"Amalfi migration progress: {data['progress_percent']:.1f}% "
                  f"({data['files_with_direct_imports']}/{data['baseline']} files remaining)")

    def test_notification_factory_milestone(self):
        """MILESTONE: Fallisce quando consolidamento notifiche è completo.

        Target: Ridurre pattern duplicati da 17 a <5.
        """
        detector = RefactorProgressDetector()
        data = detector.detect_duplicate_notifications()

        if data['total_calls'] < 5:
            pytest.fail(
                f"🎉 MILESTONE RAGGIUNTO! "
                f"Notification factory completo: {data['total_calls']} pattern duplicati rimanenti "
                f"(erano {data['baseline']}). "
                f"Aggiornare REFACTOR_PROGRESS.md e rimuovere questo test."
            )
        else:
            print(f"Notification factory progress: {data['progress_percent']:.1f}% "
                  f"({data['total_calls']}/{data['baseline']} duplicates remaining)")

    def test_phase_1_completion_milestone(self):
        """MILESTONE: Fallisce quando Phase 1 (Stabilizzazione Core) è completa.

        Phase 1 è completa quando:
        - Transaction migration < 10 commits
        - GaraService < 500 lines
        - UserService < 500 lines
        """
        detector = RefactorProgressDetector()

        tx_data = detector.detect_transaction_migration()
        gara_data = detector.detect_service_size('models/competition/services.py', 1695)
        user_data = detector.detect_service_size('models/user/services.py', 1449)

        tx_complete = tx_data['total_commits'] <= 10
        gara_complete = gara_data and gara_data['current_lines'] < 500
        user_complete = user_data and user_data['current_lines'] < 500

        if tx_complete and gara_complete and user_complete:
            pytest.fail(
                f"🎉 FASE 1 COMPLETATA! "
                f"Stabilizzazione Core completa: "
                f"Transactions: {tx_data['total_commits']} commits, "
                f"GaraService: {gara_data['current_lines']} lines, "
                f"UserService: {user_data['current_lines']} lines. "
                f"Procedere alla Fase 2 (Disaccoppiamento Domini)."
            )
        else:
            completed_count = sum([tx_complete, gara_complete, user_complete])
            print(f"Phase 1 progress: {completed_count}/3 tasks completed")

    def test_comprehensive_test_coverage_milestone(self):
        """MILESTONE: Fallisce quando coverage dei test di refactoring è adeguato.

        Target: Almeno 5 characterization tests, 3 TDD tests, 2 integration tests.
        """
        detector = RefactorProgressDetector()
        test_counts = detector.count_refactor_tests()

        adequate_coverage = (
            test_counts['characterization'] >= 5 and
            test_counts['tdd'] >= 3 and
            test_counts['integration'] >= 2
        )

        if adequate_coverage:
            pytest.fail(
                f"🎉 TEST COVERAGE MILESTONE! "
                f"Adequate test coverage achieved: "
                f"{test_counts['characterization']} characterization, "
                f"{test_counts['tdd']} TDD, "
                f"{test_counts['integration']} integration tests. "
                f"Consider adding more specific tests as needed."
            )
        else:
            total_tests = sum(test_counts.values()) - test_counts['milestones']
            print(f"Test coverage progress: {total_tests} total refactor tests")


class TestRefactorProgressBaseline:
    """Test che verificano le baseline metrics siano corrette."""

    def test_baseline_metrics_are_reasonable(self):
        """Verifica che le metriche baseline siano nell'intervallo atteso."""
        if RefactorProgressDetector is None:
            pytest.skip("RefactorProgressDetector not available")

        detector = RefactorProgressDetector()

        # Transaction migration baseline should be substantial
        tx_data = detector.detect_transaction_migration()
        assert tx_data['total_commits'] >= 50, "Transaction baseline seems too low"
        assert tx_data['total_commits'] <= 500, "Transaction baseline seems too high"

        # Service sizes should be substantial
        gara_data = detector.detect_service_size('models/competition/services.py', 1695)
        if gara_data:
            assert gara_data['current_lines'] >= 1000, "GaraService baseline seems too low"

        user_data = detector.detect_service_size('models/user/services.py', 1449)
        if user_data:
            assert user_data['current_lines'] >= 800, "UserService baseline seems too low"

    def test_progress_detection_is_working(self):
        """Verifica che il sistema di detection progress sia funzionante."""
        if RefactorProgressDetector is None:
            pytest.skip("RefactorProgressDetector not available")

        detector = RefactorProgressDetector()

        # Should be able to detect various metrics
        tx_data = detector.detect_transaction_migration()
        assert 'total_commits' in tx_data
        assert 'progress_percent' in tx_data
        assert isinstance(tx_data['progress_percent'], (int, float))

        amalfi_data = detector.detect_amalfi_imports()
        assert 'files_with_direct_imports' in amalfi_data
        assert isinstance(amalfi_data['files_with_direct_imports'], int)

        test_counts = detector.count_refactor_tests()
        assert isinstance(test_counts, dict)
        assert 'characterization' in test_counts