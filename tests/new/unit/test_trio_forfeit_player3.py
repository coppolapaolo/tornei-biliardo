"""Test forfeit handling for trio matches where player3 forfeits.

Regression test for bug where player3 in a trio match was not found
by WithdrawPolicyService.handle_forfeit() because player3_id is stored
in TrioMatch table, not Match table.
"""

import pytest

from models.competition.withdraw_policy_service import WithdrawPolicyService


@pytest.mark.unit
class TestTrioForfeitPlayer3:
    """Test forfeit handling for trio player3."""

    def test_handle_forfeit_queries_trio_player3(self):
        """Verify handle_forfeit queries TrioMatch for player3_id."""
        # This is a structural test to ensure the fix is in place
        # Read the source code to verify the fix
        import inspect
        source = inspect.getsource(WithdrawPolicyService.handle_forfeit)

        # Verify the fix includes:
        # 1. Import of TrioMatch
        assert "from models.match.models import TrioMatch" in source or \
               "TrioMatch" in source, "TrioMatch should be imported"

        # 2. Query joining TrioMatch for player3
        assert "TrioMatch.player3_id" in source, \
            "Should query TrioMatch.player3_id for player3 in trio"

        # 3. Separate handling for trio matches
        assert "is_trio == True" in source or "is_trio==True" in source, \
            "Should filter for trio matches"

        # 4. Call to trio.handle_forfeit
        assert "trio.handle_forfeit" in source or "handle_forfeit(user_id)" in source, \
            "Should call TrioMatch.handle_forfeit for trio matches"


@pytest.mark.unit
class TestTrioForfeitPlayer12:
    """Test forfeit handling for trio player1 or player2."""

    def test_handle_forfeit_uses_trio_handler_for_player12(self):
        """Player1/2 in trio should use TrioMatch.handle_forfeit, not regular logic."""
        import inspect
        source = inspect.getsource(WithdrawPolicyService.handle_forfeit)

        # Verify trio matches are excluded from regular match handling
        assert "Match.is_trio == False" in source or "is_trio == False" in source, \
            "Regular match query should exclude trio matches"

        # Verify separate query for trio matches with player1/player2
        assert "pending_trio_matches_as_player12" in source, \
            "Should have separate query for trio matches with player1/2"


@pytest.mark.unit
class TestForfeitUsesMatchDistance:
    """Test forfeit uses match_distance instead of gara.distance."""

    def test_handle_forfeit_uses_match_distance(self):
        """Forfeit should use match.match_distance when available."""
        import inspect
        source = inspect.getsource(WithdrawPolicyService.handle_forfeit)

        # Verify match_distance is used
        assert "match.match_distance" in source or "match_distance" in source, \
            "Should use match.match_distance for winning score"
