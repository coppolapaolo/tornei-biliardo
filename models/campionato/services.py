# models/campionato/services.py
"""Re-export shim for backward compatibility (Round 4 P4).

Original 1025 LOC split into:
- tournament_service.py: TournamentService CRUD + lifecycle (~600 LOC)
- statistics_service.py: TournamentStatisticsService + compute_campionato_status (~290 LOC)
"""

from .tournament_service import TournamentService
from .statistics_service import TournamentStatisticsService, compute_campionato_status

__all__ = ["TournamentService", "TournamentStatisticsService", "compute_campionato_status"]
