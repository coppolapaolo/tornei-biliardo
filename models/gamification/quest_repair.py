"""Riparazione dei completamenti-fantasma delle quest settimanali.

Il difetto (corretto in `record_activity_for_quests`, PR #191): le quest delle
settimane passate restavano `ACTIVE` in colonna e arruolavano d'ufficio chi
faceva attività, che le «completava» tutte in un colpo con gli XP moltiplicati.

Questo modulo toglie ciò che quel difetto ha prodotto. La firma di un
artefatto è **temporale**, e per questo inequivocabile: una partecipazione
nata *dopo* la chiusura della finestra della quest (`created_at > end_date`)
non può essere stata un'iscrizione legittima — l'arruolamento automatico
avviene solo giocando, e chi giocava *durante* la settimana veniva arruolato
allora. Ne discendono due categorie:

- partecipazioni fantasma **completate**: si toglie la partecipazione e la
  transazione XP che ha fruttato (individuata per utente + `quest_id` nel
  `related_entities` del ledger);
- partecipazioni fantasma **non completate** (es. «gioca 3 partite» a 1/3):
  nessun XP di mezzo, si toglie solo la riga.

Dopo la pulizia, lo stato derivato di ogni utente toccato si ricostruisce con
`GamificationRecalcService.rebuild_for_user`: il livello torna alla somma del
ledger ripulito, e `_rebuild_quests` non può resuscitare i fantasmi perché
ricalcola solo le partecipazioni esistenti, dentro la loro finestra.

Limite dichiarato: i traguardi già sbloccati **restano** anche se il livello
scende sotto la soglia che li aveva concessi — è la scelta di
`_rebuild_achievements` («existing unlocks are always preserved») e non la si
scavalca da qui. Il report li elenca, la decisione è di prodotto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List

from models.base import db
from models.gamification.models import (
    Quest,
    QuestParticipation,
    XPTransaction,
    XPTransactionType,
)
from models.transaction.manager import transactional

logger = logging.getLogger(__name__)


@dataclass
class GhostParticipation:
    """Una partecipazione nata dopo la chiusura della quest."""

    participation_id: int
    user_id: int
    quest_id: int
    quest_name: str
    quest_week_start: str
    completed: bool
    xp_awarded: int
    transaction_ids: List[int] = field(default_factory=list)


def find_ghost_participations() -> List[GhostParticipation]:
    """Elenca gli artefatti, senza toccare nulla (è la base del dry-run)."""
    rows = (
        db.session.query(QuestParticipation, Quest)
        .join(Quest, Quest.id == QuestParticipation.quest_id)
        .filter(QuestParticipation.created_at > Quest.end_date)
        .order_by(QuestParticipation.user_id, Quest.start_date)
        .all()
    )

    ghosts: List[GhostParticipation] = []
    for participation, quest in rows:
        transaction_ids: List[int] = []
        if participation.is_completed and participation.xp_awarded:
            # `related_entities` è testo JSON: si filtra in Python sui soli
            # candidati plausibili (stesso utente, stesso tipo) — sono pochi.
            candidates = XPTransaction.query.filter_by(
                user_id=participation.user_id,
                transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
            ).all()
            for tx in candidates:
                try:
                    related = json.loads(tx.related_entities or "{}")
                except (ValueError, TypeError):
                    continue
                if related.get("quest_id") == quest.id:
                    transaction_ids.append(tx.id)

        ghosts.append(
            GhostParticipation(
                participation_id=participation.id,
                user_id=participation.user_id,
                quest_id=quest.id,
                quest_name=quest.name,
                quest_week_start=str(quest.start_date.date()),
                completed=bool(participation.is_completed),
                xp_awarded=int(participation.xp_awarded or 0),
                transaction_ids=transaction_ids,
            )
        )
    return ghosts


@transactional(domain="gamification")
def repair_ghost_participations() -> Dict[str, int]:
    """Toglie gli artefatti e ricostruisce gli utenti toccati.

    Idempotente: al secondo giro non trova più niente. Ritorna i contatori
    del lavoro fatto.
    """
    from models.gamification.recalc_service import GamificationRecalcService

    ghosts = find_ghost_participations()

    removed_participations = 0
    removed_transactions = 0
    xp_reclaimed = 0
    users = sorted({g.user_id for g in ghosts})

    for ghost in ghosts:
        for tx_id in ghost.transaction_ids:
            tx = db.session.get(XPTransaction, tx_id)
            if tx is not None:
                xp_reclaimed += int(tx.xp_amount)
                db.session.delete(tx)
                removed_transactions += 1

        participation = db.session.get(QuestParticipation, ghost.participation_id)
        if participation is None:
            continue
        quest = db.session.get(Quest, ghost.quest_id)
        if quest is not None:
            quest.participant_count = max(0, quest.participant_count - 1)
            if participation.is_completed:
                quest.completion_count = max(0, quest.completion_count - 1)
        db.session.delete(participation)
        removed_participations += 1

    db.session.flush()

    for user_id in users:
        GamificationRecalcService.rebuild_for_user(user_id)

    logger.info(
        "Riparazione quest fantasma: %s partecipazioni e %s transazioni rimosse, "
        "%s XP rientrati, %s utenti ricostruiti",
        removed_participations,
        removed_transactions,
        xp_reclaimed,
        len(users),
    )
    return {
        "participations_removed": removed_participations,
        "transactions_removed": removed_transactions,
        "xp_reclaimed": xp_reclaimed,
        "users_rebuilt": len(users),
    }
