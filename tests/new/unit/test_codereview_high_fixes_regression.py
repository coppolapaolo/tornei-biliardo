"""Regression test per i 5 bug HIGH trovati nella code review multi-agente.

Ogni classe copre una correzione specifica:

1. nudge_service.mark_feature_used         — usage_count None → TypeError al 1° uso
2. leaderboard_service._calculate_streak_longest — LeaderboardEntry senza score (NOT NULL)
3. spareggio_service.finalize_classification     — ordina ignorando matches_won (gare WINS)
4. set_lifecycle_service.complete_set            — ignora la modalità "esatto numero di set"
5. round_manager._recalculate_affected_classifications — dict-vs-ORM + bare except
"""

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.classification.models import RoundClassification, GaraClassification
from models.status_enum import GaraStatus, MatchStatus


def _make_user(suffix: str, name: str) -> User:
    u = User(
        username=f"{name}_{suffix}",
        email=f"{name}_{suffix}@test.com",
        role="player",
    )
    u.set_password("test123")
    return u


def _make_feature(code: str):
    """FeatureConfig minimo (feature_code è FK a feature_config.code)."""
    from models.gamification.feature_models import FeatureConfig

    return FeatureConfig(code=code, name=code, rules="[]", is_active=True)


# ---------------------------------------------------------------------------
# Bug 1 — nudge_service: usage_count None al primo uso
# ---------------------------------------------------------------------------
class TestNudgeUsageCountFirstUse:
    def test_mark_feature_used_first_time_does_not_raise(self, db_session):
        """Primo uso assoluto di una feature: usage_count parte da 0, non None."""
        from models.gamification.nudge_service import NudgeService
        from models.gamification.feature_models import UserFeatureUsage

        suffix = uuid.uuid4().hex[:8]
        user = _make_user(suffix, "nudge")
        db_session.add(user)
        feature_code = f"feat_{suffix}"
        db_session.add(_make_feature(feature_code))
        db_session.flush()

        # Non deve sollevare TypeError: NoneType + int
        NudgeService.mark_feature_used(user.id, feature_code)
        db_session.flush()

        usage = UserFeatureUsage.query.filter_by(
            user_id=user.id, feature_code=feature_code
        ).first()
        assert usage is not None
        assert usage.usage_count == 1

    def test_mark_feature_used_increments_on_second_use(self, db_session):
        from models.gamification.nudge_service import NudgeService
        from models.gamification.feature_models import UserFeatureUsage

        suffix = uuid.uuid4().hex[:8]
        user = _make_user(suffix, "nudge2")
        db_session.add(user)
        feature_code = f"feat_{suffix}"
        db_session.add(_make_feature(feature_code))
        db_session.flush()

        NudgeService.mark_feature_used(user.id, feature_code)
        NudgeService.mark_feature_used(user.id, feature_code)
        db_session.flush()

        usage = UserFeatureUsage.query.filter_by(
            user_id=user.id, feature_code=feature_code
        ).first()
        assert usage.usage_count == 2


# ---------------------------------------------------------------------------
# Bug 2 — leaderboard_service: STREAK_LONGEST senza score → IntegrityError
# ---------------------------------------------------------------------------
class TestStreakLongestLeaderboardScore:
    def test_calculate_streak_longest_sets_score(self, db_session):
        """Ogni LeaderboardEntry deve avere score valorizzato (colonna NOT NULL)."""
        from models.gamification.leaderboard_service import LeaderboardService
        from models.gamification.models import StreakTracker, StreakType

        suffix = uuid.uuid4().hex[:8]
        user = _make_user(suffix, "streak")
        db_session.add(user)
        db_session.flush()

        tracker = StreakTracker(
            user_id=user.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=3,
            longest_streak=7,
        )
        db_session.add(tracker)
        db_session.flush()

        entries = LeaderboardService._calculate_streak_longest()
        mine = [e for e in entries if e.user_id == user.id]
        assert len(mine) == 1
        assert mine[0].score == 7
        assert mine[0].calculated_at is not None

    def test_refresh_streak_longest_does_not_raise_integrity_error(self, db_session):
        """Il refresh completo (con commit) non deve sollevare IntegrityError."""
        from models.gamification.leaderboard_service import LeaderboardService
        from models.gamification.models import (
            StreakTracker,
            StreakType,
            LeaderboardType,
            LeaderboardEntry,
        )

        suffix = uuid.uuid4().hex[:8]
        user = _make_user(suffix, "streak_refresh")
        db_session.add(user)
        db_session.flush()

        db_session.add(
            StreakTracker(
                user_id=user.id,
                streak_type=StreakType.WEEKLY_ACTIVITY,
                current_streak=1,
                longest_streak=5,
            )
        )
        db_session.flush()

        # Non deve sollevare: prima del fix → NOT NULL constraint failed: score
        LeaderboardService._refresh_leaderboard(LeaderboardType.STREAK_LONGEST)

        entry = LeaderboardEntry.query.filter_by(
            leaderboard_type=LeaderboardType.STREAK_LONGEST, user_id=user.id
        ).first()
        assert entry is not None
        assert entry.score == 5


# ---------------------------------------------------------------------------
# Bug 3 — spareggio_service.finalize_classification: ordina ignorando matches_won
# ---------------------------------------------------------------------------
class TestFinalizeClassificationWinsOrdering:
    def _setup_wins_gara(self, db_session):
        suffix = uuid.uuid4().hex[:8]
        winner = _make_user(suffix, "wins_winner")  # più vittorie, meno rack diff
        runner = _make_user(suffix, "wins_runner")  # meno vittorie, più rack diff
        db_session.add_all([winner, runner])
        db_session.flush()

        gara = Gara(
            number=1,
            name=f"Gara WINS {suffix}",
            date=date(2026, 1, 1),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=1,
            current_round=1,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="amalfi",
            classification_system="WINS",
            tiebreaker_enabled=True,
            tiebreaker_until_position=3,
            status=GaraStatus.PLAYING.value,
        )
        db_session.add(gara)
        db_session.flush()

        for p in (winner, runner):
            db_session.add(
                Inscription(
                    gara_id=gara.id,
                    user_id=p.id,
                    is_withdrawn=False,
                    is_forfeit=False,
                    is_waitlist=False,
                )
            )
        db_session.flush()

        # RoundClassification del round finale: winner 2 vittorie/diff +2,
        # runner 1 vittoria/diff +8. In WINS deve vincere chi ha più vittorie.
        db_session.add_all(
            [
                RoundClassification(
                    gara_id=gara.id,
                    round_number=1,
                    user_id=winner.id,
                    position=2,
                    matches_won=2,
                    rack_difference=2,
                ),
                RoundClassification(
                    gara_id=gara.id,
                    round_number=1,
                    user_id=runner.id,
                    position=1,
                    matches_won=1,
                    rack_difference=8,
                ),
            ]
        )
        # GaraClassification con SSR (non decisivo qui: differiscono già su wins)
        db_session.add_all(
            [
                GaraClassification(
                    gara_id=gara.id,
                    user_id=winner.id,
                    position=2,
                    racks_won=12,
                    rack_difference=2,
                    matches_won=2,
                    spot_shot_wins=0,
                ),
                GaraClassification(
                    gara_id=gara.id,
                    user_id=runner.id,
                    position=1,
                    racks_won=14,
                    rack_difference=8,
                    matches_won=1,
                    spot_shot_wins=1,
                ),
            ]
        )
        db_session.flush()
        return gara, winner, runner

    def test_wins_system_ranks_by_matches_won_first(self, db_session):
        from models.competition.spareggio_service import SpareggioService

        gara, winner, runner = self._setup_wins_gara(db_session)

        ok, _msg = SpareggioService.finalize_classification(gara.id)
        assert ok is True

        gc_winner = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=winner.id
        ).first()
        gc_runner = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=runner.id
        ).first()

        # Chi ha più vittorie deve essere 1°, anche con rack_difference inferiore
        assert gc_winner.position == 1
        assert gc_runner.position == 2


# ---------------------------------------------------------------------------
# Bug 4 — set_lifecycle.complete_set: modalità "esatto numero di set"
# ---------------------------------------------------------------------------
class TestCompleteSetExactMode:
    def _make_multiset_match(self, db_session, *, is_race_to_sets, match_distance):
        suffix = uuid.uuid4().hex[:8]
        p1 = _make_user(suffix, "ms_p1")
        p2 = _make_user(suffix, "ms_p2")
        db_session.add_all([p1, p2])
        db_session.flush()

        gara = Gara(
            number=1,
            name=f"Gara MS {suffix}",
            date=date(2026, 1, 1),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=1,
            current_round=1,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
        )
        db_session.add(gara)
        db_session.flush()

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            is_multi_set=True,
            match_distance=match_distance,
            is_race_to_sets=is_race_to_sets,
            current_set_number=1,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()
        return match, p1, p2

    def test_exact_mode_does_not_complete_early(self, db_session):
        """Esatto 3 set: dopo 2 set vinti da p1 il match NON deve chiudersi."""
        match, p1, _p2 = self._make_multiset_match(
            db_session, is_race_to_sets=False, match_distance=3
        )
        from models.match.set_lifecycle_service import SetLifecycleService

        SetLifecycleService.complete_set(match, 1, p1.id)  # p1: 1
        SetLifecycleService.complete_set(match, 2, p1.id)  # p1: 2 (2/3 set)
        db_session.flush()

        # In race-to-2 si sarebbe già chiuso; in esatto-3 deve proseguire
        assert not MatchStatus.is_finished(match.status)
        assert match.winner_id is None
        assert match.current_set_number == 3

    def test_exact_mode_completes_after_all_sets(self, db_session):
        """Esatto 3 set: al 3° set giocato chiude col vincitore per conteggio."""
        match, p1, p2 = self._make_multiset_match(
            db_session, is_race_to_sets=False, match_distance=3
        )
        from models.match.set_lifecycle_service import SetLifecycleService

        SetLifecycleService.complete_set(match, 1, p1.id)  # p1: 1
        SetLifecycleService.complete_set(match, 2, p1.id)  # p1: 2
        SetLifecycleService.complete_set(match, 3, p2.id)  # p2: 1 → 3 set giocati
        db_session.flush()

        assert MatchStatus.is_finished(match.status)
        assert match.winner_id == p1.id  # 2 set a 1

    def test_race_to_sets_still_completes_at_threshold(self, db_session):
        """Controllo: modalità race-to-set continua a chiudere alla soglia."""
        match, p1, _p2 = self._make_multiset_match(
            db_session, is_race_to_sets=True, match_distance=2
        )
        from models.match.set_lifecycle_service import SetLifecycleService

        SetLifecycleService.complete_set(match, 1, p1.id)  # p1: 1
        SetLifecycleService.complete_set(match, 2, p1.id)  # p1: 2 == soglia
        db_session.flush()

        assert MatchStatus.is_finished(match.status)
        assert match.winner_id == p1.id


# ---------------------------------------------------------------------------
# Bug 5 — round_manager._recalculate_affected_classifications: dict-vs-ORM + bare except
# ---------------------------------------------------------------------------
class TestRecalculateAffectedClassifications:
    def test_recalc_repopulates_and_does_not_swallow(self, db_session):
        """Il ricalcolo deve RICREARE la RoundClassification dai match,
        non lasciare la tabella vuota (vecchio bug: requery di tabella svuotata
        + TypeError dict-vs-ORM ingoiato dal bare except)."""
        from models.competition.round_manager import AdvancedRoundManager

        suffix = uuid.uuid4().hex[:8]
        p1 = _make_user(suffix, "rc_p1")
        p2 = _make_user(suffix, "rc_p2")
        db_session.add_all([p1, p2])
        db_session.flush()

        gara = Gara(
            number=1,
            name=f"Gara RC {suffix}",
            date=date(2026, 1, 1),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=1,
            current_round=1,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="amalfi",
            classification_system="WINS",
            status=GaraStatus.PLAYING.value,
        )
        db_session.add(gara)
        db_session.flush()

        # Un match concluso: p1 batte p2 5-3
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=p1.id,
                player2_id=p2.id,
                player1_score=5,
                player2_score=3,
                status=MatchStatus.COMPLETED.value,
            )
        )
        # RoundClassification stale pre-esistente (verrà cancellata e ricreata)
        db_session.add(
            RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=p1.id,
                position=1,
                matches_won=0,
                rack_difference=0,
            )
        )
        db_session.flush()

        # Non deve sollevare e deve ripopolare la classifica dai match
        AdvancedRoundManager._recalculate_affected_classifications(gara.id, 1)
        db_session.flush()

        rows = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).all()
        assert len(rows) == 2  # entrambi i giocatori del match
        by_user = {r.user_id: r for r in rows}
        # p1 ha vinto il match → 1 vittoria, 1ª posizione
        assert by_user[p1.id].matches_won == 1
        assert by_user[p1.id].position == 1
