#!/usr/bin/env python3
"""Auto-detect refactoring progress from codebase state.

This script analyzes the codebase to automatically detect progress
in the refactoring efforts by counting various metrics and patterns.

Usage:
    python scripts/refactor_progress.py
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional


class RefactorProgressDetector:
    """Detector for refactoring progress across the codebase."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent

    def detect_transaction_migration(self) -> Dict[str, Any]:
        """Rileva quante chiamate dirette a db.session.commit() rimangono."""
        files_with_commits = []
        total_commits = 0

        # Exclude directories from analysis
        exclude_dirs = ['tests/', 'venv/', 'scripts/', '__pycache__/', '.git/']

        for py_file in self.project_root.rglob('*.py'):
            # Skip excluded directories
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                commits = content.count('db.session.commit()')
                if commits > 0:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_commits.append((str(relative_path), commits))
                    total_commits += commits
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        # Sort by number of commits (highest first)
        files_with_commits.sort(key=lambda x: x[1], reverse=True)

        baseline = 308  # From initial analysis
        progress = max(0, (baseline - total_commits) / baseline * 100)

        return {
            'total_commits': total_commits,
            'baseline': baseline,
            'progress_percent': progress,
            'files_remaining': len(files_with_commits),
            'files_detail': files_with_commits[:10]  # Top 10
        }

    def detect_service_size(self, service_path: str, baseline_lines: int) -> Optional[Dict[str, Any]]:
        """Rileva dimensione attuale di un service."""
        path = self.project_root / service_path
        if not path.exists():
            return None

        try:
            lines = len(path.read_text(encoding='utf-8').splitlines())
            reduction_percent = max(0, (baseline_lines - lines) / baseline_lines * 100)

            return {
                'current_lines': lines,
                'baseline_lines': baseline_lines,
                'reduction_percent': reduction_percent,
                'target_lines': 500,
                'status': 'completed' if lines < 500 else 'in_progress' if reduction_percent > 5 else 'not_started'
            }
        except (UnicodeDecodeError, PermissionError, OSError):
            return None

    def detect_amalfi_imports(self) -> Dict[str, Any]:
        """Rileva quanti file importano ancora da amalfi/ direttamente."""
        files_with_amalfi_imports = []

        exclude_dirs = ['venv/', '__pycache__/', '.git/']

        for py_file in self.project_root.rglob('*.py'):
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                if 'from amalfi' in content or 'import amalfi' in content:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_amalfi_imports.append(str(relative_path))
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        baseline = 13  # From initial analysis
        progress = max(0, (baseline - len(files_with_amalfi_imports)) / baseline * 100)

        return {
            'files_with_direct_imports': len(files_with_amalfi_imports),
            'baseline': baseline,
            'progress_percent': progress,
            'files_list': files_with_amalfi_imports
        }

    def detect_duplicate_notifications(self) -> Dict[str, Any]:
        """Rileva pattern duplicati per NotificationService.create_notification."""
        files_with_notifications = []
        total_calls = 0

        exclude_dirs = ['tests/', 'venv/', 'scripts/', '__pycache__/', '.git/']

        for py_file in self.project_root.rglob('*.py'):
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                calls = content.count('NotificationService.create_notification')
                if calls > 0:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_notifications.append((str(relative_path), calls))
                    total_calls += calls
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        baseline = 27  # From initial analysis
        progress = max(0, (baseline - total_calls) / baseline * 100)

        return {
            'total_calls': total_calls,
            'baseline': baseline,
            'progress_percent': progress,
            'files_with_calls': len(files_with_notifications),
            'files_detail': files_with_notifications
        }

    def count_refactor_tests(self) -> Dict[str, int]:
        """Conta i test di refactoring per categoria."""
        refactor_test_dir = self.project_root / 'tests' / 'new' / 'refactor'

        counts = {
            'characterization': 0,
            'tdd': 0,
            'integration': 0,
            'milestones': 0
        }

        if not refactor_test_dir.exists():
            return counts

        # Count characterization tests
        char_dir = refactor_test_dir / 'characterization'
        if char_dir.exists():
            counts['characterization'] = len([f for f in char_dir.glob('test_*.py')])

        # Count TDD tests
        tdd_dir = refactor_test_dir / 'tdd'
        if tdd_dir.exists():
            counts['tdd'] = len([f for f in tdd_dir.glob('test_*_tdd.py')])

        # Count integration tests
        int_dir = refactor_test_dir / 'integration'
        if int_dir.exists():
            counts['integration'] = len([f for f in int_dir.glob('test_*.py')])

        # Count milestone tests
        milestone_file = refactor_test_dir / 'test_progress_milestones.py'
        if milestone_file.exists():
            counts['milestones'] = 1

        return counts

    def generate_summary_status(self) -> str:
        """Genera status summary basato sui progressi."""
        # Check transaction migration
        tx_data = self.detect_transaction_migration()
        tx_complete = tx_data['total_commits'] <= 10

        # Check service decomposition
        gara_data = self.detect_service_size('models/competition/services.py', 1695)
        gara_complete = gara_data and gara_data['current_lines'] < 500

        user_data = self.detect_service_size('models/user/services.py', 1449)
        user_complete = user_data and user_data['current_lines'] < 500

        # Check amalfi migration
        amalfi_data = self.detect_amalfi_imports()
        amalfi_complete = amalfi_data['files_with_direct_imports'] == 0

        # Determine phase
        if tx_complete and gara_complete and user_complete:
            if amalfi_complete:
                return "🟢 Phase 3 - Optimization Complete"
            else:
                return "🟡 Phase 3 - Optimization In Progress"
        elif tx_complete or gara_complete or user_complete:
            return "🟡 Phase 1 - Stabilization In Progress"
        else:
            return "🔴 Phase 1 - Stabilization Starting"

    def generate_report(self) -> None:
        """Genera report completo di progresso."""
        print("🔄 REFACTOR PROGRESS REPORT")
        print("=" * 50)
        print(f"📊 Overall Status: {self.generate_summary_status()}")
        print()

        # Transaction migration
        tx_data = self.detect_transaction_migration()
        print(f"📊 Transaction Migration: {tx_data['progress_percent']:.1f}%")
        print(f"   Direct commits: {tx_data['total_commits']}/{tx_data['baseline']}")
        print(f"   Files remaining: {tx_data['files_remaining']}")
        if tx_data['files_detail']:
            print("   Top files:")
            for file, count in tx_data['files_detail'][:5]:
                print(f"     - {file}: {count} commits")
        print()

        # GaraService size
        gara_data = self.detect_service_size('models/competition/services.py', 1695)
        if gara_data:
            print(f"📊 GaraService Decomposition: {gara_data['reduction_percent']:.1f}%")
            print(f"   Current: {gara_data['current_lines']} lines")
            print(f"   Target: {gara_data['target_lines']} lines")
            print(f"   Status: {gara_data['status']}")
            print()

        # UserService size
        user_data = self.detect_service_size('models/user/services.py', 1449)
        if user_data:
            print(f"📊 UserService Decomposition: {user_data['reduction_percent']:.1f}%")
            print(f"   Current: {user_data['current_lines']} lines")
            print(f"   Target: {user_data['target_lines']} lines")
            print(f"   Status: {user_data['status']}")
            print()

        # Amalfi migration
        amalfi_data = self.detect_amalfi_imports()
        print(f"📊 Amalfi Directory Migration: {amalfi_data['progress_percent']:.1f}%")
        print(f"   Direct imports remaining: {amalfi_data['files_with_direct_imports']}/{amalfi_data['baseline']}")
        if amalfi_data['files_list']:
            print("   Files with direct imports:")
            for file in amalfi_data['files_list'][:5]:
                print(f"     - {file}")
        print()

        # Notification factory
        notif_data = self.detect_duplicate_notifications()
        print(f"📊 Notification Factory: {notif_data['progress_percent']:.1f}%")
        print(f"   Duplicate calls: {notif_data['total_calls']}/{notif_data['baseline']}")
        print(f"   Files with calls: {notif_data['files_with_calls']}")
        print()

        # Test coverage
        test_counts = self.count_refactor_tests()
        print("🧪 Test Status:")
        print(f"   Characterization tests: {test_counts['characterization']}")
        print(f"   TDD tests: {test_counts['tdd']}")
        print(f"   Integration tests: {test_counts['integration']}")
        print(f"   Milestone tests: {test_counts['milestones']}")
        print()

        # Recommendations
        print("💡 Recommendations:")
        if tx_data['total_commits'] > 200:
            print("   - Start with transaction migration (high impact)")
        if gara_data and gara_data['current_lines'] > 1000:
            print("   - Begin GaraService decomposition")
        if test_counts['characterization'] == 0:
            print("   - Create characterization tests before refactoring")
        if test_counts['tdd'] == 0:
            print("   - Start TDD for new service implementations")


def main():
    """Main entry point for the script."""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print(__doc__)
        return

    detector = RefactorProgressDetector()
    detector.generate_report()


if __name__ == '__main__':
    main()