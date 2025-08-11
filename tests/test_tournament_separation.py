"""
Test suite for tournament domain separation

Ensures backward compatibility during Phase 2 Sprint 1 refactoring.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

import pytest


def test_tournament_imports():
    """Test that Tournament can be imported from both old and new locations"""
    # Old import pattern (backward compatibility)
    from models import Tournament as OldImport

    # New modular import
    from models.tournament.models import Tournament as NewImport

    # They should be the same class
    assert OldImport is NewImport

    # Use one of the imports for the rest of the test
    Tournament = OldImport  # <-- AGGIUNGI QUESTA RIGA

    # Verify all attributes exist
    assert hasattr(Tournament, "name")
    assert hasattr(Tournament, "tournament_type")
    assert hasattr(Tournament, "without_x")
    assert hasattr(Tournament, "final_playoffs")
    assert hasattr(Tournament, "challenge_mode")
    assert hasattr(Tournament, "is_active")

    # Verify methods exist
    assert callable(Tournament.can_be_modified)
    assert callable(Tournament.can_be_deleted)
    assert callable(Tournament.get_status)
    assert callable(Tournament.get_status_badge_class)
    assert callable(Tournament.get_status_text)


def test_tournament_relationships():
    """Test that Tournament relationships are properly defined"""
    from models import Tournament

    # Check relationship definitions
    assert hasattr(Tournament, "provas")
    assert hasattr(Tournament, "directors")


def test_tournament_service_available():
    """Test that TournamentService is available"""
    from models.tournament.services import TournamentService

    assert callable(TournamentService.create_tournament)
    assert callable(TournamentService.get_active_tournaments)


def test_legacy_models_still_imports():
    """Test that other models still import from legacy_models"""
    from models import (
        Prova,
        Inscription,
        Match,
        Rack,
        MatchResult,
        Classification,
        Playoff,
        PlayerEncounter,
        RoundClassification,
        TrioMatch,
    )

    # Just verify they can be imported
    assert Prova.__name__ == "Prova"
    assert Match.__name__ == "Match"
    assert Classification.__name__ == "Classification"
