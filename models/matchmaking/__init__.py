"""Tournament Matchmaking System

This module provides a comprehensive matchmaking system for American Pool tournaments,
implementing the Strategy Pattern to support multiple tournament formats while maintaining
consistent interfaces and behavior.

Core Components:
- MatchmakingService: Primary interface for tournament pairing generation
- EngineRegistry: Strategy management and discovery system
- PairingStrategy: Abstract base for all pairing algorithms
- Pairing: Value object representing match assignments with quality metrics

Available Strategies:
- Amalfi: Sophisticated adaptive algorithm with anti-rematch intelligence
- Round-Robin: Complete all-play-all format for league play
- Direct Elimination: Single knockout brackets for tournaments
- Double Knockout: Winners and losers brackets with elimination reprieve
- Random Anti-Rematch: Casual tournaments with variety enforcement

Key Features:
- Deterministic seeding support for testing and reproducibility
- Advanced bye handling (X-replacement with challenges and individual matches)
- Trio match support for odd player counts
- Comprehensive validation and error reporting
- Performance metrics and quality assessment
- Cross-domain integration (handicaps, challenges, notifications)

Business Context:
American Pool communities require flexible tournament organization supporting
various formats from casual meetups to competitive championships. This system
provides the infrastructure for fair, engaging tournaments while maintaining
the social aspects that make pool communities thrive.

Usage:
    from models.matchmaking import get_matchmaking_service

    service = get_matchmaking_service()
    pairings = service.run("amalfi", gara, round_number=1)

    # Or with deterministic seeding for testing
    pairings = service.run("amalfi", gara, round_number=1, seed=12345)

Architecture:
Built using Domain-Driven Design principles with clear separation of concerns,
strategy pattern implementation, and comprehensive error handling to ensure
reliable tournament operation under various conditions.
"""

# Export primary interfaces for clean API
from .service import MatchmakingService, matchmaking_service
from .bootstrap import get_matchmaking_service, get_registry
from .registry import EngineRegistry, PairingContext
from .strategies.base import Pairing, ValidationResult, PairingStrategy, BaseStrategy

__all__ = [
    "MatchmakingService",
    "matchmaking_service",
    "get_matchmaking_service",
    "get_registry",
    "EngineRegistry",
    "PairingContext",
    "Pairing",
    "ValidationResult",
    "PairingStrategy",
    "BaseStrategy",
]