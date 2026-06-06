"""Anti-invasività — policy un-solo-canale per gli eventi celebrativi.

GAMIFICATION_V3 §11 / ADR-031: gli eventi *celebrativi* (XP, level-up,
achievement, streak milestone, quest completata) devono produrre **solo** il
toast transitorio (frontend bridge). La **notifica persistente** è riservata a
ciò che è **azionabile / che puoi perderti** (invito a match, gara in zona).

Questo chiude alla radice la ridondanza toast+notifica che prima colpiva 4
eventi su 5 (una sola partita generava ~3 toast + ~3 notifiche).

I test verificano il *contratto*: pubblicando gli eventi celebrativi non viene
creata alcuna notifica persistente, e la classe di handler gamification non
registra più handler per quei tipi di evento.
"""

from __future__ import annotations

import pytest

from models.events.base import EventBus
from models.gamification.events import (
    LevelUpEvent,
    AchievementUnlockedEvent,
    StreakMilestoneEvent,
    QuestCompletedEvent,
)
from models.gamification.notification_handlers import (
    GamificationNotificationHandlers,
)
from models.notification.models import Notification, NotificationType


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Preserva e ripristina gli handler dell'EventBus (vedi tests/CLAUDE.md)."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


# (evento, NotificationType che NON deve essere creato)
CELEBRATORY_CASES = [
    (
        LevelUpEvent(user_id=0, old_level=1, new_level=2, unlocks=[], total_xp=300),
        NotificationType.LEVEL_UP,
    ),
    (
        AchievementUnlockedEvent(
            user_id=0,
            achievement_id=1,
            achievement_slug="first_blood",
            achievement_name="First Blood",
            achievement_category="skill",
            achievement_difficulty="common",
            xp_awarded=50,
        ),
        NotificationType.ACHIEVEMENT_UNLOCKED,
    ),
    (
        StreakMilestoneEvent(
            user_id=0,
            streak_type="WEEKLY_MATCH",
            milestone=4,
            current_streak=4,
            freeze_earned=1,
            xp_bonus=120,
        ),
        NotificationType.STREAK_MILESTONE,
    ),
    (
        QuestCompletedEvent(
            user_id=0,
            quest_id=1,
            quest_name="Sfida settimanale",
            quest_type="weekly",
            xp_awarded=80,
            completion_percentage=100.0,
        ),
        NotificationType.QUEST_COMPLETED,
    ),
]


class TestCelebratoryEventsAreToastOnly:
    """Gli eventi celebrativi non devono generare notifiche persistenti."""

    @pytest.mark.parametrize("event,notif_type", CELEBRATORY_CASES)
    def test_no_persistent_notification_for_celebratory_event(
        self, db_session, isolated_players, event, notif_type
    ):
        user = isolated_players[0]
        event.user_id = user.id

        # Riallinea gli handler al codice corrente (post-retire).
        GamificationNotificationHandlers.register_all_handlers()

        EventBus.publish(event)
        db_session.flush()

        created = Notification.query.filter_by(
            user_id=user.id, notification_type=notif_type
        ).all()
        assert created == [], (
            f"L'evento celebrativo {type(event).__name__} non deve creare una "
            f"notifica persistente {notif_type} (§11: solo toast)."
        )

    @pytest.mark.parametrize(
        "event_type",
        [
            LevelUpEvent,
            AchievementUnlockedEvent,
            StreakMilestoneEvent,
            QuestCompletedEvent,
        ],
    )
    def test_class_registers_no_handler_for_celebratory_event(self, event_type):
        """register_all_handlers() non deve agganciare gli eventi celebrativi."""
        EventBus._handlers.pop(event_type, None)
        GamificationNotificationHandlers.register_all_handlers()
        assert (
            event_type not in EventBus._handlers or EventBus._handlers[event_type] == []
        )
