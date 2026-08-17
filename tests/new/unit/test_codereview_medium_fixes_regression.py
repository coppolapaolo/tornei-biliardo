"""Regression test per i fix MEDIUM/LOW della code review multi-agente.

Copre:
- scoring_service.forfeit (modalità esatto numero rack) — invariante p1+p2==racks
- match_service.apply_batch_corrections — tipo sconosciuto → overall_success False
- inscription_service.can_start_with_current_inscriptions — esclude is_withdrawn
- level_service.check_unlock_eligibility — metodo ripristinato (no AttributeError)
- quest_service — nessun ZeroDivisionError con target_progress=0 (record legacy)
- venue_manager_service.process_venue_manager_request — imposta processed_at
"""

import uuid
import json
from datetime import date, time

from models.user.models import User
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus


def _user(suffix, name, role="player"):
    u = User(username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role=role)
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


# ---------------------------------------------------------------------------
# scoring_service: forfeit in modalità "esatto numero di rack"
# ---------------------------------------------------------------------------
class TestForfeitExactModeInvariant:
    def test_forfeit_preserves_rack_sum_in_exact_mode(self, db_session):
        from models.match.scoring_service import ScoringService

        suffix = uuid.uuid4().hex[:8]
        p1, p2 = _user(suffix, "ff_p1"), _user(suffix, "ff_p2")
        db_session.add_all([p1, p2])
        db_session.flush()

        gara = _gara(suffix)
        db_session.add(gara)
        db_session.flush()

        for p in (p1, p2):
            db_session.add(
                Inscription(
                    gara_id=gara.id, user_id=p.id, is_withdrawn=False, is_waitlist=False
                )
            )
        db_session.flush()

        # Match single-set, modalità ESATTO 6 rack (is_race_to=False).
        # p1 ha già vinto 2 rack, poi abbandona.
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=2,
            player2_score=0,
            match_distance=6,
            is_race_to=False,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.flush()

        ScoringService.forfeit_match(match.id, p1.id)
        db_session.flush()

        updated = db_session.get(Match, match.id)
        # Invariante: p1 + p2 == racks totali (6); prima del fix p2 finiva a 6 → somma 8
        assert updated.player1_score + updated.player2_score == 6
        assert updated.winner_id == p2.id


# ---------------------------------------------------------------------------
# match_service: batch correction con tipo sconosciuto
# ---------------------------------------------------------------------------
class TestBatchCorrectionUnknownType:
    def test_unknown_correction_type_is_not_success(self, db_session):
        from models.match.match_service import MatchService

        suffix = uuid.uuid4().hex[:8]
        admin = _user(suffix, "bc_admin", role="admin")
        p1, p2 = _user(suffix, "bc_p1"), _user(suffix, "bc_p2")
        db_session.add_all([admin, p1, p2])
        db_session.flush()

        gara = _gara(suffix)
        db_session.add(gara)
        db_session.flush()

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=3,
            player2_score=1,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=p1.id,
        )
        db_session.add(match)
        db_session.flush()

        result = MatchService.apply_batch_corrections(
            gara_id=gara.id,
            corrections=[
                {
                    "match_id": match.id,
                    "correction_type": "tipo_inesistente",  # sconosciuto
                    "new_winner_score": 5,
                    "new_loser_score": 1,
                }
            ],
            admin_id=admin.id,
        )

        # Prima del fix: nessun ramo else → overall_success restava True
        assert result.success is False


# ---------------------------------------------------------------------------
# inscription_service: conteggio esclude is_withdrawn
# ---------------------------------------------------------------------------
class TestCanStartExcludesWithdrawn:
    def test_withdrawn_inscriptions_not_counted(self, db_session):
        from models.competition.inscription_service import InscriptionService

        suffix = uuid.uuid4().hex[:8]
        players = [_user(suffix, f"ins_p{i}") for i in range(3)]
        db_session.add_all(players)
        db_session.flush()

        gara = _gara(suffix, min_participants=3, status=GaraStatus.INSCRIPTION.value)
        db_session.add(gara)
        db_session.flush()

        # 2 attivi + 1 ritirato = 2 attivi reali < min 3 → non può partire
        db_session.add_all(
            [
                Inscription(
                    gara_id=gara.id,
                    user_id=players[0].id,
                    is_withdrawn=False,
                    is_waitlist=False,
                ),
                Inscription(
                    gara_id=gara.id,
                    user_id=players[1].id,
                    is_withdrawn=False,
                    is_waitlist=False,
                ),
                Inscription(
                    gara_id=gara.id,
                    user_id=players[2].id,
                    is_withdrawn=True,
                    is_waitlist=False,
                ),
            ]
        )
        db_session.flush()

        # Prima del fix: contava anche il ritirato (3) → True erroneamente
        assert InscriptionService.can_start_with_current_inscriptions(gara.id) is False


# ---------------------------------------------------------------------------
# level_service: check_unlock_eligibility ripristinato come metodo
# ---------------------------------------------------------------------------
class TestCheckUnlockEligibilityRestored:
    def test_method_exists_and_callable(self, db_session):
        from models.gamification.level_service import LevelService

        suffix = uuid.uuid4().hex[:8]
        user = _user(suffix, "ce")
        db_session.add(user)
        db_session.flush()

        # Prima del fix il `def` era sparito → AttributeError
        assert hasattr(LevelService, "check_unlock_eligibility")
        result = LevelService.check_unlock_eligibility(user.id, "tournament_creation")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# quest_service: nessun ZeroDivisionError con target_progress legacy = 0
# ---------------------------------------------------------------------------
class TestQuestZeroTargetNoCrash:
    def test_get_quest_statistics_with_zero_target(self, db_session):
        from models.gamification.quest_service import QuestService
        from models.gamification.models import (
            Quest,
            QuestParticipation,
            QuestType,
            QuestStatus,
        )
        from models.base import utc_now

        suffix = uuid.uuid4().hex[:8]
        user = _user(suffix, "q")
        db_session.add(user)
        db_session.flush()

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

        # Partecipazione legacy con target_progress=0
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

        # Prima del fix: ZeroDivisionError nel calcolo della percentuale
        stats = QuestService.get_quest_statistics(quest.id)
        assert stats is not None


# ---------------------------------------------------------------------------
# venue_manager_service: processed_at impostato su approve/reject
# ---------------------------------------------------------------------------
class TestVenueRequestProcessedAt:
    def _setup(self, db_session, suffix):
        from models.location.models import BilliardHall

        admin = _user(suffix, "vm_admin", role="admin")
        applicant = _user(suffix, "vm_user")
        db_session.add_all([admin, applicant])
        db_session.flush()

        venue = BilliardHall(name=f"Sala {suffix}", city="Roma")
        db_session.add(venue)
        db_session.flush()
        return admin, applicant, venue

    def _make_request(self, db_session, applicant, venue):
        from models.user.models import VenueManagerRequest
        from models.status_enum import VenueManagerRequestStatus

        req = VenueManagerRequest(
            user_id=applicant.id,
            venue_id=venue.id,
            status=VenueManagerRequestStatus.PENDING.value,
        )
        db_session.add(req)
        db_session.flush()
        return req

    def test_approve_sets_processed_at(self, db_session):
        from models.user.venue_manager_service import VenueManagerService

        suffix = uuid.uuid4().hex[:8]
        admin, applicant, venue = self._setup(db_session, suffix)
        req = self._make_request(db_session, applicant, venue)

        VenueManagerService.process_venue_manager_request(
            admin_user=admin, request_id=req.id, approve=True, notes="ok"
        )
        db_session.flush()
        assert req.processed_at is not None

    def test_reject_sets_processed_at(self, db_session):
        from models.user.venue_manager_service import VenueManagerService

        suffix = uuid.uuid4().hex[:8]
        admin, applicant, venue = self._setup(db_session, suffix)
        req = self._make_request(db_session, applicant, venue)

        VenueManagerService.process_venue_manager_request(
            admin_user=admin, request_id=req.id, approve=False, notes="no"
        )
        db_session.flush()
        assert req.processed_at is not None
