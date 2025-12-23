"""
Regression test for Use Case 8 variant: Random strategy round locking.
Ensures that pre-generated rounds do not incorrectly lock the current round.
"""

import pytest
from datetime import date, datetime, timedelta

from models import Gara, Match, Inscription
from models.status_enum import GaraStatus
from models.competition.services import GaraService, InscriptionService
from models.competition.round_manager import AdvancedRoundManager

@pytest.mark.integration
class TestRandomGaraLocking:
    """Test locking behavior for Random matchmaking strategy"""

    def test_random_strategy_round_1_is_unlocked_at_startup(
        self, isolated_admin_user, isolated_players, db_session
    ):
        """
        Verify that in a Random tournament with 3 pre-generated rounds:
        - Round 1 matches are UNLOCKED for modification.
        - Round 2 and 3 matches are LOCKED.
        """
        admin_user = isolated_admin_user
        players_6 = isolated_players[:6]

        # 1. Create Random gara with 3 rounds
        gara = GaraService.create_gara(
            number=1,
            name="Random Locking Test",
            date=date.today() + timedelta(days=1),
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=admin_user.id,
            matchmaking_strategy="random",
            rounds_count=3,
            min_participants=6
        )

        # 2. Inscribe 6 players
        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # 3. Open inscriptions
        inscription_start = datetime.utcnow() - timedelta(hours=1)
        inscription_end = datetime.utcnow() + timedelta(hours=1)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        db_session.commit()

        # 4. Start first round (this pre-generates ALL 3 rounds for Random strategy)
        GaraService.start_first_round(gara.id)
        db_session.commit()
        
        # Reload to ensure state is fresh
        db_session.expire_all()
        db_session.refresh(gara)
        
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # 5. Verify match locking
        # Count matches for each round
        for round_num in range(1, 4):
            matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
            assert len(matches) > 0, f"No matches found for round {round_num}"
            
            for match in matches:
                can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)
                
                if round_num == 1:
                    # Round 1 should be UNLOCKED
                    assert can_modify, f"Match in round 1 should be modifiable. Reason: {reason}"
                else:
                    # Round 2 and 3 should be LOCKED
                    assert not can_modify, f"Match in round {round_num} should be locked."

        # 6. Progress to round 2 (simulate completing all matches in round 1)
        for match in Match.query.filter_by(gara_id=gara.id, round_number=1).all():
            if not match.is_bye:
                match.status = "completed"
                match.player1_score = 3
                match.player2_score = 1
                match.winner_id = match.player1_id
        
        # Update progression
        GaraService.update_round_progression(gara.id)
        db_session.refresh(gara)
        
        # If all matches are completed, RoundService/GaraService might move current_round to 2
        # Note: in Random strategy, we might need to manually or automatically advance current_round
        # The logic in GaraService.update_round_progression handles this.
        
        # In this test, let's verify round 2 is now unlocked if it becomes current
        if gara.current_round == 2:
            matches_r2 = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
            for match in matches_r2:
                can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
                assert can_modify, "Match in round 2 should be modifiable when it is current"
                
            # Round 1 should now be LOCKED
            matches_r1 = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
            for match in matches_r1:
                can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
                assert not can_modify, "Past round 1 should be locked"
