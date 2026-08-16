"""
Integration tests per l'attivazione/disattivazione degli achievement.

I badge bloccati-per-sempre demotivano e non vanno mostrati: si usa
`is_active=False` (già filtrato da AchievementService; `is_hidden` mostra solo
"???"). Dopo il re-engineering metric-driven (Fase 2) TUTTI gli achievement
hanno una sorgente dati reale → `UNOBTAINABLE_ACHIEVEMENT_SLUGS` è vuoto e nessun
badge resta disattivato. Lo stato sui DB esistenti è ottenuto dalle migrazioni
20260605 (disattiva 12) + 20260606 (riattiva 4) + 20260607 (riattiva 8).
"""

from models.base import db
from models.gamification.achievement_seeds import (
    seed_achievements,
    UNOBTAINABLE_ACHIEVEMENT_SLUGS,
)
from models.gamification.achievement_service import AchievementService
from models.gamification.models import Achievement


class TestAllAchievementsObtainable:
    def test_unobtainable_set_is_empty(self):
        """Dopo il re-engineering metric-driven nessun achievement è non ottenibile."""
        assert UNOBTAINABLE_ACHIEVEMENT_SLUGS == frozenset()

    def test_seed_leaves_all_achievements_active(self, db_session):
        """
        Dopo il seed, tutti gli achievement (anche gli ex-disattivati) sono attivi.
        """
        seed_achievements(db.session)

        # Gli 8 ultimi riattivati + alcuni rappresentativi.
        for slug in (
            "hot_streak",
            "unstoppable",
            "category_climber",
            "elite_player",
            "strategy_explorer",
            "challenge_master",
            "perfectionist",
            "drill_addict",
            "social_butterfly",
            "champion",
            "first_blood",
        ):
            ach = Achievement.query.filter_by(slug=slug).first()
            assert ach is not None, f"Seed mancante: {slug}"
            assert ach.is_active is True, f"{slug} dovrebbe essere attivo"

        # Nessun achievement seminato disattivato.
        assert Achievement.query.filter_by(is_active=False).count() == 0

    def test_service_includes_formerly_disabled(self, db_session, isolated_players):
        """get_user_achievements ora include anche gli ex-disattivati."""
        seed_achievements(db.session)
        player = isolated_players[0]

        achievements = AchievementService.get_user_achievements(player.id)
        returned_slugs = {a["achievement"].slug for a in achievements}

        for slug in (
            "hot_streak",
            "strategy_explorer",
            "challenge_master",
            "category_climber",
            "first_blood",
        ):
            assert slug in returned_slugs


class TestSeedMigrationConsistency:
    def test_seed_and_migration_net_state_match(self):
        """
        Lo stato netto delle migrazioni (DB esistenti) deve coincidere col set
        dei seed (nuovi DB):
            disattivati(20260605) − riattivati(20260606) − riattivati(20260607)
            == UNOBTAINABLE_ACHIEVEMENT_SLUGS (vuoto).
        Così i due percorsi non divergono nel tempo.
        """
        import importlib.util
        from pathlib import Path

        migrations_dir = Path(__file__).resolve().parents[4] / "migrations"

        def _load(filename: str):
            path = migrations_dir / filename
            spec = importlib.util.spec_from_file_location(f"_mig_{filename}", path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        disabled = set(
            _load(
                "20260605_disable_unobtainable_achievements.py"
            ).UNOBTAINABLE_ACHIEVEMENT_SLUGS
        )
        reactivated_social = set(
            _load(
                "20260606_reactivate_social_achievements.py"
            ).REACTIVATED_ACHIEVEMENT_SLUGS
        )
        reactivated_rest = set(
            _load(
                "20260607_reactivate_remaining_achievements.py"
            ).REACTIVATED_ACHIEVEMENT_SLUGS
        )

        reactivated = reactivated_social | reactivated_rest
        # nessuna sovrapposizione tra le due riattivazioni
        assert reactivated_social.isdisjoint(reactivated_rest)
        # i riattivati erano stati disattivati
        assert reactivated <= disabled
        # stato netto == set dei seed (vuoto)
        assert (disabled - reactivated) == set(UNOBTAINABLE_ACHIEVEMENT_SLUGS)
