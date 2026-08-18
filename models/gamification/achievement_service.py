"""
Achievement Service - Achievement Unlock and Progress Tracking

Service for checking achievement eligibility and awarding achievements.

Key Methods:
- check_and_award_achievement(): Check if user meets requirements and award if eligible
- get_user_achievements(): Get user's achievements with progress
- check_achievement_progress(): Update progress for progressive achievements
"""

from __future__ import annotations
from typing import Tuple, Optional, Dict, Any, List, Sequence
import json
import logging

from models.base import db, utc_now
from models.transaction.manager import transactional
from models.gamification.models import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementDifficulty,
)
from models.gamification.events import AchievementUnlockedEvent
from models.gamification.level_service import LevelService
from models.gamification.models import XPTransactionType
from models.gamification.achievement_metrics import AchievementMetrics
from models.exceptions import ValidationError
from models.events.base import EventBus

logger = logging.getLogger(__name__)


# Requisiti senza alcuna sorgente dati: resterebbero non ottenibili. Ora vuoto —
# tutti i tipi hanno un calcolo reale (metriche conteggiabili in
# AchievementMetrics o rami booleani in _check_requirements). Mantenuto come
# punto di estensione esplicito per eventuali requisiti futuri non ancora cablati.
_UNTRACKED_REQUIREMENT_TYPES: frozenset[str] = frozenset()

# Sentinella per distinguere "metric_value non fornito" da "None" (None è
# significativo: requisito non conteggiabile). Usata per riusare il valore già
# calcolato ed evitare di interrogare due volte AchievementMetrics per achievement.
_METRIC_UNSET = object()


# Requisiti con trigger dedicato o costosi da valutare: esclusi dalla
# riconciliazione di massa (`reconcile_achievements`) e gestiti dal loro handler
# specifico. `director_eligibility` itera i campionati (caro) → valutato solo a
# fine gara.
_RECONCILE_EXCLUDED_TYPES = frozenset(
    {
        "director_eligibility",
    }
)


class AchievementService:
    """
    Service for achievement unlock and progress tracking.

    Handles:
    - Checking if user meets achievement requirements
    - Updating progress for progressive achievements
    - Awarding achievements and XP bonuses
    - Emitting AchievementUnlockedEvent
    """

    @staticmethod
    @transactional(domain="gamification")
    def check_and_award_achievement(
        user_id: int, achievement_slug: str, force_check: bool = False
    ) -> Tuple[Optional[UserAchievement], bool]:
        """
        Re-evaluate a single achievement for a user and award it if now eligible.

        L'idoneità è sempre calcolata sulla **fonte di verità** (statistiche/
        ledger/conteggi reali via `_check_requirements`), non su un contatore
        incrementale: la chiamata è quindi idempotente e auto-correttiva. Per
        gli achievement "conta N", `current_progress` viene riallineato al
        valore reale della metrica solo a scopo di display.

        Per rivalutare in blocco gli achievement di un utente (uso tipico negli
        event handler) preferire `reconcile_achievements`.

        Args:
            user_id: User ID
            achievement_slug: Achievement slug (e.g., "first_blood")
            force_check: Re-check requirements anche se già sbloccato

        Returns:
            Tuple of (UserAchievement or None, was_newly_unlocked: bool)

        Emits:
            AchievementUnlockedEvent if newly unlocked
        """
        # Skip gamification for admin users
        from models.user.models import User

        user = db.session.get(User, user_id)
        if user and user.is_admin:
            logger.debug(f"Skipping achievement check for admin user {user_id}")
            return None, False

        achievement = Achievement.query.filter_by(slug=achievement_slug).first()
        if not achievement or not achievement.is_active:
            logger.warning(f"Achievement {achievement_slug} not found or inactive")
            return None, False

        return AchievementService._evaluate_and_award(
            user_id, achievement, force_check=force_check
        )

    @staticmethod
    @transactional(domain="gamification")
    def reconcile_achievements(user_id: int) -> List[str]:
        """Rivaluta in blocco gli achievement attivi 'a basso costo' dell'utente.

        Punto d'ingresso unico per gli event handler: invece di elencare slug a
        mano, si "riconcilia" lo stato dai dati reali (metric-driven). Sblocca
        quelli diventati idonei. Esclude i requisiti con trigger dedicato/costoso
        (`_RECONCILE_EXCLUDED_TYPES`, es. director_eligibility). Ogni achievement
        è isolato: un errore su uno non blocca gli altri.

        Returns:
            La lista degli slug appena sbloccati.
        """
        from models.user.models import User

        user = db.session.get(User, user_id)
        if user and user.is_admin:
            return []

        newly_unlocked: List[str] = []
        for achievement in Achievement.query.filter_by(is_active=True).all():
            try:
                requirement_type = json.loads(achievement.requirements).get("type")
            except (ValueError, TypeError):
                continue
            if requirement_type in _RECONCILE_EXCLUDED_TYPES:
                continue
            try:
                _, unlocked = AchievementService._evaluate_and_award(
                    user_id, achievement
                )
                if unlocked:
                    newly_unlocked.append(achievement.slug)
            except Exception as exc:  # isolamento per-achievement
                logger.warning(
                    f"reconcile: errore su '{achievement.slug}' "
                    f"per user {user_id}: {exc}"
                )
        return newly_unlocked

    @staticmethod
    @transactional(domain="gamification")
    def revoke_no_longer_earned(
        user_id: int, requirement_types: Sequence[str]
    ) -> List[str]:
        """Toglie i traguardi che i dati non giustificano piu'.

        **Perche' esiste.** Fino al 2026-08-18 la riconciliazione sapeva solo
        sbloccare: era la scelta giusta finche' i fatti non si potevano
        disfare. Da quando una prova si puo' cancellare — un tocco sbagliato
        durante l'allenamento — un traguardo poteva restare acceso su un conto
        che non esisteva piu'.

        **Non e' una revoca a colpo sicuro: e' un ricalcolo.** L'idoneita' si
        rivaluta sulla fonte di verita' (``AchievementMetrics``), quindi se
        altri esercizi reggono comunque il requisito il traguardo **resta**.
        Chi ha fatto cento prove e ne cancella una non perde niente.

        **Solo i tipi indicati.** Il chiamante dichiara quali metriche ha
        toccato: rivalutare tutto vorrebbe dire togliere anche traguardi il cui
        requisito e' booleano o legato a un evento irripetibile, dove
        «non idoneo adesso» non significa «non e' mai successo».

        L'XP del traguardo torna indietro con un movimento compensativo, come
        per la prova: il registro racconta cos'e' successo, non fa finta di
        niente.

        Returns:
            Gli slug dei traguardi tolti.
        """
        from models.user.models import User

        user = db.session.get(User, user_id)
        if user and user.is_admin:
            return []

        tolti: List[str] = []
        tipi = set(requirement_types)

        for achievement in Achievement.query.filter_by(is_active=True).all():
            try:
                requirements = json.loads(achievement.requirements)
            except (ValueError, TypeError):
                continue
            requirement_type = requirements.get("type")
            if requirement_type not in tipi:
                continue

            user_achievement = UserAchievement.query.filter_by(
                user_id=user_id, achievement_id=achievement.id
            ).first()
            if user_achievement is None or not user_achievement.is_unlocked:
                continue

            try:
                metric_value = AchievementMetrics.current_value(
                    user_id, requirement_type, requirements
                )
                if metric_value is not None:
                    target = requirements.get("count", 1)
                    user_achievement.current_progress = min(metric_value, target)

                ancora_idoneo = AchievementService._check_requirements(
                    user_id=user_id,
                    requirement_type=requirement_type,
                    requirements=requirements,
                    metric_value=metric_value,
                )
            except Exception as exc:
                # Un errore di valutazione non deve **togliere** niente: nel
                # dubbio il traguardo resta. Sbagliare per eccesso qui vuol
                # dire lasciare un badge di troppo; sbagliare per difetto vuol
                # dire toglierne uno guadagnato.
                logger.warning(
                    f"revoca: errore su '{achievement.slug}' per user {user_id}: {exc}"
                )
                continue

            if ancora_idoneo:
                continue

            user_achievement.is_unlocked = False
            user_achievement.unlocked_at = None
            tolti.append(achievement.slug)

            if achievement.xp_reward > 0:
                try:
                    LevelService.award_xp(
                        user_id=user_id,
                        xp_amount=-achievement.xp_reward,
                        transaction_type=XPTransactionType.ACHIEVEMENT_UNLOCK,
                        reason=f"Achievement revoked: {achievement.name}",
                        related_entities={
                            "achievement_id": achievement.id,
                            "achievement_slug": achievement.slug,
                            "revoked": True,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        f"revoca: XP non restituito per '{achievement.slug}' "
                        f"(user {user_id}): {exc}"
                    )

            logger.info(f"User {user_id} lost achievement '{achievement.slug}'")

        return tolti

    @staticmethod
    def _evaluate_and_award(
        user_id: int, achievement: Achievement, force_check: bool = False
    ) -> Tuple[Optional[UserAchievement], bool]:
        """Core (non transazionale) di valutazione+assegnazione di un achievement.

        Assume utente non-admin e achievement attivo (verificati dai chiamanti).
        Opera sulla sessione corrente: il commit è del decoratore @transactional
        del chiamante (`check_and_award_achievement` / `reconcile_achievements`).
        """
        user_achievement = UserAchievement.query.filter_by(
            user_id=user_id, achievement_id=achievement.id
        ).first()

        if user_achievement is None:
            user_achievement = UserAchievement(
                user_id=user_id,
                achievement_id=achievement.id,
                current_progress=0,  # Explicit init before flush
            )
            db.session.add(user_achievement)

        # Skip if already unlocked (unless force_check)
        if user_achievement.is_unlocked and not force_check:
            return user_achievement, False

        requirements = json.loads(achievement.requirements)
        requirement_type = requirements.get("type")

        # Allinea current_progress al valore reale della metrica (display only:
        # l'idoneità è valutata sulla fonte di verità, non sul contatore). Per i
        # tipi non conteggiabili (booleani/stub) current_progress resta com'è.
        metric_value = AchievementMetrics.current_value(
            user_id, requirement_type, requirements
        )
        if metric_value is not None:
            target = requirements.get("count", 1)
            user_achievement.current_progress = min(metric_value, target)

        # Check if requirements met (single source of truth). Riusa il
        # metric_value già calcolato sopra per non interrogare due volte
        # AchievementMetrics per lo stesso achievement (perf reconcile, ADR-037).
        is_eligible = AchievementService._check_requirements(
            user_id=user_id,
            requirement_type=requirement_type,
            requirements=requirements,
            metric_value=metric_value,
        )

        if not is_eligible or user_achievement.is_unlocked:
            return user_achievement, False

        # Award achievement!
        user_achievement.is_unlocked = True
        user_achievement.unlocked_at = utc_now()

        if achievement.xp_reward > 0:
            LevelService.award_xp(
                user_id=user_id,
                xp_amount=achievement.xp_reward,
                transaction_type=XPTransactionType.ACHIEVEMENT_UNLOCK,
                reason=f"Unlocked achievement: {achievement.name}",
                related_entities={
                    "achievement_id": achievement.id,
                    "achievement_slug": achievement.slug,
                },
            )

        EventBus.publish(
            AchievementUnlockedEvent(
                user_id=user_id,
                achievement_id=achievement.id,
                achievement_slug=achievement.slug,
                achievement_name=achievement.name,
                achievement_category=achievement.category.value,
                achievement_difficulty=achievement.difficulty.value,
                xp_awarded=achievement.xp_reward,
            )
        )

        logger.info(
            f"User {user_id} unlocked achievement '{achievement.slug}' "
            f"(+{achievement.xp_reward} XP)"
        )

        return user_achievement, True

    @staticmethod
    def _check_requirements(
        user_id: int,
        requirement_type: str,
        requirements: Dict[str, Any],
        metric_value: Any = _METRIC_UNSET,
    ) -> bool:
        """
        Check if a user currently meets an achievement's requirements.

        Modello unico: gli achievement "conta N" derivano il valore corrente
        dalla fonte di verità (`AchievementMetrics`) e lo confrontano col
        target — niente contatori incrementali. I requisiti booleani/a soglia
        (win_rate, level_reached, weekly_streak, gaming_data_shared,
        director_eligibility) hanno logica dedicata. I tipi senza sorgente dati
        (`_UNTRACKED_REQUIREMENT_TYPES`) restano non ottenibili.

        Args:
            user_id: User ID
            requirement_type: Type of requirement
            requirements: Full requirements dict

        Returns:
            True if requirements are met
        """
        # 1) Metriche conteggiabili: idoneità = valore reale >= target.
        # Riusa il valore se già calcolato dal chiamante (evita doppia query).
        if metric_value is _METRIC_UNSET:
            metric_value = AchievementMetrics.current_value(
                user_id, requirement_type, requirements
            )
        if metric_value is not None:
            return metric_value >= requirements.get("count", 1)

        # 2) Requisiti booleani / a soglia con logica dedicata.
        if requirement_type == "win_rate":
            from models.user.services import UserStatsService

            stats = UserStatsService.get_user_stats(user_id)
            total_matches = stats.get("total_matches", 0)
            win_percentage = stats.get("win_percentage", 0)
            return (
                total_matches >= requirements["min_matches"]
                and win_percentage >= requirements["percentage"]
            )

        if requirement_type == "level_reached":
            from models.gamification.models import UserLevel

            user_level = db.session.get(UserLevel, user_id)
            current_level = user_level.current_level if user_level else 1
            return current_level >= requirements["level"]

        if requirement_type == "weekly_streak":
            from models.gamification.models import StreakTracker, StreakType

            streak = StreakTracker.query.filter_by(
                user_id=user_id, streak_type=StreakType.WEEKLY_ACTIVITY
            ).first()
            current_streak = streak.current_streak if streak else 0
            return current_streak >= requirements["weeks"]

        if requirement_type == "gaming_data_shared":
            from models.user.privacy_models import UserPrivacySetting

            settings = UserPrivacySetting.query.filter_by(user_id=user_id).first()
            if not settings:
                return False
            # Gaming data fields (excluding personal contact info)
            return any(
                [
                    settings.show_statistics,
                    settings.show_recent_matches,
                    settings.show_classifications,
                    settings.show_challenge_stats,
                ]
            )

        if requirement_type == "director_eligibility":
            return AchievementService._check_director_eligibility(
                user_id=user_id,
                min_gare=requirements.get("min_gare", 10),
                min_campionati=requirements.get("min_campionati_completi", 1),
            )

        if requirement_type == "category_reached":
            # "Raggiungi la categoria X" = categoria attuale pari o superiore
            # (A migliore di B di C di D). Ordine: A=1 … D=4.
            from models.rating.models import PlayerCategory

            order = {"A": 1, "B": 2, "C": 3, "D": 4}
            target = order.get(str(requirements.get("category", "B")).upper())
            if target is None:
                return False
            current = PlayerCategory.get_user_current_category(user_id)
            if current is None:
                return False
            current_rank = order.get(current.category.value.upper())
            return current_rank is not None and current_rank <= target

        # 3) Tipi privi di tracking → non ottenibili (achievement disattivati).
        if requirement_type in _UNTRACKED_REQUIREMENT_TYPES:
            return False

        logger.warning(f"Unknown requirement type: {requirement_type}")
        return False

    @staticmethod
    def _check_director_eligibility(
        user_id: int, min_gare: int = 10, min_campionati: int = 1
    ) -> bool:
        """
        Check if user has enough experience for director eligibility achievement.

        Requirements (OR logic):
        - Participated in min_gare completed gare
        - Participated in ALL gare of at least min_campionati campionati

        Args:
            user_id: User ID to check
            min_gare: Minimum completed gare participations
            min_campionati: Minimum complete campionati

        Returns:
            True if either condition is met
        """
        from models.competition.models import Inscription, Gara
        from models.campionato.models import Campionato
        from models.status_enum import GaraStatus
        from sqlalchemy import func

        # Count gare where user participated (inscription not withdrawn)
        # in gare that are completed
        gare_count = (
            db.session.query(Inscription)
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
                Gara.status == GaraStatus.COMPLETED.value,
            )
            .count()
        )

        if gare_count >= min_gare:
            logger.debug(
                f"User {user_id} eligible for director: {gare_count} gare >= {min_gare}"
            )
            return True

        # Check complete campionati (user participated in ALL gare of a campionato)
        # Get campionati where user has at least one inscription
        user_campionati = (
            db.session.query(Campionato.id)
            .join(Gara, Gara.campionato_id == Campionato.id)
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
                Campionato.is_deleted == False,  # noqa: E712
            )
            .distinct()
            .all()
        )

        complete_campionati_count = 0

        for (campionato_id,) in user_campionati:
            # Count total completed gare in this campionato
            total_gare = (
                db.session.query(func.count(Gara.id))
                .filter(
                    Gara.campionato_id == campionato_id,
                    Gara.status == GaraStatus.COMPLETED.value,
                )
                .scalar()
            ) or 0

            if total_gare == 0:
                continue  # Campionato has no completed gare yet

            # Count gare where user participated in this campionato
            user_gare = (
                db.session.query(func.count(Inscription.id))
                .join(Gara, Inscription.gara_id == Gara.id)
                .filter(
                    Gara.campionato_id == campionato_id,
                    Gara.status == GaraStatus.COMPLETED.value,
                    Inscription.user_id == user_id,
                    Inscription.is_withdrawn == False,  # noqa: E712
                )
                .scalar()
            ) or 0

            if user_gare >= total_gare:
                complete_campionati_count += 1
                if complete_campionati_count >= min_campionati:
                    logger.debug(
                        f"User {user_id} eligible for director: "
                        f"{complete_campionati_count} complete campionati "
                        f">= {min_campionati}"
                    )
                    return True

        logger.debug(
            f"User {user_id} not eligible for director: "
            f"{gare_count} gare (need {min_gare}), "
            f"{complete_campionati_count} campionati (need {min_campionati})"
        )
        return False

    @staticmethod
    def has_achievement(user_id: int, achievement_slug: str) -> bool:
        """
        Check if user has unlocked a specific achievement.

        Args:
            user_id: User ID
            achievement_slug: Achievement slug to check

        Returns:
            True if achievement is unlocked
        """
        achievement = Achievement.query.filter_by(slug=achievement_slug).first()
        if not achievement:
            return False

        user_achievement = UserAchievement.query.filter_by(
            user_id=user_id, achievement_id=achievement.id, is_unlocked=True
        ).first()

        return user_achievement is not None

    @staticmethod
    def get_user_achievements(
        user_id: int, unlocked_only: bool = False, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get user's achievements with progress.

        Args:
            user_id: User ID
            unlocked_only: If True, only return unlocked achievements
            category: Filter by category (e.g., "MATCH")

        Returns:
            List of dicts with achievement and progress info:
            [
                {
                    "achievement": Achievement,
                    "is_unlocked": bool,
                    "current_progress": int,
                    "progress_percentage": float,
                    "unlocked_at": datetime or None
                },
                ...
            ]
        """
        # Build query
        query = Achievement.query.filter_by(is_active=True)

        if category:
            from models.gamification.models import AchievementCategory

            try:
                category_enum = AchievementCategory[category.upper()]
                query = query.filter_by(category=category_enum)
            except KeyError:
                logger.warning(f"Invalid category: {category}")

        achievements = query.all()

        # Prefetch di tutte le UserAchievement dell'utente in un dict per evitare
        # un N+1 (una query per achievement nel loop sottostante).
        user_achievements = {
            ua.achievement_id: ua
            for ua in UserAchievement.query.filter_by(user_id=user_id).all()
        }

        result = []
        for achievement in achievements:
            # Get user progress (dal prefetch, niente query nel loop)
            user_achievement = user_achievements.get(achievement.id)

            is_unlocked = user_achievement.is_unlocked if user_achievement else False
            current_progress = (
                user_achievement.current_progress if user_achievement else 0
            )
            unlocked_at = user_achievement.unlocked_at if user_achievement else None

            # Skip locked achievements if unlocked_only
            if unlocked_only and not is_unlocked:
                continue

            # Progress: per le metriche conteggiabili usa il valore reale
            # (display auto-correttivo, indipendente dal contatore salvato).
            requirements = json.loads(achievement.requirements)
            requirement_type = requirements.get("type")
            metric_value = AchievementMetrics.current_value(
                user_id, requirement_type, requirements
            )
            if metric_value is not None:
                target = requirements.get("count", 1)
                current_progress = min(metric_value, target)
                progress_percentage = (
                    min(100.0, metric_value / target * 100) if target else 0.0
                )
            elif achievement.is_progressive:
                target = requirements.get("count", 100)
                progress_percentage = min(100.0, (current_progress / target * 100))
            else:
                progress_percentage = 100.0 if is_unlocked else 0.0

            result.append(
                {
                    "achievement": achievement,
                    "is_unlocked": is_unlocked,
                    "current_progress": current_progress,
                    "progress_percentage": round(progress_percentage, 1),
                    "unlocked_at": unlocked_at,
                }
            )

        return result

    @staticmethod
    def get_achievement_stats(user_id: int) -> Dict[str, Any]:
        """
        Get achievement statistics for user profile.

        Returns:
            {
                "total_unlocked": int,
                "total_achievements": int,
                "completion_percentage": float,
                "by_category": {
                    "MATCH": {"unlocked": int, "total": int},
                    ...
                },
                "by_difficulty": {
                    "COMMON": {"unlocked": int, "total": int},
                    ...
                },
                "recent_unlocks": [Achievement, ...]
            }
        """
        from models.gamification.models import (
            AchievementCategory,
            AchievementDifficulty,
        )

        all_achievements = Achievement.query.filter_by(is_active=True).all()
        unlocked = UserAchievement.query.filter_by(
            user_id=user_id, is_unlocked=True
        ).all()

        # By category
        by_category = {}
        for category in AchievementCategory:
            cat_total = len([a for a in all_achievements if a.category == category])
            cat_unlocked = len(
                [ua for ua in unlocked if ua.achievement.category == category]
            )
            by_category[category.value] = {"unlocked": cat_unlocked, "total": cat_total}

        # By difficulty
        by_difficulty = {}
        for difficulty in AchievementDifficulty:
            diff_total = len(
                [a for a in all_achievements if a.difficulty == difficulty]
            )
            diff_unlocked = len(
                [ua for ua in unlocked if ua.achievement.difficulty == difficulty]
            )
            by_difficulty[difficulty.value] = {
                "unlocked": diff_unlocked,
                "total": diff_total,
            }

        # Recent unlocks (last 5)
        recent_unlocks = (
            UserAchievement.query.filter_by(user_id=user_id, is_unlocked=True)
            .order_by(UserAchievement.unlocked_at.desc())
            .limit(5)
            .all()
        )

        return {
            "total_unlocked": len(unlocked),
            "total_achievements": len(all_achievements),
            "completion_percentage": (
                round((len(unlocked) / len(all_achievements) * 100), 1)
                if all_achievements
                else 0.0
            ),
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "recent_unlocks": [ua.achievement for ua in recent_unlocks],
        }

    # ========================================
    # Admin Operations
    # ========================================

    @staticmethod
    @transactional(domain="gamification")
    def create_achievement(
        slug: str,
        name: str,
        description: str,
        category: str,
        difficulty: str,
        icon_path: Optional[str],
        xp_reward: int,
        is_hidden: bool,
        is_progressive: bool,
        requirement_type: str,
        requirement_value: int,
    ) -> Achievement:
        """Create a new achievement definition.

        Only *countable* requirement types are accepted
        (`AchievementMetrics.COUNTABLE_TYPES`), because the shape stored here is
        always `{"type": ..., "count": N}`. A type with bespoke logic
        (win_rate, level_reached, weekly_streak, category_reached) reads keys
        this shape does not carry, and a type with no resolver cannot be
        computed at all: either way the achievement would be born dead — never
        unlockable, with no error raised anywhere. Those belong in the seeds,
        where the requirement shape is written out in full.

        Raises:
            ValidationError: if slug/name are missing, the slug already exists,
                or the requirement type is not countable.
        """
        if not slug or not name:
            raise ValidationError("Slug e nome sono obbligatori")
        if Achievement.query.filter_by(slug=slug).first():
            raise ValidationError("Un achievement con questo slug esiste già")
        if requirement_type not in AchievementMetrics.COUNTABLE_TYPES:
            ammessi = ", ".join(sorted(AchievementMetrics.COUNTABLE_TYPES))
            raise ValidationError(
                f"Requisito «{requirement_type}» non conteggiabile: un "
                f"achievement creato cosi' non si sbloccherebbe mai. "
                f"Tipi ammessi: {ammessi}. I requisiti a logica propria "
                f"(win_rate, level_reached, weekly_streak, category_reached) "
                f"vanno dichiarati nei seed."
            )

        requirements = json.dumps(
            {"type": requirement_type, "count": requirement_value}
        )
        achievement = Achievement(
            slug=slug,
            name=name,
            description=description,
            category=AchievementCategory[category.upper()],
            difficulty=AchievementDifficulty[difficulty.upper()],
            icon_path=icon_path,
            xp_reward=xp_reward,
            is_hidden=is_hidden,
            is_progressive=is_progressive,
            requirements=requirements,
        )
        db.session.add(achievement)
        logger.info(f"Created achievement '{slug}'")
        return achievement

    @staticmethod
    @transactional(domain="gamification")
    def toggle_hidden(achievement_id: int) -> Achievement:
        """Toggle achievement hidden status.

        Raises:
            ValueError: If achievement not found.
        """
        achievement = db.session.get(Achievement, achievement_id)
        if not achievement:
            raise ValueError("Achievement non trovato")
        achievement.is_hidden = not achievement.is_hidden
        logger.info(f"Achievement '{achievement.slug}' hidden={achievement.is_hidden}")
        return achievement
