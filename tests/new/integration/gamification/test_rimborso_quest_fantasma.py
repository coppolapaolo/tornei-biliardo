"""Il rimborso degli XP delle quest-fantasma (seguito di PR #191).

Il fix ha fermato i completamenti moltiplicati; questo ripara il pregresso:
partecipazioni nate DOPO la chiusura della quest (l'arruolamento d'ufficio su
settimane già finite) e le transazioni XP che hanno fruttato. La firma è
temporale — `created_at > quest.end_date` — perché chi giocava durante la
settimana veniva arruolato allora: un'iscrizione posteriore alla finestra non
può essere legittima.
"""

from datetime import timedelta

from models.base import db, utc_now
from models.gamification.models import (
    Quest,
    QuestParticipation,
    UserLevel,
    XPTransaction,
    XPTransactionType,
)
from models.gamification.level_service import LevelService
from models.gamification.quest_repair import (
    find_ghost_participations,
    repair_ghost_participations,
)
from models.gamification.quest_seeds import seed_weekly_quests


def _stato_di_produzione(giocatore):
    """Ricrea il pregresso: una quest della settimana scorsa completata come
    fantasma (dopo la chiusura), e una della settimana corrente completata
    legittimamente. Il fantasma si fabbrica come faceva il bug: iscrizione e
    completamento OGGI su una finestra già chiusa."""
    oggi = utc_now().date()
    seed_weekly_quests(db.session, reference_date=oggi - timedelta(weeks=1))
    seed_weekly_quests(db.session, reference_date=oggi)
    quests = Quest.query.order_by(Quest.start_date).all()
    vecchia = next(q for q in quests if "Vinci" in q.name and q.end_date < utc_now())
    corrente = next(q for q in quests if "Vinci" in q.name and q.end_date >= utc_now())

    def completa(quest):
        p = QuestParticipation(
            user_id=giocatore.id,
            quest_id=quest.id,
            current_progress=1,
            target_progress=1,
            is_completed=True,
            completed_at=utc_now(),
            xp_awarded=quest.xp_reward,
        )
        db.session.add(p)
        quest.participant_count += 1
        quest.completion_count += 1
        LevelService.award_xp(
            user_id=giocatore.id,
            xp_amount=quest.xp_reward,
            transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
            reason=f"Completed quest: {quest.name}",
            related_entities={"quest_id": quest.id, "quest_name": quest.name},
        )
        return p

    fantasma = completa(vecchia)
    # La legittima: stessa meccanica, ma la finestra della quest è aperta e
    # l'iscrizione cade dentro (created_at = adesso <= end_date).
    legittima = completa(corrente)
    db.session.commit()
    return vecchia, corrente, fantasma, legittima


def test_il_dry_run_trova_solo_il_fantasma(db_session, isolated_players):
    giocatore = isolated_players[0]
    vecchia, corrente, fantasma, legittima = _stato_di_produzione(giocatore)

    trovati = find_ghost_participations()

    assert [g.participation_id for g in trovati] == [fantasma.id]
    assert trovati[0].completed is True
    assert trovati[0].xp_awarded == vecchia.xp_reward
    assert len(trovati[0].transaction_ids) == 1


def test_il_rimborso_toglie_il_fantasma_e_ricostruisce_il_livello(
    db_session, isolated_players
):
    giocatore = isolated_players[0]
    vecchia, corrente, fantasma, legittima = _stato_di_produzione(giocatore)
    xp_prima = db.session.get(UserLevel, giocatore.id).total_xp

    report = repair_ghost_participations()
    db.session.commit()

    assert report["participations_removed"] == 1
    assert report["transactions_removed"] == 1
    assert report["xp_reclaimed"] == vecchia.xp_reward
    assert report["users_rebuilt"] == 1

    # La partecipazione legittima e i suoi XP restano; il livello riflette
    # solo quelli.
    superstiti = QuestParticipation.query.filter_by(user_id=giocatore.id).all()
    assert [p.quest_id for p in superstiti] == [corrente.id]
    livello = db.session.get(UserLevel, giocatore.id)
    assert livello.total_xp == xp_prima - vecchia.xp_reward
    transazioni = XPTransaction.query.filter_by(user_id=giocatore.id).all()
    assert all(
        f'"quest_id": {vecchia.id}' not in (t.related_entities or "")
        for t in transazioni
    )
    # Contatori della quest vecchia rientrati.
    assert vecchia.participant_count == 0
    assert vecchia.completion_count == 0

    # Idempotente: il secondo giro non trova più niente.
    assert find_ghost_participations() == []
    report2 = repair_ghost_participations()
    assert report2["participations_removed"] == 0


def test_una_iscrizione_fantasma_mai_completata_si_toglie_senza_xp(
    db_session, isolated_players
):
    giocatore = isolated_players[0]
    oggi = utc_now().date()
    seed_weekly_quests(db.session, reference_date=oggi - timedelta(weeks=1))
    vecchia = Quest.query.filter(Quest.name.contains("gioca 3")).first()
    db.session.add(
        QuestParticipation(
            user_id=giocatore.id,
            quest_id=vecchia.id,
            current_progress=1,
            target_progress=3,
            is_completed=False,
            xp_awarded=0,
        )
    )
    vecchia.participant_count += 1
    db.session.commit()

    report = repair_ghost_participations()
    db.session.commit()

    assert report["participations_removed"] == 1
    assert report["transactions_removed"] == 0
    assert report["xp_reclaimed"] == 0
    assert QuestParticipation.query.count() == 0
