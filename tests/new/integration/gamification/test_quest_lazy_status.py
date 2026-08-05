"""
Integration tests per lo status quest calcolato a read-time.

Fase 1 / Task C (vedi GAMIFICATION_V3_HANDOFF.md): `update_quest_statuses()`
non è mai chiamato in produzione, quindi il campo `status` precalcolato resta
congelato sul valore di creazione. `Quest.effective_status` /
`is_currently_active` derivano lo stato reale dalle date con `utc_now()`, senza
bisogno di cron. Tutti i test qui NON chiamano update_quest_statuses.
"""

import json
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.gamification.quest_service import QuestService
from models.gamification.models import Quest, QuestType, QuestStatus


def _make_quest(
    *,
    start_offset_days: float,
    end_offset_days: float,
    stored_status: QuestStatus = QuestStatus.UPCOMING
) -> Quest:
    """Crea una quest con finestra relativa a ora e status DB esplicito.

    stored_status simula il valore "congelato" in DB (di norma UPCOMING perché
    nessun job lo aggiorna).
    """
    now = utc_now()
    quest = Quest(
        name="Test Quest",
        description="x",
        quest_type=QuestType.WEEKLY,
        status=stored_status,
        start_date=now + timedelta(days=start_offset_days),
        end_date=now + timedelta(days=end_offset_days),
        requirements=json.dumps({"type": "matches_played", "target": 5}),
        xp_reward=100,
    )
    db.session.add(quest)
    db.session.commit()
    return quest


class TestEffectiveStatus:
    def test_future_window_is_upcoming(self, db_session):
        quest = _make_quest(start_offset_days=2, end_offset_days=9)
        assert quest.effective_status == QuestStatus.UPCOMING
        assert quest.is_currently_active is False

    def test_current_window_is_active_even_if_db_says_upcoming(self, db_session):
        """Caso centrale: finestra corrente ma status DB congelato a UPCOMING."""
        quest = _make_quest(
            start_offset_days=-1,
            end_offset_days=6,
            stored_status=QuestStatus.UPCOMING,
        )
        assert quest.effective_status == QuestStatus.ACTIVE
        assert quest.is_currently_active is True

    def test_past_window_is_expired_even_if_db_says_active(self, db_session):
        """Finestra scaduta ma status DB ancora ACTIVE (cron mai girato)."""
        quest = _make_quest(
            start_offset_days=-10,
            end_offset_days=-3,
            stored_status=QuestStatus.ACTIVE,
        )
        assert quest.effective_status == QuestStatus.EXPIRED
        assert quest.is_currently_active is False

    def test_admin_expired_override_wins_over_temporal(self, db_session):
        """Override admin EXPIRED vince anche su finestra temporalmente attiva."""
        quest = _make_quest(
            start_offset_days=-1,
            end_offset_days=6,
            stored_status=QuestStatus.EXPIRED,
        )
        assert quest.effective_status == QuestStatus.EXPIRED
        assert quest.is_currently_active is False

    def test_completed_override_is_respected(self, db_session):
        quest = _make_quest(
            start_offset_days=-1,
            end_offset_days=6,
            stored_status=QuestStatus.COMPLETED,
        )
        assert quest.effective_status == QuestStatus.COMPLETED
        assert quest.is_currently_active is False


class TestGetUserQuestsActiveOnly:
    def test_active_only_uses_effective_status(self, db_session, isolated_players):
        """
        get_user_quests(active_only=True) deve includere la quest temporalmente
        attiva (status DB=UPCOMING) ed escludere future e scadute — senza alcun
        update_quest_statuses.
        """
        player = isolated_players[0]
        active_now = _make_quest(start_offset_days=-1, end_offset_days=6)
        _future = _make_quest(start_offset_days=3, end_offset_days=10)
        _past = _make_quest(
            start_offset_days=-10,
            end_offset_days=-2,
            stored_status=QuestStatus.ACTIVE,
        )

        results = QuestService.get_user_quests(player.id, active_only=True)
        returned_ids = {r["quest"].id for r in results}

        assert active_now.id in returned_ids
        assert _future.id not in returned_ids
        assert _past.id not in returned_ids
