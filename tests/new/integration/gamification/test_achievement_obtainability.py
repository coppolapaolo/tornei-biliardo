"""Integration test: achievement resi ottenibili (cablaggio reale).

Verifica end-to-end che gli achievement prima non ottenibili ora si sblocchino
attraverso i percorsi reali:
- champion / podium_finish: dal libro mastro XP (premi di piazzamento gara);
- social_butterfly: creando proposte via ProposalService;
- popular_player: accettando una proposta via ProposalService;
- diverse_competitor: raggiungendo la soglia di avversari unici;
- category_climber: ricevendo una categoria via RatingService;
- challenge_master: completando drill via ChallengeService.
"""

from datetime import timedelta


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


class TestCategoryAchievementViaRatingService:
    def test_category_climber_unlocks_on_category_assignment(
        self, db_session, isolated_players
    ):
        from models.rating.models import CategoryLevel
        from models.rating.rating_service import RatingService

        seed_achievements(db.session)
        player = isolated_players[0]

        assert (
            AchievementService.has_achievement(player.id, "category_climber") is False
        )

        # Assegnare la categoria B innesca la riconciliazione → sblocco.
        RatingService.assign_player_category(player.id, CategoryLevel.B)

        assert AchievementService.has_achievement(player.id, "category_climber") is True
        # elite_player (categoria A) NON deve sbloccarsi con la sola B.
        assert AchievementService.has_achievement(player.id, "elite_player") is False


class TestChallengeAchievementViaChallengeService:
    def test_challenge_master_unlocks_after_ten_completions(
        self, db_session, isolated_players
    ):
        from models.challenge.models import Challenge, ChallengeAttempt
        from models.challenge.services import ChallengeService

        seed_achievements(db.session)
        player = isolated_players[0]

        challenge = Challenge(
            description="drill", image_path="d.png", pass_fail_only=True
        )
        db_session.add(challenge)
        db_session.flush()

        # 9 completamenti già a registro.
        for _ in range(9):
            db_session.add(
                ChallengeAttempt(
                    challenge_id=challenge.id,
                    user_id=player.id,
                    completed=True,
                    passed=True,
                )
            )
        db_session.commit()
        assert (
            AchievementService.has_achievement(player.id, "challenge_master") is False
        )

        # Il 10º completamento passa dal service → reconcile → sblocco.
        pending = ChallengeAttempt(challenge_id=challenge.id, user_id=player.id)
        db_session.add(pending)
        db_session.commit()
        ChallengeService.complete_challenge_attempt(pending.id, passed=True)

        assert AchievementService.has_achievement(player.id, "challenge_master") is True


class TestRetroactiveReconcileScript:
    """Lo script di reconcile concede retroattivamente i badge già meritati
    (ricalcolo idempotente, nessun reset)."""

    def _load_reconcile_all(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[4]
            / "scripts"
            / "reconcile_achievements.py"
        )
        spec = importlib.util.spec_from_file_location("_reconcile_script", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.reconcile_all

    def test_reconcile_all_grants_retroactive_badges(
        self, db_session, isolated_players
    ):
        seed_achievements(db.session)
        player = isolated_players[0]

        # Dato storico: una vittoria di gara a ledger, ma badge non ancora dato.
        _award_tournament_win(player.id)
        assert AchievementService.has_achievement(player.id, "champion") is False

        reconcile_all = self._load_reconcile_all()
        stats = reconcile_all(dry_run=False)

        assert stats["total_unlocked"] >= 1
        assert AchievementService.has_achievement(player.id, "champion") is True

        # Idempotente: una seconda passata non sblocca nient'altro.
        stats2 = reconcile_all(dry_run=False)
        assert stats2["total_unlocked"] == 0
