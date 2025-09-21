#!/usr/bin/env python3
"""Advanced refactoring progress detector for tornei-biliardo project.

This script provides comprehensive analysis of refactoring progress across multiple
dimensions: transaction migration, service decomposition, architectural cleanup,
and test coverage. Features enhanced detection logic with precision filtering
and strategic categorization for systematic phase planning.

Key Features:
- Enhanced db.session.commit() detection with false positive filtering
- Architectural categorization (routes, models, utils, amalfi, other)
- Service decomposition tracking with size metrics
- Legacy amalfi/ migration progress monitoring
- Notification factory consolidation tracking
- Comprehensive test coverage analysis
- Strategic recommendations for next refactoring phases

Enhanced Detection Logic:
- Excludes comments, docstrings, and string literals for accuracy
- Categorizes files by architectural layer for targeted refactoring
- Provides detailed breakdown for phase planning and prioritization

Usage:
    python scripts/refactor_progress.py        # Generate full progress report
    python scripts/refactor_progress.py --help # Show usage information

The script supports the systematic refactoring methodology documented in
docs/refactoring/ and aligns with the Domain-Driven Design architecture
of this Flask-based pool tournament community platform.
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional


class RefactorProgressDetector:
    """Advanced detector for refactoring progress across the tornei-biliardo codebase.

    Provides comprehensive analysis of multiple refactoring dimensions with enhanced
    detection logic and strategic categorization. Supports the systematic refactoring
    methodology for this Flask-based pool tournament community platform.
    """

    def __init__(self):
        """Initialize detector with project root path resolution."""
        self.project_root = Path(__file__).parent.parent

    def detect_transaction_migration(self) -> Dict[str, Any]:
        """Detect remaining direct db.session.commit() calls across the codebase.

        Enhanced detection logic with precision filtering to exclude false positives
        from comments, docstrings, and string literals. Results are categorized
        by file type for systematic phase planning.

        Returns:
            Dict containing progress metrics, file breakdown, and categorized results
            for strategic refactoring planning.
        """
        files_with_commits = []
        total_commits = 0

        # Exclude non-production code from transaction migration analysis
        exclude_dirs = ["tests/", "venv/", "__pycache__/", ".git/", "scripts/"]

        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories to focus on production code
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                # Enhanced detection: count only actual commit calls, not references
                lines = content.split("\n")
                active_commits = 0
                for line in lines:
                    stripped_line = line.strip()
                    if "db.session.commit()" in line:
                        # FILTERING LOGIC: Exclude false positives to improve accuracy

                        # Skip single-line comments
                        if stripped_line.startswith("#"):
                            continue

                        # Skip multi-line string/docstring markers (simplified detection)
                        if stripped_line.startswith('"""') or stripped_line.startswith(
                            "'''"
                        ):
                            continue

                        # Skip string literals containing commit calls (documentation/examples)
                        if (
                            '"db.session.commit()"' in line
                            or "'db.session.commit()'" in line
                            or '"""db.session.commit()"""' in line
                            or "'''db.session.commit()'''" in line
                        ):
                            continue

                        # Count as active commit call requiring migration
                        active_commits += 1

                if active_commits > 0:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_commits.append((str(relative_path), active_commits))
                    total_commits += active_commits
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        # Sort by commit frequency for strategic prioritization (highest impact first)
        files_with_commits.sort(key=lambda x: x[1], reverse=True)

        baseline = 308  # From initial refactoring analysis baseline
        progress = max(0, (baseline - total_commits) / baseline * 100)

        # CATEGORIZATION SYSTEM: Group files by architectural layer for systematic phase planning
        # This categorization enables strategic refactoring by addressing similar patterns together
        categories = {
            "routes": [],  # Web layer - API endpoints and request handling
            "models": [],  # Domain layer - business logic and data services
            "utils": [],  # Infrastructure - shared utilities and helpers
            "amalfi": [],  # Legacy matchmaking engine requiring special migration
            "other": [],  # Miscellaneous files not fitting standard patterns
        }

        # Classify each file to enable phase-based refactoring strategy
        for file_path, count in files_with_commits:
            if file_path.startswith("routes/"):
                categories["routes"].append((file_path, count))
            elif file_path.startswith("models/"):
                categories["models"].append((file_path, count))
            elif file_path.startswith("utils/"):
                categories["utils"].append((file_path, count))
            elif file_path.startswith("amalfi/"):
                categories["amalfi"].append((file_path, count))
            else:
                categories["other"].append((file_path, count))

        return {
            "total_commits": total_commits,  # Current active commit calls requiring migration
            "baseline": baseline,  # Original count (308) from refactoring start
            "progress_percent": progress,  # Migration completion percentage
            "files_remaining": len(
                files_with_commits
            ),  # Number of files still needing migration
            "files_detail": files_with_commits[
                :10
            ],  # Top 10 highest-impact files for prioritization
            "all_files": files_with_commits,  # Complete list for comprehensive analysis
            "categories": categories,  # Architectural categorization for phase planning
        }

    def detect_service_size(
        self, service_path: str, baseline_lines: int
    ) -> Optional[Dict[str, Any]]:
        """Detect current service file size and calculate decomposition progress.

        Measures file size reduction from baseline to track service decomposition
        efforts. Part of Task 1.2 GaraService decomposition strategy.

        Args:
            service_path: Relative path to service file from project root
            baseline_lines: Original line count before decomposition

        Returns:
            Dictionary with size metrics and decomposition status, or None if file not found
        """
        path = self.project_root / service_path
        if not path.exists():
            return None

        try:
            lines = len(path.read_text(encoding="utf-8").splitlines())
            reduction_percent = max(0, (baseline_lines - lines) / baseline_lines * 100)

            return {
                "current_lines": lines,
                "baseline_lines": baseline_lines,
                "reduction_percent": reduction_percent,
                "target_lines": 500,
                "status": (
                    "completed"
                    if lines < 500
                    else "in_progress" if reduction_percent > 5 else "not_started"
                ),
            }
        except (UnicodeDecodeError, PermissionError, OSError):
            return None

    def detect_amalfi_imports(self) -> Dict[str, Any]:
        """Detect remaining direct imports from legacy amalfi/ directory.

        Tracks migration progress from legacy amalfi engine to unified matchmaking
        service. Part of architectural cleanup to eliminate legacy dependencies.

        Returns:
            Dictionary with import count, baseline, and progress metrics
        """
        files_with_amalfi_imports = []

        exclude_dirs = ["venv/", "__pycache__/", ".git/"]

        for py_file in self.project_root.rglob("*.py"):
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                if "from amalfi" in content or "import amalfi" in content:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_amalfi_imports.append(str(relative_path))
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        baseline = 13  # From initial analysis
        progress = max(0, (baseline - len(files_with_amalfi_imports)) / baseline * 100)

        return {
            "files_with_direct_imports": len(files_with_amalfi_imports),
            "baseline": baseline,
            "progress_percent": progress,
            "files_list": files_with_amalfi_imports,
        }

    def detect_duplicate_notifications(self) -> Dict[str, Any]:
        """Detect duplicate notification creation patterns for factory consolidation.

        Identifies opportunities to replace scattered NotificationService.create_notification
        calls with centralized factory methods for better maintainability.

        Returns:
            Dictionary with call count, file distribution, and progress metrics
        """
        files_with_notifications = []
        total_calls = 0

        exclude_dirs = ["tests/", "venv/", "scripts/", "__pycache__/", ".git/"]

        for py_file in self.project_root.rglob("*.py"):
            if any(exclude in str(py_file) for exclude in exclude_dirs):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                calls = content.count("NotificationService.create_notification")
                if calls > 0:
                    relative_path = py_file.relative_to(self.project_root)
                    files_with_notifications.append((str(relative_path), calls))
                    total_calls += calls
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

        baseline = 27  # From initial analysis
        progress = max(0, (baseline - total_calls) / baseline * 100)

        return {
            "total_calls": total_calls,
            "baseline": baseline,
            "progress_percent": progress,
            "files_with_calls": len(files_with_notifications),
            "files_detail": files_with_notifications,
        }

    def count_refactor_tests(self) -> Dict[str, int]:
        """Count refactoring tests by category for quality assurance tracking.

        Provides metrics on test coverage for refactoring efforts, ensuring
        proper validation at each phase of the systematic refactoring process.

        Returns:
            Dictionary with counts for each test category (characterization, TDD, etc.)
        """
        refactor_test_dir = self.project_root / "tests" / "new" / "refactor"

        counts = {"characterization": 0, "tdd": 0, "integration": 0, "milestones": 0}

        if not refactor_test_dir.exists():
            return counts

        # Count characterization tests
        char_dir = refactor_test_dir / "characterization"
        if char_dir.exists():
            counts["characterization"] = len([f for f in char_dir.glob("test_*.py")])

        # Count TDD tests
        tdd_dir = refactor_test_dir / "tdd"
        if tdd_dir.exists():
            counts["tdd"] = len([f for f in tdd_dir.glob("test_*_tdd.py")])

        # Count integration tests
        int_dir = refactor_test_dir / "integration"
        if int_dir.exists():
            counts["integration"] = len([f for f in int_dir.glob("test_*.py")])

        # Count milestone tests
        milestone_file = refactor_test_dir / "test_progress_milestones.py"
        if milestone_file.exists():
            counts["milestones"] = 1

        return counts

    def generate_summary_status(self) -> str:
        """Generate overall refactoring phase status based on progress metrics.

        Combines multiple refactoring dimensions (transaction migration, service
        decomposition, amalfi migration) to determine current phase and readiness
        for next steps in the systematic refactoring plan.

        Returns:
            Formatted status string with phase indicator and completion status
        """
        # Check transaction migration
        tx_data = self.detect_transaction_migration()
        tx_complete = tx_data["total_commits"] <= 10

        # Check service decomposition (Task 1.2)
        # Note: "Gara" is Italian for "competition" - core domain service for tournament management
        gara_data = self.detect_service_size("models/competition/services.py", 1695)
        gara_complete = gara_data and gara_data["current_lines"] < 500

        user_data = self.detect_service_size("models/user/services.py", 1449)
        user_complete = user_data and user_data["current_lines"] < 500

        # Check amalfi migration
        amalfi_data = self.detect_amalfi_imports()
        amalfi_complete = amalfi_data["files_with_direct_imports"] == 0

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
        """Generate comprehensive refactoring progress report.

        Produces detailed analysis including transaction migration progress,
        service decomposition metrics, architectural categorization, and
        strategic recommendations for next phases.
        """
        print("🔄 REFACTOR PROGRESS REPORT")
        print("=" * 50)
        print(f"📊 Overall Status: {self.generate_summary_status()}")
        print()

        # Transaction migration
        tx_data = self.detect_transaction_migration()
        print(f"📊 Transaction Migration: {tx_data['progress_percent']:.1f}%")
        print(f"   Direct commits: {tx_data['total_commits']}/{tx_data['baseline']}")
        print(f"   Files remaining: {tx_data['files_remaining']}")

        # ENHANCED REPORTING: Show categorized breakdown for strategic phase planning
        if "categories" in tx_data:
            categories = tx_data["categories"]
            print("   Breakdown by architectural layer:")
            for category, files in categories.items():
                if files:
                    total_commits_in_category = sum(count for _, count in files)
                    print(
                        f"     {category}: {len(files)} files, {total_commits_in_category} commits"
                    )
                    # Show top 3 files per category for targeted refactoring
                    for file_path, count in files[:3]:
                        print(f"       - {file_path}: {count}")

        if tx_data["files_detail"]:
            print("   Top files overall:")
            for file, count in tx_data["files_detail"][:5]:
                print(f"     - {file}: {count} commits")
        print()

        # GaraService size (Competition Service decomposition tracking)
        gara_data = self.detect_service_size("models/competition/services.py", 1695)
        if gara_data:
            print(
                f"📊 GaraService Decomposition: {gara_data['reduction_percent']:.1f}%"
            )
            print(f"   Current: {gara_data['current_lines']} lines")
            print(f"   Target: {gara_data['target_lines']} lines")
            print(f"   Status: {gara_data['status']}")
            print()

        # UserService size
        user_data = self.detect_service_size("models/user/services.py", 1449)
        if user_data:
            print(
                f"📊 UserService Decomposition: {user_data['reduction_percent']:.1f}%"
            )
            print(f"   Current: {user_data['current_lines']} lines")
            print(f"   Target: {user_data['target_lines']} lines")
            print(f"   Status: {user_data['status']}")
            print()

        # Amalfi migration
        amalfi_data = self.detect_amalfi_imports()
        print(f"📊 Amalfi Directory Migration: {amalfi_data['progress_percent']:.1f}%")
        print(
            f"   Direct imports remaining: {amalfi_data['files_with_direct_imports']}/{amalfi_data['baseline']}"
        )
        if amalfi_data["files_list"]:
            print("   Files with direct imports:")
            for file in amalfi_data["files_list"][:5]:
                print(f"     - {file}")
        print()

        # Notification factory
        notif_data = self.detect_duplicate_notifications()
        print(f"📊 Notification Factory: {notif_data['progress_percent']:.1f}%")
        print(
            f"   Duplicate calls: {notif_data['total_calls']}/{notif_data['baseline']}"
        )
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
        if tx_data["total_commits"] > 200:
            print("   - Start with transaction migration (high impact)")
        if gara_data and gara_data["current_lines"] > 1000:
            print("   - Begin GaraService decomposition")
        if test_counts["characterization"] == 0:
            print("   - Create characterization tests before refactoring")
        if test_counts["tdd"] == 0:
            print("   - Start TDD for new service implementations")


def main():
    """Main entry point for the script."""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        return

    detector = RefactorProgressDetector()
    detector.generate_report()


if __name__ == "__main__":
    main()
