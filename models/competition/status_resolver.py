# models/competition/status_resolver.py
"""
Resolves the real status of a Gara by examining match completion,
round progress, and inscription deadlines.

Extracted from Gara model to follow Single Responsibility Principle.
The Gara model delegates to this module via proxy methods for backward compatibility.
"""

from typing import Any

from models.base import utc_now
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus


class GaraStatusResolver:
    """Resolves derived status for a Gara based on match and round state."""

    @staticmethod
    def resolve(gara: Any) -> str:
        """Determine the real status of a gara, considering rounds and inscriptions.

        Args:
            gara: A Gara instance (or duck-typed object with status, matches, etc.)

        Returns:
            The resolved status string (may be a GaraStatus or ProvaDerivedStatus value).
        """
        status = getattr(gara, "status", None)

        if status == GaraStatus.PLAYING.value:
            return GaraStatusResolver._resolve_playing(gara)
        elif status == GaraStatus.INSCRIPTION.value:
            return GaraStatusResolver._resolve_inscription(gara)

        return status or ""

    @staticmethod
    def _resolve_playing(gara: Any) -> str:
        """Resolve status for a gara in PLAYING state."""
        matches_list = getattr(gara, "matches", []) or []
        if not matches_list:
            return GaraStatus.PLAYING.value

        finished_statuses = [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]

        # Check if ALL matches across ALL rounds are completed
        all_matches_completed = all(
            m.status in finished_statuses for m in matches_list
        )
        rounds_with_matches = set(
            m.round_number for m in matches_list if hasattr(m, "round_number")
        )
        rounds_count = getattr(gara, "rounds_count", 0) or 0
        all_rounds_have_matches = (
            len(rounds_with_matches) == rounds_count
            and max(rounds_with_matches) == rounds_count
        ) if rounds_with_matches else False

        if all_matches_completed and all_rounds_have_matches:
            return ProvaDerivedStatus.TOURNAMENT_COMPLETED.value

        # Fallback: check current round status
        current_round = getattr(gara, "current_round", 0) or 0
        current_round_matches = [
            m
            for m in matches_list
            if hasattr(m, "round_number") and m.round_number == current_round
        ]

        if current_round_matches:
            all_finished = all(
                m.status in finished_statuses for m in current_round_matches
            )
            if all_finished:
                if current_round < rounds_count:
                    return ProvaDerivedStatus.ROUND_COMPLETED.value
                else:
                    return ProvaDerivedStatus.TOURNAMENT_COMPLETED.value

        return GaraStatus.PLAYING.value

    @staticmethod
    def _resolve_inscription(gara: Any) -> str:
        """Resolve status for a gara in INSCRIPTION state."""
        inscription_end = getattr(gara, "inscription_end", None)
        if inscription_end and utc_now() > inscription_end:
            return ProvaDerivedStatus.INSCRIPTION_CLOSED.value
        return GaraStatus.INSCRIPTION.value


# Status badge configuration for UI presentation
STATUS_BADGE_MAP: dict[str, dict[str, str]] = {
    GaraStatus.SETUP.value: {"class": "bg-warning", "text": "Setup"},
    GaraStatus.INSCRIPTION.value: {"class": "bg-info", "text": "Iscrizioni Aperte"},
    ProvaDerivedStatus.INSCRIPTION_CLOSED.value: {
        "class": "bg-secondary",
        "text": "Iscrizioni Chiuse",
    },
    "ready_to_start": {"class": "bg-primary", "text": "Pronta per Iniziare"},
    GaraStatus.PLAYING.value: {"class": "bg-success", "text": "In Corso"},
    GaraStatus.AWAITING_SSR.value: {"class": "bg-warning", "text": "Spareggi"},
    GaraStatus.COMPLETED.value: {"class": "bg-dark", "text": "Completata"},
    ProvaDerivedStatus.ROUND_COMPLETED.value: {
        "class": "bg-info",
        "text": "Turno Completato",
    },
    ProvaDerivedStatus.TOURNAMENT_COMPLETED.value: {
        "class": "bg-dark",
        "text": "Gara Completata",
    },
}

_DEFAULT_BADGE: dict[str, str] = {"class": "bg-secondary", "text": "Sconosciuto"}


def get_status_badge(gara: Any) -> dict[str, str]:
    """Get badge display info for a gara's real status.

    Args:
        gara: A Gara instance (or duck-typed object).

    Returns:
        Dict with 'class' (CSS class) and 'text' (display label).
    """
    real_status = GaraStatusResolver.resolve(gara)
    return STATUS_BADGE_MAP.get(real_status, _DEFAULT_BADGE)
