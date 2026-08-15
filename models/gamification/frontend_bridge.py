"""
Gamification Frontend Bridge - Connects Backend Events to Frontend Animations

This module listens to gamification domain events and creates temporary
frontend events (via Flask flash mechanism) that trigger animations in the browser.

It acts as the "Transmission" between the Python backend engine and the
JavaScript frontend display.
"""

from __future__ import annotations
import functools
import json
import logging
from typing import Any, Callable, Dict, TypeVar

from flask import flash, has_request_context
from flask_babel import gettext as _
from flask_login import current_user

from models.events.base import EventBus
from models.gamification.events import (
    XPGainedEvent,
    LevelUpEvent,
    AchievementUnlockedEvent,
    StreakMilestoneEvent,
    StreakBrokenEvent,
    QuestCompletedEvent,
)


class GamificationEventType:
    """Enum for frontend event types."""

    XP = "xp"
    LEVEL_UP = "levelup"
    ACHIEVEMENT = "achievement"
    STREAK = "streak"
    STREAK_LOST = "streak_lost"
    QUEST = "quest"
    WELCOME = "welcome"


logger = logging.getLogger(__name__)

_Handler = TypeVar("_Handler", bound=Callable[..., None])


def _only_in_request(handler: _Handler) -> _Handler:
    """No-op per gli handler del bridge fuori da una richiesta HTTP.

    Il bridge esiste solo per accodare flash message alla risposta corrente:
    senza richiesta non c'è nessuno a cui mostrarli. Il controllo va **prima**
    del corpo dell'handler, non dentro ``_flash_gamification_event``: gli
    handler compongono le stringhe con ``_()`` e ``gettext`` risolve la lingua
    leggendo ``session``, che fuori dal contesto solleva
    ``RuntimeError: Working outside of request context``.

    Emerso lanciando ``scripts/reconcile_achievements.py`` in produzione: ogni
    level-up stampava un traceback. Il lavoro andava comunque a termine (i
    gestori di EventBus sono isolati), ma lo stesso vale per qualunque script
    da console o scheduled task che assegni XP, dove l'errore è puro rumore
    che nasconde i problemi veri.
    """

    @functools.wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        if not has_request_context():
            return None
        return handler(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


class GamificationFrontendBridge:
    """
    Bridge that translates domain events into frontend flash messages.

    These messages are consumed by base.html and passed to
    gamification.js via showGamificationEvent().
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Register all bridge handlers with the EventBus."""
        EventBus.register_handler(
            XPGainedEvent,
            GamificationFrontendBridge.handle_xp_gained,
            priority=0,  # Low priority, UI only
        )

        EventBus.register_handler(
            LevelUpEvent, GamificationFrontendBridge.handle_level_up, priority=0
        )

        EventBus.register_handler(
            AchievementUnlockedEvent,
            GamificationFrontendBridge.handle_achievement_unlocked,
            priority=0,
        )

        EventBus.register_handler(
            StreakMilestoneEvent,
            GamificationFrontendBridge.handle_streak_milestone,
            priority=0,
        )

        # B4: do NOT register a frontend handler for StreakBrokenEvent — the
        # toast is non-actionable (user can't "undo" a broken streak), so it
        # adds noise without value. The event is still emitted by the service
        # layer for analytics/notifications.

        EventBus.register_handler(
            QuestCompletedEvent,
            GamificationFrontendBridge.handle_quest_completed,
            priority=0,
        )

        logger.info("Registered gamification frontend bridge handlers")

    @staticmethod
    def _flash_gamification_event(
        event_type: str, data: Dict[str, Any], user_id: int
    ) -> None:
        """
        Helper to flash event if suitable for current context.

        Only flashes if:
        1. We are in a Flask request context
        2. There is a logged-in user
        3. The event belongs to the current user (don't animate for others)
        """
        if not has_request_context():
            return

        if not current_user.is_authenticated:
            return

        if current_user.id != user_id:
            # Event is for another user, don't show animation to this user
            return

        if current_user.is_admin:
            # Admin users don't see gamification animations
            return

        try:
            payload = {"type": event_type, "data": data}
            # Use 'gamification_event' category to separate from normal alerts
            flash(json.dumps(payload), category="gamification_event")
            logger.debug(f"Flashed gamification event: {event_type}")
        except Exception as e:
            logger.error(f"Error flashing gamification event: {e}")

    @staticmethod
    @_only_in_request
    def handle_xp_gained(event: XPGainedEvent) -> None:
        """Send XP gain event to frontend."""
        # Only flash significant XP gains to avoid spam (e.g., > 0)
        if event.xp_amount <= 0:
            return

        # B21: narrative reason — describe the action, not the entity ID.
        reason = _("Hai guadagnato XP")
        if event.related_entities:
            if "match_id" in event.related_entities:
                reason = _("Per aver giocato la partita")
            elif "gara_id" in event.related_entities:
                reason = _("Per aver partecipato al torneo")
            elif "quest_id" in event.related_entities:
                reason = _("Per aver completato la quest")
            elif "achievement_id" in event.related_entities:
                reason = _("Per aver sbloccato un achievement")

        GamificationFrontendBridge._flash_gamification_event(
            "xp", {"amount": event.xp_amount, "reason": reason}, event.user_id
        )

    @staticmethod
    @_only_in_request
    def handle_level_up(event: LevelUpEvent) -> None:
        """Send level up event to frontend."""
        # B21: include total XP and unlocks summary so the toast is
        # self-contained. ADR-031: i LevelUnlock sono *feedback/ricompense* di
        # livello, non i gate reali (quelli sono FeatureConfig/ABAC, con codici
        # distinti). Evitiamo quindi "funzioni sbloccate", che sovra-prometteva
        # accesso a capacità non necessariamente concesse dal livello.
        unlock_count = len(event.unlocks) if event.unlocks else 0
        if unlock_count > 0:
            subtitle = _(
                "Hai accumulato %(xp)d XP totali — %(n)d nuove ricompense di livello!",
                xp=event.total_xp,
                n=unlock_count,
            )
        else:
            subtitle = _("Hai accumulato %(xp)d XP totali", xp=event.total_xp)

        GamificationFrontendBridge._flash_gamification_event(
            "levelup",
            {
                "level": event.new_level,
                "title": _("Livello %(level)d raggiunto!", level=event.new_level),
                "subtitle": subtitle,
            },
            event.user_id,
        )

    @staticmethod
    @_only_in_request
    def handle_achievement_unlocked(event: AchievementUnlockedEvent) -> None:
        """Send achievement event to frontend."""
        # B21: prefer the semantic achievement description (already i18n) when
        # present; fall back to a generic XP-only line.
        description = _get_achievement_description(event)
        GamificationFrontendBridge._flash_gamification_event(
            "achievement",
            {
                "name": event.achievement_name,
                "description": description,
                "rarity": event.achievement_difficulty.lower(),
                "icon": "🏆",
            },
            event.user_id,
        )

    @staticmethod
    @_only_in_request
    def handle_streak_milestone(event: StreakMilestoneEvent) -> None:
        """Send streak milestone event to frontend."""
        # B21: human-readable narrative — "filotto" used in pool jargon.
        if event.streak_type == "WEEKLY_MATCH":
            message = _(
                "Hai giocato per %(weeks)d settimane consecutive!",
                weeks=event.current_streak,
            )
        else:
            message = _(
                "Sei attivo da %(weeks)d settimane consecutive!",
                weeks=event.current_streak,
            )
        if event.freeze_earned > 0:
            message = message + " " + _("Hai guadagnato un congelatore!")

        GamificationFrontendBridge._flash_gamification_event(
            "streak",
            {
                "count": event.current_streak,
                "type": event.streak_type,
                "hasFreeze": event.freeze_earned > 0,
                "message": message,
            },
            event.user_id,
        )

    @staticmethod
    @_only_in_request
    def handle_streak_broken(event: StreakBrokenEvent) -> None:
        """Send streak lost event to frontend."""
        # B21 + B4: kept for back-compat but message i18n'd; B4 will remove
        # the bridge handler entirely.
        GamificationFrontendBridge._flash_gamification_event(
            "streak_lost",
            {
                "message": _(
                    "Hai perso una serie di %(weeks)d settimane.",
                    weeks=event.streak_length,
                )
            },
            event.user_id,
        )

    @staticmethod
    @_only_in_request
    def handle_quest_completed(event: QuestCompletedEvent) -> None:
        """Send quest completion event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "quest",
            {
                "name": _(event.quest_name),
                "description": _(
                    "Quest completata: %(name)s — +%(xp)d XP",
                    name=_(event.quest_name),
                    xp=event.xp_awarded,
                ),
            },
            event.user_id,
        )

    # B10: per-feature narrative copy for nudge toasts. The DB stores the
    # English code/name; we translate at toast-emission time so the user sees
    # an actionable Italian message ("vai alla classifica" rather than
    # "View Other Profiles").
    _NUDGE_COPY: Dict[str, Dict[str, str]] = {
        "view_other_profiles": {
            "name": "Scopri gli altri giocatori",
            "description": (
                "Ora puoi sbirciare i profili degli altri. "
                "Vai alla classifica per cominciare!"
            ),
        },
        "view_global_stats": {
            "name": "Statistiche globali",
            "description": "Confronta le tue performance con quelle della community.",
        },
        "create_match_direct": {
            "name": "Crea una partita diretta",
            "description": "Sfida un avversario specifico — proponi luogo e data.",
        },
        "create_match_community": {
            "name": "Proponi una partita aperta",
            "description": (
                "Lancia una proposta alla community e aspetta che "
                "qualcuno si faccia avanti."
            ),
        },
        "manage_availability": {
            "name": "Imposta la tua disponibilità",
            "description": (
                "Fai sapere quando sei libero così altri " "possono proporti partite."
            ),
        },
        "create_gara": {
            "name": "Organizza una gara",
            "description": "Sei pronto: puoi creare la tua prima gara standalone.",
        },
        "create_campionato": {
            "name": "Organizza un campionato",
            "description": "Crea una serie di gare e gestisci una stagione completa.",
        },
        "do_challenge": {
            "name": "Prova le sfide",
            "description": (
                "Allenati con drill mirati: "
                "ogni completamento conta per la classifica."
            ),
        },
    }

    @staticmethod
    @_only_in_request
    def handle_nudge_event(user_id: int, feature_config: Any) -> None:
        """
        Send nudge event to frontend.
        feature_config is expected to be a FeatureConfig model instance.
        """
        # ADR-028 alignment: don't promote a feature whose primary endpoint
        # is hidden by the production allowlist for the current user.
        from models.gamification.feature_endpoint_map import feature_visible_to_user

        if not feature_visible_to_user(feature_config.code, current_user):
            return

        # B10: prefer per-feature narrative copy over the raw DB strings
        # (which are English code names), wrapped in _() for i18n.
        copy = GamificationFrontendBridge._NUDGE_COPY.get(feature_config.code)
        name = _(copy["name"]) if copy else feature_config.name
        description = _(copy["description"]) if copy else feature_config.description

        GamificationFrontendBridge._flash_gamification_event(
            "nudge",
            {
                "code": feature_config.code,
                "name": name,
                "description": description,
                "badge": feature_config.badge_slug,
            },
            user_id,
        )

    #: Copy dei ruoli concedibili (ADR-041). Dizionario separato da
    #: ``_NUDGE_COPY`` di proposito: quello è indicizzato per **codice feature**,
    #: e un ruolo concesso non è una feature sbloccata. Le chiavi sono i valori
    #: di ``GrantableRole``.
    _ROLE_GRANTED_COPY: Dict[str, Dict[str, str]] = {
        "examiner": {
            "name": "Sei un esaminatore",
            "description": (
                "Ora puoi comporre esami e certificarli di persona. "
                "Dichiara le tue disponibilità per farti trovare."
            ),
        },
    }

    @staticmethod
    @_only_in_request
    def handle_role_granted_event(user_id: int, role: Any) -> None:
        """Toast di sblocco quando a qualcuno viene concesso un ruolo.

        Perché non riusare ``handle_feature_unlock_event``: la sua firma vuole
        una ``FeatureConfig``, e un ruolo **non è** una feature sbloccata.
        Costruirne una fittizia per far tornare i conti significherebbe
        inventare un codice che non esiste in ``feature_config`` — e quel codice
        finirebbe nel payload del toast, dove il frontend lo usa per
        identificare la feature.

        Il toast è dello stesso tipo (``unlock``, 🔓): per chi lo riceve è la
        stessa cosa, una porta che si apre.
        """
        role_value = getattr(role, "value", role)
        copy = GamificationFrontendBridge._ROLE_GRANTED_COPY.get(role_value)
        if copy is None:
            # Un ruolo senza copy non merita un toast muto o in inglese: meglio
            # il silenzio, finché qualcuno non gli scrive due righe.
            return

        GamificationFrontendBridge._flash_gamification_event(
            "unlock",
            {
                "code": f"role:{role_value}",
                "name": _(copy["name"]),
                "description": _(copy["description"]),
                "icon": "🔓",
            },
            user_id,
        )

    @staticmethod
    @_only_in_request
    def handle_feature_unlock_event(user_id: int, feature_config: Any) -> None:
        """
        Send feature unlock event to frontend.
        Typically triggered via manual flash or specific domain event.
        """
        # ADR-028 alignment: stay silent for features whose endpoint isn't
        # in the allowlist — celebrating an unlock the user can't act on
        # would be misleading.
        from models.gamification.feature_endpoint_map import feature_visible_to_user

        if not feature_visible_to_user(feature_config.code, current_user):
            return

        # B10: same narrative copy as the nudge — see _NUDGE_COPY above.
        copy = GamificationFrontendBridge._NUDGE_COPY.get(feature_config.code)
        name = _(copy["name"]) if copy else feature_config.name
        description = _(copy["description"]) if copy else feature_config.description

        GamificationFrontendBridge._flash_gamification_event(
            "unlock",
            {
                "code": feature_config.code,
                "name": name,
                "description": description,
                "icon": "🔓",
            },
            user_id,
        )


def _i18n_nudge_anchor() -> None:
    """Ancora di estrazione i18n per ``_NUDGE_COPY`` — **mai chiamata**.

    Le copy dei nudge vengono tradotte a emission-time con ``_(copy["name"])`` /
    ``_(copy["description"])``: passando una *variabile* a ``_()``, pybabel non
    riesce a estrarle staticamente, quindi senza questa ancora resterebbero in
    italiano anche in EN. Qui ripetiamo i literal (identici ai valori
    concatenati in ``_NUDGE_COPY``) dentro ``_()`` solo perché l'estrazione
    statica li includa nel catalogo. Non viene mai eseguita.
    """
    _("Scopri gli altri giocatori")
    _("Ora puoi sbirciare i profili degli altri. Vai alla classifica per cominciare!")
    _("Statistiche globali")
    _("Confronta le tue performance con quelle della community.")
    _("Crea una partita diretta")
    _("Sfida un avversario specifico — proponi luogo e data.")
    _("Proponi una partita aperta")
    _("Lancia una proposta alla community e aspetta che qualcuno si faccia avanti.")
    _("Imposta la tua disponibilità")
    _("Fai sapere quando sei libero così altri possono proporti partite.")
    _("Organizza una gara")
    _("Sei pronto: puoi creare la tua prima gara standalone.")
    _("Organizza un campionato")
    _("Crea una serie di gare e gestisci una stagione completa.")
    _("Prova le sfide")
    _("Allenati con drill mirati: ogni completamento conta per la classifica.")
    # _ROLE_GRANTED_COPY (ADR-041): stessa ragione, stessa ancora.
    _("Sei un esaminatore")
    _(
        "Ora puoi comporre esami e certificarli di persona. "
        "Dichiara le tue disponibilità per farti trovare."
    )


def _get_achievement_description(event: AchievementUnlockedEvent) -> str:
    """B21: prefer the achievement.description from DB (semantic, i18n-ready)
    over a generic "+XP - category" line. Falls back to the generic line if
    the achievement record is unavailable.
    """
    try:
        from models.gamification.models import Achievement
        from models.base import db

        achievement = db.session.get(Achievement, event.achievement_id)
        if achievement and achievement.description:
            return f"{achievement.description} — +{event.xp_awarded} XP"
    except Exception:
        # Avoid breaking the toast pipeline if DB access fails for any reason
        logger.debug(
            "Could not fetch achievement description; using fallback", exc_info=True
        )

    return _(
        "+%(xp)d XP — %(category)s",
        xp=event.xp_awarded,
        category=event.achievement_category.capitalize(),
    )


# Auto-register handlers
GamificationFrontendBridge.register_all_handlers()


def flash_gamification_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Public API to trigger a gamification frontend event manually.
    Useful for events not triggered by domain events, like "Welcome".
    """
    if not has_request_context() or not current_user.is_authenticated:
        return

    if current_user.is_admin:
        return

    try:
        payload = {"type": event_type, "data": data}
        flash(json.dumps(payload), category="gamification_event")
        logger.debug(f"Manually flashed gamification event: {event_type}")
    except Exception as e:
        logger.error(f"Error manually flashing gamification event: {e}")
