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
    safe_commit,
    init_db,
    reset_db,
)

# PHASE 1 COMPLETE: User domain imported from modular structure
from .user.models import User, TournamentDirector, DirectorRequest, VenueManagerRequest, VenueManagement

# PHASE 2 SPRINT 1 COMPLETE: All domains separated
from .campionato.models import Campionato
from .competition.models import Gara, Inscription
from .match.models import Match, Rack, MatchResult, TrioMatch
from .match.set_models import Set, SetRack
from .match.multi_discipline_service import MultiDisciplineService
from .classification.models import Classification, RoundClassification, PlayerEncounter

# PHASE 3: New domains for specification compliance
from .challenge.models import Challenge, ChallengeAttempt, ChallengeFavorite
from .challenge.gara_challenge_models import GaraChallenge, GaraChallengeAttempt, GaraChallengeClassification
from .challenge.services import ChallengeService
from .challenge.gara_challenge_service import GaraChallengeService
from .exam.models import Exam, ExamChallenge, ExamAttempt, ExamChallengeResult
from .individual_match.models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    PlayerAvailability,
    ProposalType,
    ProposalStatus,
    MatchStatus,
    InvitationStatus,
)
from .playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from .rating.models import (
    PlayerCategory,
    PlayerRating,
    HandicapRule,
    CategoryHandicapRule,
    RatingHandicapRule,
    CategoryLevel,
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
from .location.models import (
    BilliardHall,
    UserLocationAvailability,
    DayOfWeek,
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

# PHASE 3.2: Cross-domain orchestration
from .orchestration import DomainOrchestrator, OperationResult, OperationType

# Export all available models for backward compatibility
__all__ = [
    # Database and utilities
    "db",
    "get_or_create",
    "bulk_create",
    "safe_commit",
    "init_db",
    "reset_db",
    # User domain models (Phase 1)
    "User",
    "TournamentDirector",
    "DirectorRequest",
    "VenueManagerRequest",
    "VenueManagement",
    # Campionato domain models (Phase 2 Sprint 1)
    "Campionato",
    # Competition domain models (Phase 2 Sprint 1)
    "Gara",
    "Inscription",
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
    "ExamChallenge",
    "ExamAttempt",
    "ExamChallengeResult",
    # Individual Match domain models (Phase 3)
    "MatchProposal",
    "ProposalInvitation",
    "IndividualMatch",
    "IndividualRack",
    "PlayerAvailability",
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
    "PlayerCategory",
    "PlayerRating",
    "HandicapRule",
    "CategoryHandicapRule",
    "RatingHandicapRule",
    "CategoryLevel",
    "RatingSystem",
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
    "DayOfWeek",
    # Tiebreaker domain models (Phase 4)
    "Tiebreaker",
    "SpotShot",
    "RallyAttempt",
    "PlayoffMatch",
    "TiebreakerConfiguration",
    "TiebreakerType",
    "TiebreakerStatus",
    "SpotShotResult",
    # Cross-domain orchestration (Phase 3.2)
    "DomainOrchestrator",
    "OperationResult",
    "OperationType",
]

# Phase tracking
__version__ = "2.0.0-sprint1"
__phase__ = "Phase 2 Sprint 1: Domain Separation COMPLETE"
