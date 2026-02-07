"""
Module: models/individual_match/models.py
Purpose: Re-export shim for backward compatibility after P3a split.

Original models have been split into:
- proposal_models.py: MatchProposal, ProposalInvitation, enums
- match_models.py: IndividualMatch, IndividualSet, IndividualRack
- availability_models.py: PlayerAvailability (deprecated)
"""

# Proposal models
from .proposal_models import (
    ProposalType,
    ProposalStatus,
    InvitationStatus,
    MatchProposal,
    ProposalInvitation,
)

# Match models
from .match_models import (
    IndividualMatch,
    IndividualSetStatus,
    IndividualSet,
    IndividualRack,
)

# Availability models
from .availability_models import PlayerAvailability

# Re-export MatchStatus from shared enum for backward compat
from ..status_enum import MatchStatus

__all__ = [
    "ProposalType",
    "ProposalStatus",
    "InvitationStatus",
    "MatchProposal",
    "ProposalInvitation",
    "IndividualMatch",
    "IndividualSetStatus",
    "IndividualSet",
    "IndividualRack",
    "PlayerAvailability",
    "MatchStatus",
]
