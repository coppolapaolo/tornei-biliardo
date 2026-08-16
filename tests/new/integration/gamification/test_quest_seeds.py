"""Integration tests per il seeding delle quest personali settimanali."""

from datetime import date, datetime, time, timedelta


from models.base import db
from models.gamification.quest_seeds import (
    seed_weekly_quests,
    PERSONAL_WEEKLY_QUESTS,
)
from models.gamification.models import Quest, QuestStatus, QuestType


class TestSeedWeeklyQuests:
    def test_seeds_current_week_quests_active(self, db_session):
        ref = date(2026, 6, 3)  # mercoledì
        created = seed_weekly_quests(db.session, reference_date=ref)
        assert created == len(PERSONAL_WEEKLY_QUESTS)

        quests = Quest.query.all()
        assert len(quests) == len(PERSONAL_WEEKLY_QUESTS)

        # Finestra = lunedì..domenica della settimana ISO di ref.
        monday = datetime.combine(date(2026, 6, 1), time.min)
        sunday = datetime.combine(date(2026, 6, 7), time.max)
        for q in quests:
            assert q.quest_type == QuestType.WEEKLY
            assert q.start_date == monday
            assert q.end_date == sunday
            # Lo status effettivo è ACTIVE se "oggi" cade nella finestra; qui ref
            # è nel passato, quindi verifichiamo che le date siano corrette e che
            # effective_status sia coerente (EXPIRED dato che la finestra è chiusa).
            assert q.effective_status in (QuestStatus.ACTIVE, QuestStatus.EXPIRED)

    def test_idempotent_same_week(self, db_session):
        ref = date(2026, 6, 3)
        first = seed_weekly_quests(db.session, reference_date=ref)
        second = seed_weekly_quests(db.session, reference_date=ref)
        assert first == len(PERSONAL_WEEKLY_QUESTS)
        assert second == 0  # nessun duplicato
        assert Quest.query.count() == len(PERSONAL_WEEKLY_QUESTS)

    def test_new_week_creates_fresh_quests(self, db_session):
        week1 = date(2026, 6, 3)
        week2 = week1 + timedelta(days=7)
        seed_weekly_quests(db.session, reference_date=week1)
        created_week2 = seed_weekly_quests(db.session, reference_date=week2)
        assert created_week2 == len(PERSONAL_WEEKLY_QUESTS)
        assert Quest.query.count() == 2 * len(PERSONAL_WEEKLY_QUESTS)

    def test_requirements_use_cabled_activity_types(self, db_session):
        """Le quest seed devono usare solo activity_type cablati agli eventi."""
        import json

        cabled = {
            "matches_played",
            "matches_won",
            "tournaments_registered",
            "tournaments_completed",
        }
        seed_weekly_quests(db.session, reference_date=date(2026, 6, 3))
        for q in Quest.query.all():
            req_type = json.loads(q.requirements)["type"]
            assert (
                req_type in cabled
            ), f"quest '{q.name}' usa tipo non cablato {req_type}"


class TestSeededQuestProgresses:
    def test_active_seeded_quest_progresses_via_record_activity(
        self, db_session, isolated_players
    ):
        """Una quest seed ATTIVA progredisce con record_activity_for_quests."""
        from models.gamification.quest_service import QuestService

        # Settimana corrente → ACTIVE.
        seed_weekly_quests(db.session, reference_date=None)
        player = isolated_players[0]

        results = QuestService.record_activity_for_quests(
            user_id=player.id, activity_type="matches_played", activity_count=1
        )
        # Almeno la quest "gioca 3 partite" deve risultare tra quelle toccate.
        touched_names = {q.name for q, _ in results}
        assert any("gioca 3 partite" in n for n in touched_names)
