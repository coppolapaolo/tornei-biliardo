"""Il bridge frontend deve essere un no-op fuori da una richiesta HTTP.

Regressione da produzione: `scripts/reconcile_achievements.py` assegnava XP e
ogni level-up stampava

    RuntimeError: Working outside of request context

La guardia `has_request_context()` c'era, ma dentro `_flash_gamification_event`:
gli handler compongono prima le stringhe con `_()`, e `gettext` risolve la
lingua leggendo `session`. Il controllo deve stare **prima** del corpo.

Il test pilota entrambe le condizioni invece di dedurle dall'ambiente:

- `has_request_context` è sostituita perché la suite lascia in giro contesti di
  richiesta di altri test; con `pytest-randomly` l'esito cambiava a ogni run.
- `_` è sostituita con una che solleva perché le due versioni di `flask_babel`
  si comportano in modo diverso: quella di produzione chiama comunque il locale
  selector (→ `session` → RuntimeError), quella installata qui ritorna `None`.
  Senza questa sostituzione il test passerebbe anche con il bug presente.

Il contratto verificato è quindi esplicito e indipendente da versione e
ordinamento: **fuori da una richiesta l'handler non valuta traduzioni**.
"""

from unittest.mock import patch

import pytest

import models.gamification.frontend_bridge as bridge_module
from models.gamification.frontend_bridge import GamificationFrontendBridge
from models.gamification.events import (
    XPGainedEvent,
    LevelUpEvent,
    AchievementUnlockedEvent,
    StreakMilestoneEvent,
    QuestCompletedEvent,
)


def _outside_request_gettext(*args, **kwargs):
    """Simula flask_babel di produzione fuori dal contesto di richiesta."""
    raise RuntimeError("Working outside of request context.")


HANDLERS_AND_EVENTS = [
    (
        "handle_xp_gained",
        lambda: XPGainedEvent(
            user_id=1,
            xp_amount=50,
            transaction_type="match_win",
            new_total_xp=1000,
            level_before=4,
            level_after=4,
            related_entities={"match_id": 7},
        ),
    ),
    (
        "handle_level_up",
        lambda: LevelUpEvent(
            user_id=1, old_level=4, new_level=5, total_xp=1000, unlocks=[]
        ),
    ),
    (
        "handle_achievement_unlocked",
        lambda: AchievementUnlockedEvent(
            user_id=1,
            achievement_id=3,
            achievement_slug="first_blood",
            achievement_name="First Blood",
            achievement_category="skill",
            achievement_difficulty="common",
            xp_awarded=100,
        ),
    ),
    (
        "handle_streak_milestone",
        lambda: StreakMilestoneEvent(
            user_id=1,
            streak_type="weekly_match",
            milestone=4,
            current_streak=4,
            freeze_earned=1,
            xp_bonus=120,
        ),
    ),
    (
        "handle_quest_completed",
        lambda: QuestCompletedEvent(
            user_id=1,
            quest_id=2,
            quest_name="Quest X",
            quest_type="weekly",
            xp_awarded=150,
            completion_percentage=100.0,
        ),
    ),
]


@pytest.mark.parametrize(
    "handler_name,make_event",
    HANDLERS_AND_EVENTS,
    ids=[h for h, _e in HANDLERS_AND_EVENTS],
)
def test_handler_does_not_translate_outside_request(handler_name, make_event):
    """Nessun contesto di richiesta: come negli script da console e nei task."""
    handler = getattr(GamificationFrontendBridge, handler_name)
    with patch.object(bridge_module, "has_request_context", lambda: False):
        with patch.object(bridge_module, "_", _outside_request_gettext):
            handler(make_event())  # non deve sollevare


def test_handlers_still_run_inside_a_request(app):
    """Contro-prova: la guardia non deve spegnere il bridge nelle richieste
    vere, altrimenti i toast sparirebbero e i test sopra passerebbero comunque.
    """
    called = {}

    def _spy(event_type, data, user_id):
        called["type"] = event_type

    with app.test_request_context("/"):
        with patch.object(
            GamificationFrontendBridge,
            "_flash_gamification_event",
            staticmethod(_spy),
        ):
            GamificationFrontendBridge.handle_level_up(
                LevelUpEvent(
                    user_id=1, old_level=1, new_level=2, total_xp=100, unlocks=[]
                )
            )

    assert called.get("type") == "levelup"
