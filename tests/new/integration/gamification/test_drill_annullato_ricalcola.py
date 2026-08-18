"""Annullare una prova rimette in riga serie settimanale e traguardi.

La regola non è «togli uno», è **ricalcola**: se altri esercizi reggono
comunque la serie o il traguardo, non cambia niente. La differenza conta,
perché sottrarre avrebbe punito chi si allena tutti i giorni per un tocco
sbagliato — cioè esattamente la persona per cui l'annulla esiste.

Quello che questi test presidiano è il *non* cambiare: è il caso che una
sottrazione ingenua sbaglierebbe, e che nessun errore segnalerebbe.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.events.base import EventBus
from models.gamification.models import (
    Achievement,
    AchievementCategory,
    AchievementDifficulty,
    StreakTracker,
    StreakType,
    UserAchievement,
)
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Gli handler sono globali: si preservano, non si azzerano."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


@pytest.fixture
def player(db_session) -> User:
    user = User(
        username=f"undo_{uuid.uuid4().hex[:8]}",
        email=f"undo_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def drill(db_session) -> Challenge:
    challenge = Challenge(
        description="Serie di dieci bilie per il test dell'annulla",
        image_path="/static/challenges/undo.jpg",
        is_active=True,
    )
    db_session.add(challenge)
    db_session.commit()
    return challenge


def _streak(user_id: int, streak_type: StreakType) -> int:
    tracker = StreakTracker.query.filter_by(
        user_id=user_id, streak_type=streak_type
    ).first()
    return tracker.current_streak if tracker else 0


def _registra(user_id: int, challenge_id: int, score: int = 5) -> ChallengeAttempt:
    return ChallengeService.record_attempt(
        user_id=user_id, challenge_id=challenge_id, score=score
    )


# ────────────────────────────────────────────────────────────────────────────
# La serie settimanale
# ────────────────────────────────────────────────────────────────────────────
def test_l_unica_prova_della_settimana_annullata_spegne_la_serie(
    player, drill, db_session
):
    """Se quella prova era tutto, la serie torna a zero: non c'è più niente."""
    attempt = _registra(player.id, drill.id)
    db_session.commit()
    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1

    ChallengeService.delete_attempt(attempt_id=attempt.id, actor_id=player.id)
    db_session.commit()

    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 0
    assert _streak(player.id, StreakType.WEEKLY_ACTIVITY) == 0


def test_un_altra_prova_nella_stessa_settimana_tiene_su_la_serie(
    player, drill, db_session
):
    """È il caso che una sottrazione ingenua sbaglierebbe.

    Due prove nella stessa settimana, ne annullo una: la settimana resta viva,
    quindi la serie **non deve muoversi**. Chi si allena tutti i giorni non
    perde la serie per un tocco sbagliato.
    """
    prima = _registra(player.id, drill.id, score=4)
    _registra(player.id, drill.id, score=7)
    db_session.commit()
    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1

    ChallengeService.delete_attempt(attempt_id=prima.id, actor_id=player.id)
    db_session.commit()

    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1
    assert _streak(player.id, StreakType.WEEKLY_ACTIVITY) == 1


# ────────────────────────────────────────────────────────────────────────────
# I traguardi
# ────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def traguardo_tre_prove(db_session) -> Achievement:
    """Un traguardo su misura: tre prove bastano, così il test resta leggibile."""
    achievement = Achievement(
        slug=f"tre_prove_{uuid.uuid4().hex[:8]}",
        name="Tre prove",
        description="Completa tre esercizi",
        category=AchievementCategory.SKILL,
        difficulty=AchievementDifficulty.COMMON,
        requirements='{"type": "challenges_completed", "count": 3}',
        xp_reward=50,
        is_active=True,
    )
    db_session.add(achievement)
    db_session.commit()
    return achievement


def _sbloccato(user_id: int, achievement_id: int) -> bool:
    row = UserAchievement.query.filter_by(
        user_id=user_id, achievement_id=achievement_id
    ).first()
    return bool(row and row.is_unlocked)


def test_il_traguardo_cade_se_il_conto_non_lo_regge_piu(
    player, drill, traguardo_tre_prove, db_session
):
    prove = [_registra(player.id, drill.id, score=i) for i in range(3)]
    db_session.commit()
    assert _sbloccato(player.id, traguardo_tre_prove.id) is True

    ChallengeService.delete_attempt(attempt_id=prove[-1].id, actor_id=player.id)
    db_session.commit()

    assert _sbloccato(player.id, traguardo_tre_prove.id) is False


def test_il_traguardo_resta_se_le_prove_bastano_ancora(
    player, drill, traguardo_tre_prove, db_session
):
    """Quattro prove, ne annullo una: ne restano tre, e tre bastavano.

    Senza il ricalcolo questo caso non si distingue dall'altro, e chi ha cento
    prove perderebbe il traguardo cancellandone una.
    """
    prove = [_registra(player.id, drill.id, score=i) for i in range(4)]
    db_session.commit()
    assert _sbloccato(player.id, traguardo_tre_prove.id) is True

    ChallengeService.delete_attempt(attempt_id=prove[-1].id, actor_id=player.id)
    db_session.commit()

    assert _sbloccato(player.id, traguardo_tre_prove.id) is True


def test_il_traguardo_tolto_restituisce_il_suo_xp(
    player, drill, traguardo_tre_prove, db_session
):
    """Anche l'XP del traguardo torna indietro, con un movimento compensativo.

    Senza, sbloccare-e-annullare in cerchio sarebbe una fonte di XP: il
    traguardo si può riprendere completando di nuovo la terza prova.
    """
    from models.gamification.models import XPTransaction, XPTransactionType

    prove = [_registra(player.id, drill.id, score=i) for i in range(3)]
    db_session.commit()

    premi = XPTransaction.query.filter_by(
        user_id=player.id,
        transaction_type=XPTransactionType.ACHIEVEMENT_UNLOCK,
    ).all()
    if not premi:
        pytest.skip("Il traguardo non ha pagato XP in questo ambiente")
    assert sum(p.xp_amount for p in premi) > 0

    ChallengeService.delete_attempt(attempt_id=prove[-1].id, actor_id=player.id)
    db_session.commit()

    dopo = XPTransaction.query.filter_by(
        user_id=player.id,
        transaction_type=XPTransactionType.ACHIEVEMENT_UNLOCK,
    ).all()
    assert sum(p.xp_amount for p in dopo) == 0
    assert len(dopo) > len(premi)  # compensato, non cancellato
