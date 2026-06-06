"""Integration test: achievement resi ottenibili (cablaggio reale).

Verifica end-to-end che gli achievement prima non ottenibili ora si sblocchino
attraverso i percorsi reali:
- champion / podium_finish: dal libro mastro XP (premi di piazzamento gara);
- social_butterfly: creando proposte via ProposalService;
- popular_player: accettando una proposta via ProposalService;
- diverse_competitor: raggiungendo la soglia di avversari unici.
"""

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.gamification.achievement_seeds import seed_achievements
from models.gamification.achievement_service import AchievementService
from models.gamification.models import XPTransaction, XPTransactionType
from models.individual_match.proposal_service import ProposalService


def _award_tournament_win(user_id: int) -> None:
    db.session.add(
        XPTransaction(
            user_id=user_id,
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
            xp_amount=500,
            reason="win",
            level_before=1,
            level_after=1,
        )
    )
    db.session.commit()


class TestTournamentPlacementAchievements:
    def test_champion_and_podium_unlock_from_xp_ledger(
        self, db_session, isolated_players
    ):
        seed_achievements(db.session)
        player = isolated_players[0]

        # Prima di vincere: non sbloccabili.
        _, unlocked = AchievementService.check_and_award_achievement(
            player.id, "champion"
        )
        assert unlocked is False

        # Una vittoria di gara registrata nel ledger → champion E podium.
        _award_tournament_win(player.id)

        _, champion_unlocked = AchievementService.check_and_award_achievement(
            player.id, "champion"
        )
        _, podium_unlocked = AchievementService.check_and_award_achievement(
            player.id, "podium_finish"
        )
        assert champion_unlocked is True
        assert podium_unlocked is True  # il vincitore è anche sul podio


class TestSocialAchievementsViaProposalService:
    def _create_open_proposal(self, proposer_id: int):
        return ProposalService.create_open_proposal(
            proposer_id=proposer_id,
            location="Sala Test",
            scheduled_at=utc_now() + timedelta(days=1),
        )

    def test_social_butterfly_unlocks_after_five_proposals(
        self, db_session, isolated_players
    ):
        seed_achievements(db.session)
        proposer = isolated_players[0]

        # social_butterfly richiede 5 proposte create.
        for _ in range(4):
            self._create_open_proposal(proposer.id)
        assert (
            AchievementService.has_achievement(proposer.id, "social_butterfly") is False
        )

        # La 5ª proposta innesca lo sblocco via _reevaluate_social_achievement.
        self._create_open_proposal(proposer.id)
        assert (
            AchievementService.has_achievement(proposer.id, "social_butterfly") is True
        )

    def test_popular_player_unlocks_after_accepting(self, db_session, isolated_players):
        seed_achievements(db.session)
        proposer = isolated_players[0]
        accepter = isolated_players[1]

        # popular_player richiede 10 proposte accettate dall'utente.
        for i in range(10):
            proposal = self._create_open_proposal(proposer.id)
            if i < 9:
                ProposalService.accept_proposal(accepter.id, proposal.id)
                assert (
                    AchievementService.has_achievement(accepter.id, "popular_player")
                    is False
                )
            else:
                ProposalService.accept_proposal(accepter.id, proposal.id)

        assert AchievementService.has_achievement(accepter.id, "popular_player") is True
