# models/campionato/homepage_service.py
"""Service for aggregating homepage data.

Extracts business logic previously inline in routes/main.py:index().
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, Optional

from models.campionato.models import Campionato
from models.competition.models import Gara
from models.status_enum import GaraStatus, TournamentStatus
from models.campionato.services import TournamentService

# How many completed campionati to surface alongside active ones on the homepage.
# Older ones live behind the "Vedi tutti" link to /campionatos.
HOMEPAGE_COMPLETED_LIMIT = 2


class HomepageService:
    """Aggregates data for the public homepage."""

    @staticmethod
    def get_homepage_data() -> Optional[Dict[str, Any]]:
        """Return all data needed to render the homepage.

        The homepage shows a single "Campionati" section: all in-progress
        campionati first (status != COMPLETED/TERMINATED), then the most
        recent few completed ones as a tail.

        Returns:
            Dict with keys:
              - tournaments_data: list of dicts (active + tail of completed)
              - active_campionatos: backwards-compat list (same campionati)
              - active_count, completed_total, completed_shown: counters
                used by the template ("Vedi tutti" appears when there are
                more completed than shown).
              - standalone_garas: list of standalone Gara.
            None if there is nothing public to show.
        """
        candidates = (
            Campionato.query.filter_by(is_active=True)
            .order_by(Campionato.created_at.desc())
            .all()
        )

        # Status is derived from related gare; computed once per row.
        active: list[Campionato] = []
        completed: list[Campionato] = []
        terminal_statuses = {
            TournamentStatus.COMPLETED.value,
            TournamentStatus.TERMINATED.value,
        }
        for c in candidates:
            if c.get_status() in terminal_statuses:
                completed.append(c)
            else:
                active.append(c)

        completed_shown = completed[:HOMEPAGE_COMPLETED_LIMIT]
        campionatos_to_show = active + completed_shown

        standalone_garas = (
            Gara.query.filter_by(campionato_id=None)
            .filter(Gara.status != GaraStatus.SETUP.value)
            .order_by(Gara.date.desc())
            .limit(5)
            .all()
        )

        if not campionatos_to_show and not standalone_garas:
            return None

        tournaments_data = [
            HomepageService._build_tournament_data(c) for c in campionatos_to_show
        ]

        return {
            "tournaments_data": tournaments_data,
            "active_campionatos": campionatos_to_show,
            "active_count": len(active),
            "completed_total": len(completed),
            "completed_shown": len(completed_shown),
            "standalone_garas": standalone_garas,
        }

    @staticmethod
    def _build_tournament_data(campionato: Campionato) -> Dict[str, Any]:
        """Build display data for a single campionato."""
        upcoming_garas = (
            Gara.query.filter(
                Gara.campionato_id == campionato.id,
                Gara.date >= date.today(),
            )
            .order_by(Gara.date)
            .limit(3)
            .all()
        )

        completed_garas = (
            Gara.query.filter(
                Gara.campionato_id == campionato.id,
                Gara.status == GaraStatus.COMPLETED.value,
            )
            .order_by(Gara.date.desc())
            .all()
        )

        service = TournamentService()
        general_classification = service.calculate_general_classification(
            campionato.id
        )

        top_classifications = [
            HomepageService._to_classification_namespace(position, player_data)
            for position, player_data in general_classification[:5]
        ]

        return {
            "campionato": campionato,
            "upcoming_garas": upcoming_garas,
            "completed_garas": completed_garas,
            "top_classifications": top_classifications,
        }

    @staticmethod
    def _to_classification_namespace(
        position: int, player_data: Dict[str, Any]
    ) -> SimpleNamespace:
        """Convert classification tuple into a SimpleNamespace for the template."""
        return SimpleNamespace(
            position=position,
            user=SimpleNamespace(username=player_data.get("username", "N/A")),
            total_matches_won=player_data.get("total_matches_won", 0),
            matches_won=player_data.get("total_matches_won", 0),
            total_rack_difference=player_data.get("total_rack_difference", 0),
            total_spot_shot_wins=player_data.get("total_spot_shot_wins", 0),
        )
