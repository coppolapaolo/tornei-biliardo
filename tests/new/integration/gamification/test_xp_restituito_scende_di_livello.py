"""L'XP restituito fa scendere di livello, e non va mai sotto zero (2026-11-10).

Il difetto, trovato da una revisione il 2026-11-10: `LevelService.award_xp`
sapeva salire di livello ma non scendere. Annullare una prova che aveva fatto
passare di livello restituisce l'XP con un movimento negativo: il livello
restava quello nuovo e `current_xp` — l'XP dentro il livello — andava sotto
zero. Il badge in alto mostrava «-110 / N XP».

Il livello è una funzione dell'XP totale (è così che lo ricalcola
`GamificationRecalcService._rebuild_level`): con un importo negativo si scende
finché serve, come con uno positivo si sale. `highest_level_reached` resta: è
un massimo storico.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.events.base import EventBus
from models.gamification.config_service import (
    GamificationConfigService as ConfigService,
)
from models.gamification.level_service import LevelService
from models.gamification.models import UserLevel, XPTransactionType
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Gli handler sono globali: si preservano, non si azzerano."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


@pytest.fixture
def player(db_session) -> User:
    s = uuid.uuid4().hex[:8]
    user = User(username=f"xp_{s}", email=f"xp_{s}@test.com")
    user.role = UserRole.PLAYER.value
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


def _dai(user_id: int, quanto: int):
    return LevelService.award_xp(
        user_id=user_id,
        xp_amount=quanto,
        transaction_type=XPTransactionType.ADMIN_GRANT,
        reason="test",
    )


def test_l_importo_negativo_fa_scendere_di_livello(player, db_session):
    soglia = ConfigService.get_xp_for_next_level(1)
    _dai(player.id, soglia - 10)
    livello, salito = _dai(player.id, 50)
    assert salito is True
    assert (livello.current_level, livello.current_xp) == (2, 40)

    livello, salito = _dai(player.id, -50)

    assert salito is False
    assert livello.current_level == 1
    assert livello.current_xp == soglia - 10
    assert livello.total_xp == soglia - 10
    assert livello.highest_level_reached == 2


def test_si_scende_di_quanti_livelli_serve(player, db_session):
    fino_al_terzo = ConfigService.get_xp_for_level(3)
    livello, _salito = _dai(player.id, fino_al_terzo + 5)
    assert livello.current_level == 3

    livello, _salito = _dai(player.id, -(fino_al_terzo + 5) + 7)

    assert livello.current_level == 1
    assert livello.current_xp == 7
    assert livello.total_xp == 7


def test_sotto_zero_non_si_va(player, db_session):
    _dai(player.id, 30)

    livello, _salito = _dai(player.id, -80)

    assert livello.current_level == 1
    assert livello.current_xp == 0
    assert livello.total_xp == 0


def test_il_badge_non_mostra_mai_xp_negativo(player, db_session):
    """Le righe scritte prima della correzione possono essere già sotto zero."""
    db_session.add(
        UserLevel(user_id=player.id, current_level=2, current_xp=-110, total_xp=150)
    )
    db_session.commit()

    progresso = LevelService.get_level_progress(player.id)

    assert progresso["current_xp"] == 0
    assert progresso["progress_percentage"] == 0.0


def test_annullare_la_prova_che_aveva_fatto_salire_riporta_al_livello_di_prima(
    player, db_session
):
    esercizio = Challenge(
        description="Dieci bilie",
        image_path="/static/challenges/xp.jpg",
        pass_fail_only=False,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.commit()
    soglia = ConfigService.get_xp_for_next_level(1)
    _dai(player.id, soglia - 10)
    prova = ChallengeService.record_attempt(
        user_id=player.id, challenge_id=esercizio.id, score=5
    )
    assert db_session.get(UserLevel, player.id).current_level >= 2

    ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=player.id)
    db_session.expire_all()

    livello = db_session.get(UserLevel, player.id)
    assert livello.current_level == 1
    assert livello.current_xp == soglia - 10
    assert LevelService.get_level_progress(player.id)["current_xp"] >= 0
