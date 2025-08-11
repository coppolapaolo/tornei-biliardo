"""
Test suite for match domain separation

Ensures backward compatibility during Phase 2 Sprint 1 refactoring.

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""


def test_match_imports():
    """Test that Match can be imported from both old and new locations"""
    # Old import pattern
    from models import Match as OldImport

    # New modular import
    from models.match.models import Match as NewImport

    # They should be the same class
    assert OldImport is NewImport

    # Use one import for testing
    Match = OldImport

    # Verify attributes
    assert hasattr(Match, "prova_id")
    assert hasattr(Match, "round_number")
    assert hasattr(Match, "player1_id")
    assert hasattr(Match, "player2_id")
    assert hasattr(Match, "status")

    # Verify methods (none in this case, but pattern for future)
    assert hasattr(Match, "__tablename__")


def test_rack_imports():
    """Test that Rack can be imported from both locations"""
    from models import Rack as OldImport
    from models.match.models import Rack as NewImport

    assert OldImport is NewImport

    # Use one import for testing
    Rack = OldImport

    # Verify attributes
    assert hasattr(Rack, "match_id")
    assert hasattr(Rack, "rack_number")
    assert hasattr(Rack, "winner_id")

    # Verify methods
    assert callable(Rack.can_be_removed)
    assert callable(Rack.can_be_confirmed)
    assert callable(Rack.can_remove_confirmation)


def test_match_result_imports():
    """Test that MatchResult can be imported from both locations"""
    from models import MatchResult as OldImport
    from models.match.models import MatchResult as NewImport

    assert OldImport is NewImport

    # Verify attributes
    assert hasattr(OldImport, "match_id")
    assert hasattr(OldImport, "user_id")
    assert hasattr(OldImport, "winner_id")


def test_trio_match_imports():
    """Test that TrioMatch can be imported from both locations"""
    from models import TrioMatch as OldImport
    from models.match.models import TrioMatch as NewImport

    assert OldImport is NewImport

    # Use one import for testing
    TrioMatch = OldImport

    # Verify attributes
    assert hasattr(TrioMatch, "match_id")
    assert hasattr(TrioMatch, "player1_id")
    assert hasattr(TrioMatch, "player2_id")
    assert hasattr(TrioMatch, "player3_id")

    # Verify methods
    assert callable(TrioMatch.add_rack_win)
    assert callable(TrioMatch.get_current_state)


def test_match_services():
    """Test that match services are available"""
    from models.match.services import (
        MatchService,
        RackService,
        MatchResultService,
    )

    assert callable(MatchService.create_match)
    assert callable(MatchService.get_matches_by_prova)
    assert callable(RackService.add_rack_result)
    assert callable(MatchResultService.submit_result)
    assert callable(MatchService.create_trio_match)


def test_relationships():
    """Test that relationships are properly defined"""
    from models import Match, Rack

    # Match relationships
    assert hasattr(Match, "player1")
    assert hasattr(Match, "player2")
    assert hasattr(Match, "winner")
    assert hasattr(Match, "racks")

    # Foreign keys
    assert hasattr(Match, "prova_id")
    assert hasattr(Rack, "match_id")
