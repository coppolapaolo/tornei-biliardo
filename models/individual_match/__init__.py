"""
Module: models/individual_match/__init__.py
Purpose: Individual Match domain initialization and exports
Requirements: SPECIFICHE.md - Individual match proposals system
Sprint 13: Added specialized services exports
"""

from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    ProposalType,
    ProposalStatus,
    MatchStatus,
    InvitationStatus,
)

# Facade services (backward compatible)
from .services import IndividualMatchService, MatchProposalService

# Specialized services (Sprint 13)
from .proposal_service import ProposalService
from .match_lifecycle_service import MatchLifecycleService
from .individual_rack_service import IndividualRackService
from .statistics_service import IndividualMatchStatisticsService

__all__ = [
    # Models
    "MatchProposal",
    "ProposalInvitation",
    "IndividualMatch",
    "IndividualRack",
    # Enums
    "ProposalType",
    "ProposalStatus",
    "MatchStatus",
    "InvitationStatus",
    # Facade Services (backward compatible)
    "IndividualMatchService",
    "MatchProposalService",
    # Specialized Services (Sprint 13)
    "ProposalService",
    "MatchLifecycleService",
    "IndividualRackService",
    "IndividualMatchStatisticsService",
]
