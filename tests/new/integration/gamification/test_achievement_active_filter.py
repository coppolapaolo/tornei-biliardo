"""
Integration tests per la disattivazione degli achievement non ottenibili.

Fase 1 / Task B (vedi GAMIFICATION_V3_HANDOFF.md): i badge bloccati-per-sempre
demotivano e non vanno mostrati. `is_hidden` non li nasconde davvero (il service
mostra "???"), quindi si usa `is_active=False` — già filtrato da
AchievementService.

Set disattivato = i 2 stub di requisito sempre False (`win_streak`,
`category_reached` → 4 achievement) + 8 progress-based mai incrementati.
"""

import pytest

from models.base import db
from models.gamification.achievement_seeds import (
    seed_achievements,
    UNOBTAINABLE_ACHIEVEMENT_SLUGS,
)
from models.gamification.achievement_service import AchievementService
from models.gamification.models import Achievement


class TestUnobtainableAchievementsDisabled:
    def test_seed_marks_unobtainable_as_inactive(self, db_session):
        """Dopo il seed, gli achievement non ottenibili hanno is_active=False."""
        seed_achievements(db.session)

        for slug in UNOBTAINABLE_ACHIEVEMENT_SLUGS:
            ach = Achievement.query.filter_by(slug=slug).first()
            assert ach is not None, f"Seed mancante: {slug}"
            assert ach.is_active is False, f"{slug} dovrebbe essere disattivato"

    def test_obtainable_achievements_stay_active(self, db_session):
        """Gli achievement cablati e funzionanti restano attivi.

        Include i 4 social/avversari resi metric-driven e cablati agli eventi.
        """
        seed_achievements(db.session)

        for slug in (
            "first_blood",
            "veteran_player",
            "tournament_debut",
            "level_10_milestone",
            "weekly_warrior",
            "sharpshooter",
            "champion",
            "podium_finish",
            "tournament_dominator",
            "social_butterfly",
            "popular_player",
            "diverse_competitor",
            "community_pillar",
        ):
            ach = Achievement.query.filter_by(slug=slug).first()
            assert ach is not None
            assert ach.is_active is True, f"{slug} dovrebbe restare attivo"

    def test_service_excludes_unobtainable(self, db_session, isolated_players):
        """get_user_achievements non include i badge disattivati."""
        seed_achievements(db.session)
        player = isolated_players[0]

        achievements = AchievementService.get_user_achievements(player.id)
        returned_slugs = {a["achievement"].slug for a in achievements}

        assert returned_slugs.isdisjoint(UNOBTAINABLE_ACHIEVEMENT_SLUGS)
        # Sanity: un achievement ottenibile è presente
        assert "first_blood" in returned_slugs


class TestSeedMigrationConsistency:
    def test_seed_and_migration_net_state_match(self):
        """
        Lo stato netto delle migrazioni (DB esistenti) deve coincidere col set
        dei seed (nuovi DB): disattivati(20260605) − riattivati(20260606) == set
        dei seed. Così i due percorsi non divergono nel tempo.
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
        reactivated = set(
            _load(
                "20260606_reactivate_social_achievements.py"
            ).REACTIVATED_ACHIEVEMENT_SLUGS
        )

        assert reactivated <= disabled  # i riattivati erano stati disattivati
        assert (disabled - reactivated) == set(UNOBTAINABLE_ACHIEVEMENT_SLUGS)
