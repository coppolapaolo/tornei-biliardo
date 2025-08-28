"""
Module: models/individual_match/__init__.py
Purpose: Individual Match domain initialization and exports
Requirements: SPECIFICHE.md - Individual match proposals system
"""

from .models import (
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
from .services import IndividualMatchService

__all__ = [
    # Models
    "MatchProposal",
    "ProposalInvitation",
    "IndividualMatch",
    "IndividualRack",
    "PlayerAvailability",
    # Enums
    "ProposalType",
    "ProposalStatus",
    "MatchStatus",
    "InvitationStatus",
    # Services
    "IndividualMatchService",
]
