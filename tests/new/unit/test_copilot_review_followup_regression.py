"""Regression test per i rilievi della review automatica (Copilot) sulla PR #6.

- scoring_service._apply_forfeit_scores: score None (legacy) → no TypeError, clamp >= 0
- table_assignment_service._get_free_tables: deduplica i tavoli (sorgente legacy
  con duplicati non deve assegnare lo stesso tavolo a due match)
- quest_service: target_progress=0 NON completata → 0% (non 100%); completata → 100%
"""

import uuid
import json
from datetime import date, time

from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    return u


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    return Gara(**base)


class TestForfeitExactModeNullScore:
    def test_none_score_does_not_crash_and_clamps(self, db_session):
        from models.match.scoring_service import ScoringService

        suffix = uuid.uuid4().hex[:8]
        p1, p2 = _user(suffix, "ff_p1"), _user(suffix, "ff_p2")
        db_session.add_all([p1, p2])
        db_session.flush()
        gara = _gara(suffix)
        db_session.add(gara)
        db_session.flush()

        # Match esatto 6 rack con player1_score = None (record legacy)
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=None,
            player2_score=0,
            match_distance=6,
            is_race_to=False,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        # p1 (score None) abbandona → niente TypeError, p2 = 6 - 0 = 6, >= 0
        ScoringService._apply_forfeit_scores(match, forfeit_player=1, winning_score=6)
        assert match.player2_score == 6
        assert match.player2_score >= 0
        # Lo score del perdente NON deve restare None (romperebbe le stringhe
        # punteggio e la classificazione che somma player*_score senza `or 0`).
        assert match.player1_score == 0
        # Invariante p1 + p2 == racks
        assert match.player1_score + match.player2_score == 6

    def test_none_score_forfeit_player2_mirror(self, db_session):
        """Caso speculare: player2 (perdente) con score None."""
        from models.match.scoring_service import ScoringService

        suffix = uuid.uuid4().hex[:8]
        p1, p2 = _user(suffix, "ff2_p1"), _user(suffix, "ff2_p2")
        db_session.add_all([p1, p2])
        db_session.flush()
        gara = _gara(suffix)
        db_session.add(gara)
        db_session.flush()

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=0,
            player2_score=None,
            match_distance=6,
            is_race_to=False,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        ScoringService._apply_forfeit_scores(match, forfeit_player=2, winning_score=6)
        assert match.player2_score == 0  # perdente normalizzato, non None
        assert match.player1_score == 6  # vincitore
        assert match.player1_score + match.player2_score == 6

    def test_incoherent_loser_score_still_preserves_invariant(self, db_session):
        """Record legacy con score perdente > racks: clamp a [0, racks],
        l'invariante p1+p2==racks regge comunque."""
        from models.match.scoring_service import ScoringService

        suffix = uuid.uuid4().hex[:8]
        p1, p2 = _user(suffix, "ffx_p1"), _user(suffix, "ffx_p2")
        db_session.add_all([p1, p2])
        db_session.flush()
        gara = _gara(suffix)
        db_session.add(gara)
        db_session.flush()

        # player1 (perdente) ha uno score incoerente: 10 con racks=6
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=10,
            player2_score=0,
            match_distance=6,
            is_race_to=False,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        ScoringService._apply_forfeit_scores(match, forfeit_player=1, winning_score=6)
        assert match.player1_score == 6  # clampato a racks
        assert match.player2_score == 0
        assert match.player1_score + match.player2_score == 6


class TestFreeTablesDedup:
    def test_duplicate_tables_deduped_preserving_order(self, db_session):
        from models.match.table_assignment_service import TableAssignmentService

        suffix = uuid.uuid4().hex[:8]
        gara = _gara(
            suffix, available_tables=json.dumps(["T1", "T1", "T2", "T3", "T2"])
        )
        db_session.add(gara)
        db_session.flush()

        free = TableAssignmentService._get_free_tables(gara.id)
        # Dedup mantenendo l'ordine di prima apparizione
        assert free == ["T1", "T2", "T3"]


class TestQuestZeroTargetSemantics:
    def _make_quest(self, db_session, suffix):
        from models.gamification.models import Quest, QuestType, QuestStatus
        from models.base import utc_now

        quest = Quest(
            name=f"Quest {suffix}",
            description="x",
            quest_type=QuestType.WEEKLY,
            status=QuestStatus.ACTIVE,
            start_date=utc_now(),
            end_date=utc_now(),
            requirements=json.dumps({"type": "matches_played", "target": 0}),
            xp_reward=10,
        )
        db_session.add(quest)
        db_session.flush()
        return quest

    def test_zero_target_not_completed_is_zero_percent(self, db_session):
        from models.gamification.quest_service import QuestService
        from models.gamification.models import QuestParticipation

        suffix = uuid.uuid4().hex[:8]
        user = _user(suffix, "q")
        db_session.add(user)
        db_session.flush()
        quest = self._make_quest(db_session, suffix)

        db_session.add(
            QuestParticipation(
                user_id=user.id,
                quest_id=quest.id,
                current_progress=0,
                target_progress=0,
                is_completed=False,
                xp_awarded=0,
            )
        )
        db_session.flush()

        stats = QuestService.get_quest_statistics(quest.id)
        # Non completata con target 0 → 0%, non 100%
        assert stats["average_progress"] == 0.0

    def test_zero_target_completed_is_hundred_percent(self, db_session):
        from models.gamification.quest_service import QuestService
        from models.gamification.models import QuestParticipation

        suffix = uuid.uuid4().hex[:8]
        user = _user(suffix, "qc")
        db_session.add(user)
        db_session.flush()
        quest = self._make_quest(db_session, suffix)

        db_session.add(
            QuestParticipation(
                user_id=user.id,
                quest_id=quest.id,
                current_progress=0,
                target_progress=0,
                is_completed=True,
                xp_awarded=0,
            )
        )
        db_session.flush()

        stats = QuestService.get_quest_statistics(quest.id)
        assert stats["average_progress"] == 100.0
