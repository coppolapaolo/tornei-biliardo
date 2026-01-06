"""
Notification Templates for i18n Support

This module defines translatable notification templates.
Templates are stored as message keys that get translated at display time,
enabling proper language switching.

Each template has:
- title: Title message key (short)
- message: Body message key (can contain %(param)s placeholders)
- action_text: Button text (optional)

Usage:
    from models.notification.templates import NOTIFICATION_TEMPLATES

    template = NOTIFICATION_TEMPLATES.get("achievement.unlocked")
    # template = {"title": "Achievement Sbloccato!", "message": "...", ...}

Note on i18n:
    We use lazy_gettext (_l) for strings defined at module level.
    These get translated at access time, not import time, so they
    respect the user's current language setting.
"""

from flask_babel import lazy_gettext as _l

# Gamification Notifications
# ==========================

NOTIFICATION_TEMPLATES = {
    # Achievement unlocked
    "achievement.unlocked": {
        "title": "Achievement Sbloccato!",
        "message": "Hai ottenuto '%(name)s' (%(difficulty)s)! +%(xp)d XP",
        "action_text": "Visualizza Achievement",
    },

    # Level up
    "gamification.level_up": {
        "title": "Livello %(level)d Raggiunto!",
        "message": "Congratulazioni! Hai raggiunto il livello %(level)d!%(unlocks)s",
        "action_text": "Visualizza Progressi",
    },

    # Streak milestone
    "gamification.streak_milestone": {
        "title": "Streak di %(weeks)d Settimane!",
        "message": "Incredibile! Hai mantenuto il tuo streak di %(type)s per %(weeks)d settimane consecutive!%(freeze)s +%(xp)d XP",
        "action_text": "Visualizza Streak",
    },

    # Quest completed
    "gamification.quest_completed": {
        "title": "Quest Completata!",
        "message": "Hai completato la quest %(type)s '%(name)s'! +%(xp)d XP",
        "action_text": "Visualizza Quests",
    },

    # Match Notifications
    # ===================

    "match.proposal_received": {
        "title": "Nuova Proposta di Partita",
        "message": "%(proposer)s ti ha invitato a giocare presso %(location)s",
        "action_text": "Visualizza Proposta",
    },

    "match.proposal_accepted": {
        "title": "Proposta Accettata!",
        "message": "%(accepter)s ha accettato la tua proposta di partita",
        "action_text": "Visualizza Dettagli",
    },

    "match.proposal_declined": {
        "title": "Proposta Rifiutata",
        "message": "%(decliner)s ha rifiutato la tua proposta di partita",
        "action_text": "Visualizza",
    },

    # Tournament Notifications
    # ========================

    "tournament.inscription_confirmed": {
        "title": "Iscrizione Confermata",
        "message": "Sei iscritto a '%(tournament_name)s'",
        "action_text": "Visualizza Gara",
    },

    "tournament.starting_soon": {
        "title": "Gara in Partenza",
        "message": "La gara '%(tournament_name)s' inizia tra poco!",
        "action_text": "Vai alla Gara",
    },

    "tournament.match_ready": {
        "title": "Partita Pronta",
        "message": "La tua partita contro %(opponent)s è pronta al tavolo %(table)s",
        "action_text": "Visualizza Partita",
    },

    "tournament.round_completed": {
        "title": "Round Completato",
        "message": "Il round %(round)d di '%(tournament_name)s' è terminato",
        "action_text": "Visualizza Classifica",
    },

    # Director/Admin Notifications
    # ============================

    "admin.director_request": {
        "title": "Nuova Richiesta Direttore",
        "message": "%(username)s ha richiesto di diventare direttore",
        "action_text": "Gestisci Richiesta",
    },

    "admin.venue_manager_request": {
        "title": "Nuova Richiesta Gestore Sala",
        "message": "%(username)s ha richiesto di gestire '%(venue_name)s'",
        "action_text": "Gestisci Richiesta",
    },

    # User Notifications
    # ==================

    "user.director_approved": {
        "title": "Richiesta Approvata!",
        "message": "Sei stato promosso a Direttore. Ora puoi creare e gestire tornei.",
        "action_text": "Inizia",
    },

    "user.director_rejected": {
        "title": "Richiesta Non Approvata",
        "message": "La tua richiesta di diventare direttore non è stata approvata.%(notes)s",
        "action_text": "Dettagli",
    },

    "user.venue_manager_approved": {
        "title": "Richiesta Approvata!",
        "message": "Sei stato nominato gestore di '%(venue_name)s'",
        "action_text": "Gestisci Sala",
    },
}


# Difficulty level translations for achievements
# These are used as values in template params, not as template keys
# Using lazy_gettext (_l) for i18n support at display time
DIFFICULTY_LABELS = {
    "common": _l("Livello Comune"),
    "uncommon": _l("Livello Non Comune"),
    "rare": _l("Livello Raro"),
    "epic": _l("Livello Epico"),
    "legendary": _l("Livello Leggendario"),
}


# Streak type translations
STREAK_TYPE_LABELS = {
    "weekly_activity": _l("attività"),
    "weekly_match": _l("partite"),
    "weekly_tournament": _l("tornei"),
    "weekly_drill": _l("allenamenti"),
}


# Quest type translations
QUEST_TYPE_LABELS = {
    "weekly": _l("Settimanale"),
    "monthly": _l("Mensile"),
    "special_event": _l("Evento Speciale"),
}


def get_template(template_key: str) -> dict:
    """Get a notification template by key.

    Args:
        template_key: Template identifier (e.g., "achievement.unlocked")

    Returns:
        Template dict with title, message, action_text keys.
        Returns empty dict if template not found.
    """
    return NOTIFICATION_TEMPLATES.get(template_key, {})


def get_difficulty_label(difficulty: str) -> str:
    """Get translated difficulty label.

    Args:
        difficulty: Difficulty value (common, uncommon, rare, epic, legendary)

    Returns:
        Translated label like "Livello Comune" (IT) or "Common Level" (EN)
    """
    label = DIFFICULTY_LABELS.get(difficulty, difficulty)
    return str(label)  # Convert LazyString to str


def get_streak_type_label(streak_type: str) -> str:
    """Get translated streak type label."""
    label = STREAK_TYPE_LABELS.get(streak_type, streak_type)
    return str(label)  # Convert LazyString to str


def get_quest_type_label(quest_type: str) -> str:
    """Get translated quest type label."""
    label = QUEST_TYPE_LABELS.get(quest_type, quest_type)
    return str(label)  # Convert LazyString to str
