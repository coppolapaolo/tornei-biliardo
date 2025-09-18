"""
Refactor test package - Test-First Refactoring with TDD

This package contains tests for the systematic refactoring of the billiards platform
following the Test-First approach combined with TDD principles.

Structure:
- characterization/: Tests that document current behavior before refactoring
- tdd/: Test-Driven Development tests for new implementations
- integration/: Tests that verify refactored components work together
- test_progress_milestones.py: Tests that fail when refactoring milestones are reached

Following Red-Green-Refactor cycle:
1. RED: Write failing tests (characterization + TDD)
2. GREEN: Implement minimal code to pass tests
3. REFACTOR: Improve code while keeping tests green
"""
