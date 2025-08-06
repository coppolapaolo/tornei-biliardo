"""
Test suite for classification domain separation

Ensures backward compatibility during Phase 2 Sprint 1 refactoring.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-06
"""

import pytest


def test_classification_imports():
    """Test that Classification can be imported from both old and new locations"""
    # Old import pattern
    from models import Classification as OldImport
    
    # New modular import
    from models.classification.models import Classification as NewImport
    
    # They should be the same class
    assert OldImport is NewImport
    
    # Use one import for testing
    Classification = OldImport
    
    # Verify attributes
    assert hasattr(Classification, 'tournament_id')
    assert hasattr(Classification, 'user_id')
    assert hasattr(Classification, 'position')
    assert hasattr(Classification, 'total_matches_won')
    assert hasattr(Classification, 'total_point_difference')
    assert hasattr(Classification, 'provas_played')


def test_round_classification_imports():
    """Test that RoundClassification can be imported from both locations"""
    from models import RoundClassification as OldImport
    from models.classification.models import RoundClassification as NewImport
    
    assert OldImport is NewImport
    
    # Use one import for testing
    RoundClassification = OldImport
    
    # Verify attributes
    assert hasattr(RoundClassification, 'prova_id')
    assert hasattr(RoundClassification, 'round_number')
    assert hasattr(RoundClassification, 'user_id')
    assert hasattr(RoundClassification, 'position')
    assert hasattr(RoundClassification, 'matches_won')
    assert hasattr(RoundClassification, 'rack_difference')
    
    # Verify static method
    assert callable(RoundClassification.calculate_classification_after_round)


def test_player_encounter_imports():
    """Test that PlayerEncounter can be imported from both locations"""
    from models import PlayerEncounter as OldImport
    from models.classification.models import PlayerEncounter as NewImport
    
    assert OldImport is NewImport
    
    # Use one import for testing
    PlayerEncounter = OldImport
    
    # Verify attributes
    assert hasattr(PlayerEncounter, 'prova_id')
    assert hasattr(PlayerEncounter, 'player1_id')
    assert hasattr(PlayerEncounter, 'player2_id')
    assert hasattr(PlayerEncounter, 'round_number')
    
    # Verify static methods
    assert callable(PlayerEncounter.have_played)
    assert callable(PlayerEncounter.record_encounter)


def test_classification_services():
    """Test that classification services are available"""
    from models.classification.services import (
        ClassificationService,
        RoundClassificationService,
        PlayerEncounterService
    )
    
    # ClassificationService methods
    assert callable(ClassificationService.update_tournament_classification)
    assert callable(ClassificationService.get_tournament_standings)
    assert callable(ClassificationService.get_player_ranking)
    
    # RoundClassificationService methods
    assert callable(RoundClassificationService.get_round_standings)
    assert callable(RoundClassificationService.get_player_progression)
    assert callable(RoundClassificationService.calculate_and_save_round_classification)
    
    # PlayerEncounterService methods
    assert callable(PlayerEncounterService.get_player_encounters)
    assert callable(PlayerEncounterService.get_available_opponents)
    assert callable(PlayerEncounterService.record_match_encounters)
    assert callable(PlayerEncounterService.get_encounter_matrix)


def test_relationships():
    """Test that relationships are properly defined"""
    from models import Classification, RoundClassification, PlayerEncounter
    
    # Classification relationships
    assert hasattr(Classification, 'tournament_id')
    assert hasattr(Classification, 'user_id')
    
    # RoundClassification relationships
    assert hasattr(RoundClassification, 'prova_id')
    assert hasattr(RoundClassification, 'user_id')
    
    # PlayerEncounter relationships
    assert hasattr(PlayerEncounter, 'prova_id')
    assert hasattr(PlayerEncounter, 'player1_id')
    assert hasattr(PlayerEncounter, 'player2_id')