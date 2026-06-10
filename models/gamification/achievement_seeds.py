"""
Achievement Seeds - Predefined Achievements

Defines 20+ achievements across categories:
- Match: Win-based and streak achievements
- Tournament: Participation and placement achievements
- Social: Community engagement achievements
- Skill: Performance-based achievements
- Consistency: Streak and habit achievements
- Exploration: Feature discovery achievements
- Milestone: Major accomplishments

Each achievement has:
- slug: Unique identifier
- name: Display name (i18n compatible)
- description: What the achievement rewards
- category: AchievementCategory enum
- difficulty: AchievementDifficulty (common to legendary)
- requirements: JSON criteria for unlocking
- is_progressive: Whether to track partial progress
- xp_reward: Bonus XP awarded on unlock
"""

from models.gamification.models import AchievementCategory, AchievementDifficulty

PREDEFINED_ACHIEVEMENTS = [
    # ========================================
    # Match Achievements
    # ========================================
    {
        "slug": "first_blood",
        "name": "First Blood",
        "description": "Vinci la tua prima partita",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.COMMON,
        "requirements": '{"type": "match_wins", "count": 1}',
        "is_progressive": False,
        "xp_reward": 50,
    },
    {
        "slug": "veteran_player",
        "name": "Giocatore Veterano",
        "description": "Vinci 50 partite",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "match_wins", "count": 50}',
        "is_progressive": True,
        "xp_reward": 250,
    },
    {
        "slug": "century_club",
        "name": "Club del Secolo",
        "description": "Vinci 100 partite",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "match_wins", "count": 100}',
        "is_progressive": True,
        "xp_reward": 500,
    },
    {
        "slug": "match_marathon",
        "name": "Maratoneta delle Partite",
        "description": "Vinci 250 partite",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "match_wins", "count": 250}',
        "is_progressive": True,
        "xp_reward": 1000,
    },
    {
        "slug": "hot_streak",
        "name": "Serie Vincente",
        "description": "Vinci 5 partite consecutive",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "win_streak", "count": 5}',
        "is_progressive": False,
        "xp_reward": 150,
    },
    {
        "slug": "unstoppable",
        "name": "Inarrestabile",
        "description": "Vinci 10 partite consecutive",
        "category": AchievementCategory.MATCH,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "win_streak", "count": 10}',
        "is_progressive": False,
        "xp_reward": 300,
    },
    # ========================================
    # Tournament Achievements
    # ========================================
    {
        "slug": "tournament_debut",
        "name": "Debutto Torneo",
        "description": "Partecipa al tuo primo torneo",
        "category": AchievementCategory.TOURNAMENT,
        "difficulty": AchievementDifficulty.COMMON,
        "requirements": '{"type": "tournament_participation", "count": 1}',
        "is_progressive": False,
        "xp_reward": 100,
    },
    {
        "slug": "tournament_regular",
        "name": "Habitué dei Tornei",
        "description": "Partecipa a 10 tornei",
        "category": AchievementCategory.TOURNAMENT,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "tournament_participation", "count": 10}',
        "is_progressive": True,
        "xp_reward": 200,
    },
    {
        "slug": "podium_finish",
        "name": "Sul Podio",
        "description": "Finisci nei primi 3 in un torneo",
        "category": AchievementCategory.TOURNAMENT,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "tournament_podium", "count": 1}',
        "is_progressive": False,
        "xp_reward": 300,
    },
    {
        "slug": "champion",
        "name": "Campione",
        "description": "Vinci un torneo",
        "category": AchievementCategory.TOURNAMENT,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "tournament_wins", "count": 1}',
        "is_progressive": False,
        "xp_reward": 500,
    },
    {
        "slug": "tournament_dominator",
        "name": "Dominatore di Tornei",
        "description": "Vinci 5 tornei",
        "category": AchievementCategory.TOURNAMENT,
        "difficulty": AchievementDifficulty.LEGENDARY,
        "requirements": '{"type": "tournament_wins", "count": 5}',
        "is_progressive": True,
        "xp_reward": 1500,
    },
    # ========================================
    # Social Achievements
    # ========================================
    {
        "slug": "open_player",
        "name": "Giocatore Aperto",
        "description": "Condividi almeno un dato di gioco pubblicamente (statistiche, partite, classifiche o challenge)",
        "category": AchievementCategory.SOCIAL,
        "difficulty": AchievementDifficulty.COMMON,
        "requirements": '{"type": "gaming_data_shared"}',
        "is_progressive": False,
        "xp_reward": 25,
    },
    {
        "slug": "social_butterfly",
        "name": "Farfalla Sociale",
        "description": "Crea 5 proposte di partita",
        "category": AchievementCategory.SOCIAL,
        "difficulty": AchievementDifficulty.COMMON,
        "requirements": '{"type": "match_proposals_created", "count": 5}',
        "is_progressive": True,
        "xp_reward": 75,
    },
    {
        "slug": "popular_player",
        "name": "Giocatore Popolare",
        "description": "Accetta 10 inviti a partite",
        "category": AchievementCategory.SOCIAL,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "match_proposals_accepted", "count": 10}',
        "is_progressive": True,
        "xp_reward": 100,
    },
    {
        "slug": "diverse_competitor",
        "name": "Competitore Versatile",
        "description": "Gioca contro 10 avversari diversi",
        "category": AchievementCategory.SOCIAL,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "unique_opponents", "count": 10}',
        "is_progressive": True,
        "xp_reward": 150,
    },
    {
        "slug": "community_pillar",
        "name": "Pilastro della Community",
        "description": "Gioca contro 50 avversari diversi",
        "category": AchievementCategory.SOCIAL,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "unique_opponents", "count": 50}',
        "is_progressive": True,
        "xp_reward": 500,
    },
    # ========================================
    # Skill Achievements
    # ========================================
    {
        "slug": "sharpshooter",
        "name": "Tiratore Scelto",
        "description": "70% di vittorie su 20+ partite",
        "category": AchievementCategory.SKILL,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "win_rate", "percentage": 70, "min_matches": 20}',
        "is_progressive": False,
        "xp_reward": 400,
    },
    {
        "slug": "elite_performer",
        "name": "Performer Élite",
        "description": "80% di vittorie su 50+ partite",
        "category": AchievementCategory.SKILL,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "win_rate", "percentage": 80, "min_matches": 50}',
        "is_progressive": False,
        "xp_reward": 800,
    },
    {
        "slug": "category_climber",
        "name": "Scalatore di Categoria",
        "description": "Raggiungi Categoria B",
        "category": AchievementCategory.SKILL,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "category_reached", "category": "B"}',
        "is_progressive": False,
        "xp_reward": 200,
    },
    {
        "slug": "elite_player",
        "name": "Giocatore Élite",
        "description": "Raggiungi Categoria A",
        "category": AchievementCategory.SKILL,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "category_reached", "category": "A"}',
        "is_progressive": False,
        "xp_reward": 600,
    },
    # ========================================
    # Consistency Achievements (Weekly Streaks)
    # ========================================
    {
        "slug": "weekly_warrior",
        "name": "Guerriero Settimanale",
        "description": "4 settimane di streak consecutivi",
        "category": AchievementCategory.CONSISTENCY,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "weekly_streak", "weeks": 4}',
        "is_progressive": False,
        "xp_reward": 150,
    },
    {
        "slug": "monthly_master",
        "name": "Maestro Mensile",
        "description": "12 settimane di streak consecutivi",
        "category": AchievementCategory.CONSISTENCY,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "weekly_streak", "weeks": 12}',
        "is_progressive": False,
        "xp_reward": 400,
    },
    {
        "slug": "year_long_dedication",
        "name": "Dedizione Annuale",
        "description": "52 settimane di streak consecutivi",
        "category": AchievementCategory.CONSISTENCY,
        "difficulty": AchievementDifficulty.LEGENDARY,
        "requirements": '{"type": "weekly_streak", "weeks": 52}',
        "is_progressive": False,
        "xp_reward": 2000,
    },
    # ========================================
    # Exploration Achievements
    # ========================================
    {
        "slug": "strategy_explorer",
        "name": "Esploratore di Strategie",
        "description": "Prova tutte le 5 strategie di matchmaking",
        "category": AchievementCategory.EXPLORATION,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "strategies_tried", "count": 5}',
        "is_progressive": True,
        "xp_reward": 200,
    },
    {
        "slug": "challenge_master",
        "name": "Maestro dei Drill",
        "description": "Completa 10 drill di allenamento",
        "category": AchievementCategory.EXPLORATION,
        "difficulty": AchievementDifficulty.COMMON,
        "requirements": '{"type": "challenges_completed", "count": 10}',
        "is_progressive": True,
        "xp_reward": 150,
    },
    {
        "slug": "perfectionist",
        "name": "Perfezionista",
        "description": "Ottieni perfect score su 5 drill diversi",
        "category": AchievementCategory.SKILL,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "perfect_challenges", "count": 5}',
        "is_progressive": True,
        "xp_reward": 250,
    },
    {
        "slug": "drill_addict",
        "name": "Dipendente dal Drill",
        "description": "Completa 100 drill di allenamento",
        "category": AchievementCategory.EXPLORATION,
        "difficulty": AchievementDifficulty.EPIC,
        "requirements": '{"type": "challenges_completed", "count": 100}',
        "is_progressive": True,
        "xp_reward": 500,
    },
    # ========================================
    # Director Eligibility Achievement
    # ========================================
    {
        "slug": "aspiring_director",
        "name": "Aspirante Direttore",
        "description": "Hai dimostrato esperienza sufficiente per dirigere gare (10 gare o 1 campionato completo)",
        "category": AchievementCategory.MILESTONE,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "director_eligibility", "min_gare": 10, "min_campionati_completi": 1}',
        "is_progressive": False,
        "xp_reward": 200,
        "is_hidden": False,
    },
    # ========================================
    # Milestone Achievements
    # ========================================
    {
        "slug": "level_10_milestone",
        "name": "Livello 10 Raggiunto",
        "description": "Raggiungi il livello 10",
        "category": AchievementCategory.MILESTONE,
        "difficulty": AchievementDifficulty.UNCOMMON,
        "requirements": '{"type": "level_reached", "level": 10}',
        "is_progressive": False,
        "xp_reward": 300,
    },
    {
        "slug": "level_25_milestone",
        "name": "Livello 25 Raggiunto",
        "description": "Raggiungi il livello 25",
        "category": AchievementCategory.MILESTONE,
        "difficulty": AchievementDifficulty.RARE,
        "requirements": '{"type": "level_reached", "level": 25}',
        "is_progressive": False,
        "xp_reward": 750,
    },
    {
        "slug": "level_50_milestone",
        "name": "Leggenda Vivente",
        "description": "Raggiungi il livello 50",
        "category": AchievementCategory.MILESTONE,
        "difficulty": AchievementDifficulty.LEGENDARY,
        "requirements": '{"type": "level_reached", "level": 50}',
        "is_progressive": False,
        "xp_reward": 2500,
    },
]


def seed_achievements(db_session):
    """
    Seed predefined achievements into database.

    Creates Achievement records for all predefined achievements.
    Skips achievements that already exist (idempotent).

    Args:
        db_session: SQLAlchemy session

    Returns:
        Tuple of (created_count, skipped_count)
    """
    from models.gamification.models import Achievement

    created_count = 0
    skipped_count = 0

    for achievement_data in PREDEFINED_ACHIEVEMENTS:
        # Check if achievement already exists
        existing = Achievement.query.filter_by(slug=achievement_data["slug"]).first()

        if existing:
            skipped_count += 1
            continue

        # Create new achievement
        achievement = Achievement(**achievement_data)
        db_session.add(achievement)
        created_count += 1

    db_session.commit()

    return created_count, skipped_count
