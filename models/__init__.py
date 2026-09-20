"""
Models package initialization - Phase 2 Sprint 1 Complete

This module provides domain-driven model organization while maintaining
backward compatibility with existing code.

Phase Status:
- ✅ Base infrastructure complete
- ✅ User domain extracted and modularized
- ✅ Campionato domain extracted
- ✅ Competition domain extracted
- ✅ Match domain extracted
- ✅ Classification domain extracted
- ⚠️ Playoff still in legacy_models.py (future sprint)

Author: Refactoring Phase 2 - Sprint 1
Updated: 2025-08-06
"""

# Import database instance and utilities from base module
from .base import (
    db,
    get_or_create,
    bulk_create,
    init_db,
    reset_db,
)

# PHASE 1 COMPLETE: User domain imported from modular structure
from .user.models import (
    User,
    TournamentDirector,
    DirectorRequest,
    VenueManagerRequest,
    VenueManagement,
)
from .user.role_grant import RoleGrant, RoleRequest, RoleRequestRecipient
from .user.privacy_models import (
    UserPrivacySetting,
    HiddenMatch,
    HiddenInscription,
    HiddenCampionato,
)
from .user.privacy_service import PrivacyService

# PHASE 2 SPRINT 1 COMPLETE: All domains separated
from .campionato.models import Campionato
from .competition.models import Gara, Inscription
from .competition.round_configuration import RoundConfiguration
from .match.models import Match, Rack, MatchResult, TrioMatch
from .match.set_models import Set, SetRack
from .match.multi_discipline_service import MultiDisciplineService
from .classification.models import Classification, RoundClassification, PlayerEncounter

# PHASE 3: New domains for specification compliance
from .challenge.models import Challenge, ChallengeAttempt, ChallengeFavorite
from .competition.gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from .challenge.services import ChallengeService
from .competition.gara_challenge_service import GaraChallengeService
from .exam.models import (
    Exam,
    ExamExaminer,
    ExamChallenge,
    ExamAttempt,
    ExamChallengeResult,
)
from .exam.request_models import (
    ExamRequest,
    ExamRequestRecipient,
    ExamTimeProposal,
)
from .training_sheet.models import (
    TrainingSheet,
    TrainingSheetItem,
    TrainingSheetReader,
    TrainingSession,
    TrainingEntry,
)
from .istruttore.models import TrainingGroup, TrainingGroupMember
from .obiettivo.models import TrainingGoal
from .individual_match.models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    ProposalType,
    ProposalStatus,
    MatchStatus,
    InvitationStatus,
)
from .tpa.models import TpaReferto, TpaComando
from .playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from .rating.models import (
    PlayerRating,
    MatchRatingHistory,
    RatingSystem,
)
from .notification.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)
from .live_event import LiveEvent
from .location.models import (
    BilliardHall,
    UserLocationAvailability,
    DayOfWeek,
)
from .demand.models import DemandSignal, DemandSignalStatus
from .squadra.models import Squadra
from .categoria.models import Categoria
from .feedback.models import (
    FeedbackReport,
    FeedbackStatus,
    FeedbackSyncState,
    FeedbackType,
)
from .tiebreaker.models import (
    Tiebreaker,
    SpotShot,
    RallyAttempt,
    PlayoffMatch,
    TiebreakerConfiguration,
    TiebreakerType,
    TiebreakerStatus,
    SpotShotResult,
)

# PHASE 4: Gamification domain
from .gamification.models import (
    UserLevel,
    XPTransaction,
    Achievement,
    UserAchievement,
    StreakTracker,
    Quest,
    QuestParticipation,
    XPTransactionType,
    AchievementCategory,
    AchievementDifficulty,
    StreakType,
    QuestType,
    QuestStatus,
    LeaderboardType,
)
from .gamification.feature_models import (
    FeatureConfig,
    UserFeatureUsage,
)

# Shared operation result value objects (formerly under orchestration/)
from .shared.operation_result import OperationResult, OperationType

# Export all available models for backward compatibility
__all__ = [
    # Database and utilities
    "db",
    "get_or_create",
    "bulk_create",
    "init_db",
    "reset_db",
    # User domain models (Phase 1)
    "User",
    "TournamentDirector",
    "DirectorRequest",
    "VenueManagerRequest",
    "VenueManagement",
    # Ruoli concedibili e delega (ADR-041)
    "RoleGrant",
    "RoleRequest",
    "RoleRequestRecipient",
    # User privacy models
    "UserPrivacySetting",
    "HiddenMatch",
    "HiddenInscription",
    "HiddenCampionato",
    "PrivacyService",
    # Campionato domain models (Phase 2 Sprint 1)
    "Campionato",
    # Competition domain models (Phase 2 Sprint 1)
    "Gara",
    "Inscription",
    "RoundConfiguration",
    # Match domain models (Phase 2 Sprint 1)
    "Match",
    "Rack",
    "MatchResult",
    "TrioMatch",
    # Multi-set models (Phase 3)
    "Set",
    "SetRack",
    # Services
    "MultiDisciplineService",
    # Classification domain models (Phase 2 Sprint 1)
    "Classification",
    "RoundClassification",
    "PlayerEncounter",
    # Challenge domain models (Phase 3)
    "Challenge",
    "ChallengeAttempt",
    "ChallengeFavorite",
    # Gara Challenge integration models
    "GaraChallenge",
    "GaraChallengeAttempt",
    "GaraChallengeClassification",
    # Challenge services
    "ChallengeService",
    "GaraChallengeService",
    # Exam domain models (Phase 3)
    "Exam",
    "ExamExaminer",
    "ExamChallenge",
    "ExamAttempt",
    "ExamChallengeResult",
    "ExamRequest",
    "ExamRequestRecipient",
    "ExamTimeProposal",
    # Scheda di allenamento (ADR-067)
    "TrainingSheet",
    "TrainingSheetItem",
    "TrainingSheetReader",
    "TrainingSession",
    "TrainingEntry",
    # Obiettivi di allenamento (#316)
    "TrainingGoal",
    "TrainingGroup",
    "TrainingGroupMember",
    # Individual Match domain models (Phase 3)
    "MatchProposal",
    "ProposalInvitation",
    "IndividualMatch",
    "IndividualRack",
    # Referto TPA (ADR-044)
    "TpaReferto",
    "TpaComando",
    "ProposalType",
    "ProposalStatus",
    "MatchStatus",
    "InvitationStatus",
    # Playoff domain models (Phase 3)
    "PlayoffConfiguration",
    "PlayoffQualification",
    "PlayoffTournament",
    "PlayoffType",
    "QualificationStatus",
    # Rating domain models (Phase 3)
    "PlayerRating",
    "MatchRatingHistory",
    "RatingSystem",
    # Aggiornamenti live (ADR-057)
    "LiveEvent",
    # Notification domain models (Phase 3)
    "Notification",
    "NotificationPreference",
    "NotificationTemplate",
    "NotificationType",
    "NotificationPriority",
    "NotificationStatus",
    # Location domain models (Phase 3)
    "BilliardHall",
    "UserLocationAvailability",
    "DemandSignal",
    "DemandSignalStatus",
    "DayOfWeek",
    "Squadra",
    "Categoria",
    "FeedbackReport",
    "FeedbackStatus",
    "FeedbackSyncState",
    "FeedbackType",
    # Tiebreaker domain models (Phase 4)
    "Tiebreaker",
    "SpotShot",
    "RallyAttempt",
    "PlayoffMatch",
    "TiebreakerConfiguration",
    "TiebreakerType",
    "TiebreakerStatus",
    "SpotShotResult",
    # Gamification domain models (Phase 4)
    "UserLevel",
    "XPTransaction",
    "Achievement",
    "UserAchievement",
    "StreakTracker",
    "Quest",
    "QuestParticipation",
    "XPTransactionType",
    "AchievementCategory",
    "AchievementDifficulty",
    "StreakType",
    "QuestType",
    "QuestStatus",
    "LeaderboardType",
    # Gamification ABAC models (Phase 4.5)
    "FeatureConfig",
    "UserFeatureUsage",
    # Shared operation result value objects (formerly under orchestration/)
    "OperationResult",
    "OperationType",
]

# Phase tracking
__version__ = "2.0.0-sprint1"
__phase__ = "Phase 2 Sprint 1: Domain Separation COMPLETE"
