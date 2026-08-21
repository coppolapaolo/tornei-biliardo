"""Le quest delle settimane passate non devono più incassare progressi.

GlitchTip no, error log sì (2026-08-19/20): utenti che «completano» tre volte
la stessa quest settimanale nello stesso secondo, con XP triplicati:

    User 65 joined quest 'Vinci una partita questa settimana'
    User 65 completed quest '...' (+60 XP)      <- per tre volte di fila

Il meccanismo: `seed_weekly_quests` crea a ogni settimana ISO le sue quest con
`status=ACTIVE` **in colonna**, e nessuno le spegne mai — per progetto lo stato
vero si deriva dalle date (`Quest.effective_status`), perché
`update_quest_statuses()` non ha uno scheduler che lo chiami. Ma
`record_activity_for_quests`, il punto caldo chiamato a ogni partita, filtrava
per **colonna**: ogni settimana il seed aggiungeva due quest nuove e le vecchie
restavano pescabili per sempre. Un utente alla prima vittoria si iscriveva
d'ufficio alla quest di OGNI settimana seminata e le completava tutte in un
colpo: il moltiplicatore degli XP cresceva di uno a settimana (era ×3 alla
terza settimana dal varo).
"""

from datetime import timedelta

from models.base import db, utc_now
from models.gamification.models import Quest, QuestParticipation, XPTransaction
from models.gamification.quest_seeds import seed_weekly_quests
from models.gamification.quest_service import QuestService


def _semina_tre_settimane():
    """Il DB come lo trovava la produzione: tre settimane di quest, TUTTE con
    la colonna status=ACTIVE.

    Non basta seminare le settimane passate: `create_quest` deriva lo status
    dalle date **alla creazione**, quindi seminate oggi nascerebbero EXPIRED e
    il guasto sparirebbe dal test. In produzione invece sono nate ACTIVE
    durante la loro settimana (il seed gira a ogni avvio dell'app) e nessuno
    le ha mai spente: qui si riproduce esattamente quello stato.
    """
    from models.gamification.models import QuestStatus

    oggi = utc_now().date()
    for settimane_fa in (2, 1, 0):
        seed_weekly_quests(
            db.session, reference_date=oggi - timedelta(weeks=settimane_fa)
        )
    for quest in Quest.query.all():
        quest.status = QuestStatus.ACTIVE
    db.session.commit()
    return Quest.query.count()


def test_una_vittoria_completa_solo_la_quest_della_settimana_corrente(
    db_session, isolated_players
):
    giocatore = isolated_players[0]
    totali = _semina_tre_settimane()
    assert totali == 6  # 2 quest x 3 settimane: lo scenario del guasto

    esiti = QuestService.record_activity_for_quests(
        user_id=giocatore.id, activity_type="matches_won", activity_count=1
    )
    db.session.commit()

    completate = [quest for quest, appena_completata in esiti if appena_completata]
    assert len(completate) == 1, (
        "una vittoria deve completare la quest di QUESTA settimana, "
        f"non di tutte le settimane seminate (completate: {len(completate)})"
    )

    # L'iscrizione d'ufficio vale solo per la settimana in corso: le quest
    # scadute non devono nemmeno arruolare.
    partecipazioni = QuestParticipation.query.filter_by(user_id=giocatore.id).count()
    assert partecipazioni == 1

    # E gli XP sono quelli di UNA quest, non il triplo.
    xp_quest = (
        db.session.query(XPTransaction)
        .filter_by(user_id=giocatore.id)
        .filter(XPTransaction.reason.contains("Vinci una partita"))
        .all()
    )
    assert len(xp_quest) == 1


def test_join_esplicito_su_quest_scaduta_viene_rifiutato(db_session, isolated_players):
    giocatore = isolated_players[0]
    from models.gamification.models import QuestStatus

    oggi = utc_now().date()
    seed_weekly_quests(db.session, reference_date=oggi - timedelta(weeks=1))
    # Come in produzione: nata ACTIVE durante la sua settimana, mai spenta.
    scaduta = Quest.query.first()
    scaduta.status = QuestStatus.ACTIVE
    db.session.commit()

    import pytest

    with pytest.raises(ValueError):
        QuestService.join_quest(giocatore.id, scaduta.id)


def test_la_manutenzione_all_avvio_spegne_le_settimane_passate(db_session):
    """`seed_weekly_quests` gira a ogni avvio dell'app: oltre a seminare la
    settimana nuova deve spegnere in colonna quelle finite, così anche le
    query per colonna (liste, UI) tornano a dire il vero — ed è questo che
    ripara da solo il DB di produzione al primo avvio dopo il fix."""
    from models.gamification.models import QuestStatus

    oggi = utc_now().date()
    seed_weekly_quests(db.session, reference_date=oggi - timedelta(weeks=1))
    for quest in Quest.query.all():  # come in produzione: nate ACTIVE
        quest.status = QuestStatus.ACTIVE
    db.session.commit()
    assert Quest.query.filter_by(status=QuestStatus.ACTIVE).count() == 2

    seed_weekly_quests(db.session, reference_date=oggi)
    db.session.commit()

    # Le sole ACTIVE rimaste sono quelle della settimana corrente.
    attive = Quest.query.filter_by(status=QuestStatus.ACTIVE).all()
    assert len(attive) == 2
    assert all(q.start_date <= utc_now() <= q.end_date for q in attive)
