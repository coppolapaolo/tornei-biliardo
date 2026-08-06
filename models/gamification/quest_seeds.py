"""Quest Seeds — quest personali ricorrenti (loop di abitudine).

Source: GAMIFICATION_V3 §11-ter. Niente confronto sociale: sono obiettivi
**personali** settimanali ("gioca N partite", "vinci una partita") che tengono
vivo il loop di ritorno senza pressione competitiva.

Recurrence senza cron: `seed_weekly_quests` crea (in modo idempotente) le quest
della **settimana ISO corrente**. Chiamato all'avvio dell'app (che su
PythonAnywhere si ricarica ~quotidianamente), garantisce che la settimana in
corso abbia sempre le sue quest. Lo status ACTIVE/EXPIRED è poi derivato dalle
date a read-time (`Quest.effective_status`, vedi quest_service) → nessuno
scheduler necessario.

I `type` dei requisiti devono essere tra quelli cablati agli eventi in
`event_handlers` (matches_played, matches_won, tournaments_registered,
tournaments_completed), altrimenti la quest non progredirebbe.

Nota visibilità: l'esposizione delle quest agli utenti resta gated (ADR-028,
maturity-gate director) finché non validata; il seeding non cambia la
visibilità.
"""

from __future__ import annotations

from datetime import datetime, timedelta, time, date
from typing import Optional

from flask_babel import gettext as _

from models.base import utc_now
from models.gamification.models import Quest, QuestType


def _i18n_extraction_anchor() -> None:
    """Ancora di estrazione i18n — **mai chiamata**.

    Le quest seed memorizzano in DB le stringhe IT *sorgente* (vedi
    PERSONAL_WEEKLY_QUESTS): non possiamo tradurle al seed perché gira
    all'avvio, fuori da un request context (gettext solleverebbe). La
    traduzione avviene quindi a **display-time** nei template con `_(quest.name)`
    / `_(quest.description)`. Qui ripetiamo i literal dentro `_()` solo perché
    pybabel (estrazione statica) li includa nel catalogo. Questa funzione non
    viene mai eseguita: serve unicamente come ancora di estrazione.
    """
    _("Sfida settimanale: gioca 3 partite")
    _("Gioca 3 partite questa settimana per mantenere il ritmo.")
    _("Vinci una partita questa settimana")
    _("Conquista almeno una vittoria questa settimana.")


# Template delle quest personali settimanali. `key` è solo interno; il `name`
# include il periodo per essere univoco e idempotente settimana per settimana.
# I `name`/`description` sono le stringhe IT *sorgente* (msgid): restano stabili
# in DB (idempotenza del seed) e vengono tradotti a display-time, vedi
# `_i18n_extraction_anchor` sopra.
PERSONAL_WEEKLY_QUESTS = [
    {
        "name": "Sfida settimanale: gioca 3 partite",
        "description": "Gioca 3 partite questa settimana per mantenere il ritmo.",
        "requirements": {"type": "matches_played", "target": 3},
        "xp_reward": 80,
    },
    {
        "name": "Vinci una partita questa settimana",
        "description": "Conquista almeno una vittoria questa settimana.",
        "requirements": {"type": "matches_won", "target": 1},
        "xp_reward": 60,
    },
]


def _iso_week_window(reference: date) -> tuple[datetime, datetime]:
    """Finestra [lunedì 00:00:00, domenica 23:59:59.999999] della settimana ISO."""
    monday = reference - timedelta(days=reference.weekday())
    start = datetime.combine(monday, time.min)
    end = datetime.combine(monday + timedelta(days=6), time.max)
    return start, end


def seed_weekly_quests(db_session, reference_date: Optional[date] = None) -> int:
    """Crea (idempotente) le quest personali della settimana ISO corrente.

    Args:
        db_session: sessione SQLAlchemy.
        reference_date: data di riferimento (default: oggi UTC) — utile nei test.

    Returns:
        Numero di quest create in questa invocazione.
    """
    from models.gamification.quest_service import QuestService

    ref = reference_date or utc_now().date()
    start, end = _iso_week_window(ref)

    created = 0
    for template in PERSONAL_WEEKLY_QUESTS:
        # Idempotenza per settimana: stessa coppia (name, start_date).
        existing = Quest.query.filter_by(
            name=template["name"], start_date=start
        ).first()
        if existing:
            continue

        QuestService.create_quest(
            name=template["name"],
            description=template["description"],
            quest_type=QuestType.WEEKLY,
            start_date=start,
            end_date=end,
            requirements=template["requirements"],
            xp_reward=template["xp_reward"],
        )
        created += 1

    return created
