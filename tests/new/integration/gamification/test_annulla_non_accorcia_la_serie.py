"""Registrare una prova e annullarla non accorcia la serie (2026-11-10).

Il difetto, trovato da una revisione il 2026-11-10: dopo una prova cancellata
le serie settimanali si ricostruivano **sempre** dalle date dell'attività, e la
ricostruzione non sa due cose che il servizio vivo invece sa.

* I **congelamenti**: per la ricostruzione ogni settimana vuota è una rottura,
  mentre il servizio vivo l'aveva coperta spendendo un congelamento. Bastava
  registrare una prova e annullarla per trovarsi la serie più corta di prima —
  anche con un'altra prova nella stessa settimana a tenerla viva.
* Due **fonti** che gli handler contano: le sfide individuali confermate dai
  due giocatori e le sedute di scheda chiuse senza prove dietro.

La regola ora: se la settimana della prova tolta resta viva per altra attività,
la serie non si tocca; se resta vuota, la serie non scende sotto il valore che
aveva prima che quella settimana contasse.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from models.base import utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.events.base import EventBus
from models.gamification.models import StreakTracker, StreakType
from models.gamification.recalc_service import GamificationRecalcService
from models.gamification.streak_service import StreakService
from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

SERIE = (StreakType.WEEKLY_DRILL, StreakType.WEEKLY_ACTIVITY)


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Gli handler sono globali: si preservano, non si azzerano."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


def _utente(db_session) -> User:
    s = uuid.uuid4().hex[:8]
    user = User(username=f"serie_{s}", email=f"serie_{s}@test.com")
    user.role = UserRole.PLAYER.value
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def player(db_session) -> User:
    return _utente(db_session)


@pytest.fixture
def drill(db_session) -> Challenge:
    challenge = Challenge(
        description="Dieci bilie",
        image_path="/static/challenges/serie.jpg",
        pass_fail_only=False,
        is_active=True,
    )
    db_session.add(challenge)
    db_session.commit()
    return challenge


def _tracker(user_id: int, streak_type: StreakType) -> StreakTracker:
    return StreakTracker.query.filter_by(user_id=user_id, streak_type=streak_type).one()


def _serie_con_un_congelamento_speso(db_session, player, drill) -> None:
    """Tre settimane fa una prova, due settimane fa niente, la scorsa una prova.

    La settimana vuota l'ha coperta un congelamento: la serie vale 2.
    """
    oggi = date.today()
    for giorni in (21, 7):
        db_session.add(
            ChallengeAttempt(
                user_id=player.id,
                challenge_id=drill.id,
                completed=True,
                score=3,
                attempted_at=datetime.combine(
                    oggi - timedelta(days=giorni), datetime.min.time()
                ),
            )
        )
    db_session.commit()
    for streak_type in SERIE:
        StreakService.record_activity(
            player.id, streak_type, activity_date=oggi - timedelta(days=21)
        )
        _tracker(player.id, streak_type).freeze_count = 1
        db_session.commit()
        _, esito = StreakService.record_activity(
            player.id, streak_type, activity_date=oggi - timedelta(days=7)
        )
        assert esito["action"] == "freeze_used" and esito["current_streak"] == 2


def test_un_altra_prova_in_settimana_e_la_serie_non_si_muove(player, drill, db_session):
    _serie_con_un_congelamento_speso(db_session, player, drill)
    ChallengeService.record_attempt(user_id=player.id, challenge_id=drill.id, score=5)
    seconda = ChallengeService.record_attempt(
        user_id=player.id, challenge_id=drill.id, score=6
    )
    assert _tracker(player.id, StreakType.WEEKLY_DRILL).current_streak == 3

    ChallengeService.delete_attempt(attempt_id=seconda.id, actor_id=player.id)
    db_session.expire_all()

    for streak_type in SERIE:
        tracker = _tracker(player.id, streak_type)
        assert tracker.current_streak == 3
        assert tracker.longest_streak == 3


def test_registra_e_annulla_riporta_la_serie_a_com_era(player, drill, db_session):
    _serie_con_un_congelamento_speso(db_session, player, drill)
    settimana_scorsa = (date.today() - timedelta(days=7)).isocalendar()
    sola = ChallengeService.record_attempt(
        user_id=player.id, challenge_id=drill.id, score=5
    )
    assert _tracker(player.id, StreakType.WEEKLY_DRILL).current_streak == 3

    ChallengeService.delete_attempt(attempt_id=sola.id, actor_id=player.id)
    db_session.expire_all()

    for streak_type in SERIE:
        tracker = _tracker(player.id, streak_type)
        assert tracker.current_streak == 2
        assert tracker.longest_streak == 2
        assert (tracker.last_activity_year, tracker.last_activity_week) == (
            settimana_scorsa[0],
            settimana_scorsa[1],
        )


def test_registra_e_annulla_in_serie_non_fa_crescere_niente(player, drill, db_session):
    """Il giro registra-annulla ripetuto lascia tutto dov'era."""
    _serie_con_un_congelamento_speso(db_session, player, drill)

    for _giro in range(3):
        prova = ChallengeService.record_attempt(
            user_id=player.id, challenge_id=drill.id, score=5
        )
        ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=player.id)
    db_session.expire_all()

    tracker = _tracker(player.id, StreakType.WEEKLY_DRILL)
    assert tracker.current_streak == 2
    assert tracker.longest_streak == 2


def test_la_sfida_individuale_tiene_viva_la_settimana(player, drill, db_session):
    avversario = _utente(db_session)
    sfida = IndividualMatch(
        player1_id=player.id,
        player2_id=avversario.id,
        location="Sala",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=5,
        is_race_to=True,
        player1_score=5,
        player2_score=2,
    )
    db_session.add(sfida)
    db_session.commit()
    sfida.confirm_result(player.id)
    sfida.confirm_result(avversario.id)
    db_session.commit()
    assert _tracker(player.id, StreakType.WEEKLY_ACTIVITY).current_streak == 1

    prova = ChallengeService.record_attempt(
        user_id=player.id, challenge_id=drill.id, score=5
    )
    ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=player.id)
    db_session.expire_all()

    assert _tracker(player.id, StreakType.WEEKLY_ACTIVITY).current_streak == 1
    assert _tracker(player.id, StreakType.WEEKLY_DRILL).current_streak == 0
    date_per_serie = GamificationRecalcService._activity_dates_by_streak(player.id)
    assert len(date_per_serie[StreakType.WEEKLY_MATCH]) == 1
    assert len(date_per_serie[StreakType.WEEKLY_ACTIVITY]) == 1


def test_la_seduta_chiusa_senza_prove_tiene_viva_la_settimana(
    player, drill, db_session
):
    from models.training_sheet import TrainingSessionService
    from models.training_sheet.models import TrainingSheetItem
    from models.training_sheet.services import TrainingSheetService

    scheda = TrainingSheetService.create_sheet(player, "Scheda")
    voce = TrainingSheetItem(
        sheet_id=scheda.id,
        challenge_id=drill.id,
        position=1,
        measure="done",
        amount=10,
    )
    db_session.add(voce)
    db_session.commit()
    seduta = TrainingSessionService.start(scheda.id, player)
    TrainingSessionService.record(seduta.id, voce.id, player, done=True)
    TrainingSessionService.close(seduta.id, player)
    assert ChallengeAttempt.query.filter_by(user_id=player.id).count() == 0
    assert _tracker(player.id, StreakType.WEEKLY_DRILL).current_streak == 1

    prova = ChallengeService.record_attempt(
        user_id=player.id, challenge_id=drill.id, score=5
    )
    ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=player.id)
    db_session.expire_all()

    for streak_type in SERIE:
        assert _tracker(player.id, streak_type).current_streak == 1
    assert len(GamificationRecalcService._drill_activity_dates(player.id)) == 1
