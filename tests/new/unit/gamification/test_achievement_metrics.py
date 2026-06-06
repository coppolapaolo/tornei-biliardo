"""Unit test per AchievementMetrics — fonte di verità degli achievement "conta N".

Verifica che ogni metrica conteggiabile derivi dal dato reale del dominio e che
i tipi non conteggiabili ritornino None (delegati alla logica booleana del
service o restino non ottenibili).
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from models.base import db, utc_now
from models.gamification.achievement_metrics import AchievementMetrics
from models.gamification.models import XPTransaction, XPTransactionType
from models.individual_match.proposal_models import (
    MatchProposal,
    ProposalType,
    ProposalStatus,
)


def _xp(user_id: int, txn_type: XPTransactionType) -> XPTransaction:
    t = XPTransaction(
        user_id=user_id,
        transaction_type=txn_type,
        xp_amount=1,
        reason="test",
        level_before=1,
        level_after=1,
    )
    db.session.add(t)
    return t


def _proposal(proposer_id: int, *, accepted_by_id=None, status=ProposalStatus.PENDING):
    now = utc_now()
    p = MatchProposal(
        proposer_id=proposer_id,
        proposal_type=ProposalType.OPEN,
        status=status,
        scheduled_at=now + timedelta(days=1),
        expires_at=now + timedelta(hours=20),
        accepted_by_id=accepted_by_id,
    )
    db.session.add(p)
    return p


class TestCountableMetrics:
    def test_match_wins_and_participation_from_stats(
        self, db_session, isolated_players
    ):
        uid = isolated_players[0].id
        with patch(
            "models.user.services.UserStatsService.get_user_stats",
            return_value={"won_matches": 7, "inscription_count": 3},
        ):
            assert (
                AchievementMetrics.current_value(uid, "match_wins", {"count": 5}) == 7
            )
            assert (
                AchievementMetrics.current_value(
                    uid, "tournament_participation", {"count": 10}
                )
                == 3
            )

    def test_tournament_placements_from_xp_ledger(self, db_session, isolated_players):
        uid = isolated_players[0].id
        _xp(uid, XPTransactionType.TOURNAMENT_WIN)
        _xp(uid, XPTransactionType.TOURNAMENT_WIN)
        _xp(uid, XPTransactionType.TOURNAMENT_PODIUM)
        # rumore: XP non legato a piazzamenti non deve contare
        _xp(uid, XPTransactionType.MATCH_WIN)
        db_session.commit()

        # wins = solo TOURNAMENT_WIN
        assert (
            AchievementMetrics.current_value(uid, "tournament_wins", {"count": 1}) == 2
        )
        # podium = TOURNAMENT_WIN + TOURNAMENT_PODIUM (il vincitore è sul podio)
        assert (
            AchievementMetrics.current_value(uid, "tournament_podium", {"count": 1})
            == 3
        )

    def test_proposals_created_excludes_cancelled(self, db_session, isolated_players):
        uid = isolated_players[0].id
        _proposal(uid)
        _proposal(uid)
        _proposal(uid, status=ProposalStatus.CANCELLED)  # non conta
        db_session.commit()

        assert (
            AchievementMetrics.current_value(
                uid, "match_proposals_created", {"count": 5}
            )
            == 2
        )

    def test_proposals_accepted(self, db_session, isolated_players):
        proposer = isolated_players[0].id
        accepter = isolated_players[1].id
        _proposal(proposer, accepted_by_id=accepter, status=ProposalStatus.ACCEPTED)
        _proposal(proposer, accepted_by_id=accepter, status=ProposalStatus.ACCEPTED)
        db_session.commit()

        assert (
            AchievementMetrics.current_value(
                accepter, "match_proposals_accepted", {"count": 10}
            )
            == 2
        )
        # il proponente non ha "accettato" nulla
        assert (
            AchievementMetrics.current_value(
                proposer, "match_proposals_accepted", {"count": 10}
            )
            == 0
        )


class TestUniqueOpponents:
    def test_counts_distinct_opponents_across_match_types(
        self, db_session, isolated_players
    ):
        from models.competition.models import Gara
        from models.match.models import Match

        uid = isolated_players[0].id
        opp1, opp2 = isolated_players[1].id, isolated_players[2].id

        gara = Gara(
            name="metrics gara",
            number=1,
            date=date.today(),
            distance=5,
            discipline="palla_9",
            matchmaking_strategy="amalfi",
            status="playing",
        )
        db_session.add(gara)
        db_session.flush()

        # Due partite vs opp1 (stesso avversario → conta 1), una vs opp2.
        for opp in (opp1, opp1, opp2):
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=uid,
                    player2_id=opp,
                    status="completed",
                    winner_id=uid,
                    player1_score=5,
                    player2_score=2,
                )
            )
        # Partita non completata → non conta
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=uid,
                player2_id=isolated_players[3].id,
                status="playing",
            )
        )
        db_session.commit()

        assert (
            AchievementMetrics.current_value(uid, "unique_opponents", {"count": 10})
            == 2
        )


class TestNonCountable:
    @pytest.mark.parametrize(
        "req_type",
        [
            "win_rate",
            "level_reached",
            "weekly_streak",
            "gaming_data_shared",
            "director_eligibility",
            "win_streak",
            "category_reached",
            "challenges_completed",
            "perfect_challenges",
            "strategies_tried",
            "unknown_future_type",
        ],
    )
    def test_non_countable_types_return_none(
        self, db_session, isolated_players, req_type
    ):
        uid = isolated_players[0].id
        assert AchievementMetrics.current_value(uid, req_type, {}) is None
