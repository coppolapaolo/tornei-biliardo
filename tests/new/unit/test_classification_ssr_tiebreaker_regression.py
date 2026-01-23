"""
Regression test: SSR tiebreaker in calculate_classification_after_round.

Bug: When two players have equal racks_won in Random strategy,
the player with higher SSR score should be ranked higher.

Before fix: Used rack_difference as tiebreaker (ignoring SSR)
After fix: Uses spot_shot_wins from GaraClassification as tiebreaker

Vedi: https://github.com/... (if applicable)
"""

import pytest
from datetime import date, time

from models.user.models import User
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.classification.models import RoundClassification, GaraClassification
from models.status_enum import GaraStatus, MatchStatus


@pytest.fixture
def random_gara_with_tied_players(db_session):
    """
    Create a random strategy gara with two players tied on racks_won.

    Setup:
    - 2 players: player_a and player_b
    - Both have 11 racks_won after matches
    - player_a has SSR=1 (won tiebreaker)
    - player_b has SSR=0

    Expected: player_a should be ranked 1st due to SSR tiebreaker
    """
    import uuid
    suffix = uuid.uuid4().hex[:8]

    # Create users
    player_a = User(
        username=f"player_a_{suffix}",
        email=f"player_a_{suffix}@test.com",
        role="player",
    )
    player_a.set_password("test123")

    player_b = User(
        username=f"player_b_{suffix}",
        email=f"player_b_{suffix}@test.com",
        role="player",
    )
    player_b.set_password("test123")

    db_session.add_all([player_a, player_b])
    db_session.flush()

    # Create campionato with random strategy
    campionato = Campionato(
        name=f"Test Campionato SSR {suffix}",
        campionato_type="random",
        planned_gare_count=1,
        default_rounds_count=1,
        default_odd_policy="bye",
        default_anti_rematch=False,
        default_classification_system="RACKS",
        scoring_policy="racks",
    )
    db_session.add(campionato)
    db_session.flush()

    # Create gara
    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        classification_system="RACKS",
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    # Create inscriptions
    for player in [player_a, player_b]:
        inscription = Inscription(
            gara_id=gara.id,
            user_id=player.id,
            is_withdrawn=False,
            is_forfeit=False,
            is_waitlist=False,
        )
        db_session.add(inscription)
    db_session.flush()

    # Create match with equal racks for both players (tie)
    # player_a: 5 racks, player_b: 5 racks (draw - neither wins)
    # But we need both to end up with 11 racks total
    # Let's create two matches that result in 11 racks each

    # Match 1: player_a wins 5-3
    match1 = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player_a.id,
        player2_id=player_b.id,
        player1_score=5,  # player_a gets 5 racks
        player2_score=3,  # player_b gets 3 racks
        status=MatchStatus.COMPLETED.value,
    )
    db_session.add(match1)

    # Match 2: player_b wins 5-3 (simulating another match for demonstration)
    # Actually for this test, we'll just set up GaraClassification directly
    # since we want to test the sorting logic, not the match aggregation

    db_session.flush()

    # Pre-populate GaraClassification with SSR scores
    # player_a: 11 racks, SSR=1 (won tiebreaker)
    # player_b: 11 racks, SSR=0
    gc_a = GaraClassification(
        gara_id=gara.id,
        user_id=player_a.id,
        position=2,  # Initially wrong - should be 1 after fix
        racks_won=11,
        rack_difference=3,  # Lower rack_difference
        matches_won=1,
        spot_shot_wins=1,  # Won SSR
    )

    gc_b = GaraClassification(
        gara_id=gara.id,
        user_id=player_b.id,
        position=1,  # Initially wrong - should be 2 after fix
        racks_won=11,
        rack_difference=5,  # Higher rack_difference (but should lose due to SSR)
        matches_won=1,
        spot_shot_wins=0,  # Lost SSR
    )

    db_session.add_all([gc_a, gc_b])
    db_session.commit()

    return {
        "gara": gara,
        "player_a": player_a,  # Should be 1st (SSR=1)
        "player_b": player_b,  # Should be 2nd (SSR=0)
    }


class TestSSRTiebreakerRegression:
    """
    Regression test: SSR should break ties in Random strategy classification.

    Bug scenario:
    - Two players with equal racks_won (11 each)
    - Before fix: sorted by rack_difference → player_b first
    - After fix: sorted by SSR → player_a first (SSR=1 > SSR=0)
    """

    def test_calculate_classification_uses_ssr_tiebreaker(
        self, db_session, random_gara_with_tied_players
    ):
        """
        Regression: calculate_classification_after_round should use SSR
        as tiebreaker when players have equal racks_won.

        Bug: Player with higher rack_difference was ranked first
        Fix: Player with higher SSR score should be ranked first
        """
        data = random_gara_with_tied_players
        gara = db_session.get(Gara, data["gara"].id)
        player_a = db_session.get(User, data["player_a"].id)
        player_b = db_session.get(User, data["player_b"].id)

        # WHEN: Recalculate classification
        RoundClassification.calculate_classification_after_round(
            gara.id, gara.current_round
        )

        # THEN: Get the new classifications
        classifications = (
            RoundClassification.query
            .filter_by(gara_id=gara.id, round_number=gara.current_round)
            .order_by(RoundClassification.position)
            .all()
        )

        # Find positions for each player
        positions = {c.user_id: c.position for c in classifications}

        # player_a (SSR=1) should be ranked BEFORE player_b (SSR=0)
        # Even though player_b has higher rack_difference
        assert positions[player_a.id] < positions[player_b.id], (
            f"Player A (SSR=1) should be ranked before Player B (SSR=0). "
            f"Got: A={positions[player_a.id]}, B={positions[player_b.id]}"
        )

    def test_ssr_tiebreaker_not_applied_when_no_ssr_data(
        self, db_session, random_gara_with_tied_players
    ):
        """
        When no SSR data exists, should fall back to rack_difference.
        """
        data = random_gara_with_tied_players
        gara = db_session.get(Gara, data["gara"].id)

        # Remove SSR data
        GaraClassification.query.filter_by(gara_id=gara.id).delete()
        db_session.commit()

        # WHEN: Recalculate classification
        RoundClassification.calculate_classification_after_round(
            gara.id, gara.current_round
        )

        # THEN: Should complete without error
        classifications = (
            RoundClassification.query
            .filter_by(gara_id=gara.id, round_number=gara.current_round)
            .all()
        )
        assert len(classifications) >= 1  # At least some classification exists
