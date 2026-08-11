"""
Regression test: total_racks_won field in Classification model.

Bug (ADR-017): Classification model only stored total_point_difference (rack_difference)
but Random strategy campionatos sort by racks_won. The sorting value was not persisted.

Fix: Added total_racks_won field to Classification model and updated
ClassificationService.update_campionato_classification() to save racks_won.
"""

import pytest
from datetime import date, time

from models.user.models import User
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.classification.models import Classification
from models.classification.services import ClassificationService
from models.status_enum import GaraStatus, MatchStatus


@pytest.fixture
def random_campionato_with_matches(db_session):
    """
    Create a random strategy campionato with completed matches.

    Setup:
    - Campionato with random strategy
    - 1 gara with 2 players
    - Match results: player_a wins 5-3

    Expected after classification:
    - player_a: racks_won=5, rack_difference=+2
    - player_b: racks_won=3, rack_difference=-2
    """
    import uuid

    suffix = uuid.uuid4().hex[:8]

    # Create users
    player_a = User(
        username=f"rw_player_a_{suffix}",
        email=f"rw_player_a_{suffix}@test.com",
        role="player",
    )
    player_a.set_password("test123")

    player_b = User(
        username=f"rw_player_b_{suffix}",
        email=f"rw_player_b_{suffix}@test.com",
        role="player",
    )
    player_b.set_password("test123")

    db_session.add_all([player_a, player_b])
    db_session.flush()

    # Create campionato with random strategy
    campionato = Campionato(
        name=f"Test Random Campionato {suffix}",
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
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=2,  # All rounds completed
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        classification_system="RACKS",
        status=GaraStatus.COMPLETED.value,
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

    # Create completed match: player_a wins 5-3
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player_a.id,
        player2_id=player_b.id,
        player1_score=5,  # player_a: racks_won=5
        player2_score=3,  # player_b: racks_won=3
        status=MatchStatus.COMPLETED.value,
        winner_id=player_a.id,
    )
    db_session.add(match)
    db_session.commit()

    return {
        "campionato": campionato,
        "gara": gara,
        "player_a": player_a,  # 5 racks won, +2 diff
        "player_b": player_b,  # 3 racks won, -2 diff
    }


class TestTotalRacksWonRegression:
    """
    Regression test: Classification model must store total_racks_won.

    Bug (ADR-017): The Classification model only stored total_point_difference
    (rack_difference) but Random strategy campionatos sort by racks_won.
    The actual value used for sorting was not persisted.
    """

    def test_update_campionato_classification_saves_racks_won(
        self, db_session, random_campionato_with_matches
    ):
        """
        Regression: update_campionato_classification must save total_racks_won.

        Bug: Only rack_difference was saved in total_point_difference.
        Fix: Also save racks_won in total_racks_won field.
        """
        data = random_campionato_with_matches
        campionato_id = data["campionato"].id
        player_a_id = data["player_a"].id
        player_b_id = data["player_b"].id

        # WHEN: Update campionato classification
        classifications = ClassificationService.update_campionato_classification(
            campionato_id
        )

        # THEN: Classifications should have correct total_racks_won values
        assert len(classifications) == 2, "Should have 2 classifications"

        # Find classifications by user
        class_a = next(c for c in classifications if c.user_id == player_a_id)
        class_b = next(c for c in classifications if c.user_id == player_b_id)

        # Verify total_racks_won is saved correctly
        assert (
            class_a.total_racks_won == 5
        ), f"Player A should have 5 racks won, got {class_a.total_racks_won}"
        assert (
            class_b.total_racks_won == 3
        ), f"Player B should have 3 racks won, got {class_b.total_racks_won}"

        # Verify total_point_difference (rack_difference) is also correct
        assert (
            class_a.total_point_difference == 2
        ), f"Player A should have +2 rack_diff, got {class_a.total_point_difference}"
        assert (
            class_b.total_point_difference == -2
        ), f"Player B should have -2 rack_diff, got {class_b.total_point_difference}"

        # Verify positions (sorted by racks_won for random strategy)
        assert class_a.position < class_b.position, (
            f"Player A (5 racks) should be ranked before Player B (3 racks). "
            f"Got: A={class_a.position}, B={class_b.position}"
        )

    def test_total_racks_won_column_exists(self, db_session):
        """
        Verify that the total_racks_won column exists in the Classification model.

        This is a schema test to ensure the migration was applied.
        """
        # Create a classification with total_racks_won
        import uuid

        suffix = uuid.uuid4().hex[:8]

        user = User(
            username=f"schema_test_{suffix}",
            email=f"schema_test_{suffix}@test.com",
            role="player",
        )
        user.set_password("test123")
        db_session.add(user)
        db_session.flush()

        campionato = Campionato(
            name=f"Schema Test Campionato {suffix}",
            campionato_type="random",
        )
        db_session.add(campionato)
        db_session.flush()

        # Create classification with total_racks_won
        classification = Classification(
            campionato_id=campionato.id,
            user_id=user.id,
            position=1,
            total_matches_won=2,
            total_racks_won=15,  # New field
            total_point_difference=5,
            gare_played=1,
        )
        db_session.add(classification)
        db_session.commit()

        # Reload and verify
        loaded = db_session.get(Classification, classification.id)
        assert loaded.total_racks_won == 15, (
            f"total_racks_won should be saved and loaded correctly. "
            f"Expected 15, got {loaded.total_racks_won}"
        )
