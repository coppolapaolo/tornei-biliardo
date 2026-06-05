# models/dashboard/section_builders.py
"""Dashboard section builder methods.

Extracted from services.py for maintainability (Round 4 P3).
Builds player, individual match, challenge, and gamification sections.
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.match.models import Match as TournamentMatch
from models.status_enum import GaraStatus, MatchStatus

from .view_models import _user_is_match_participant


class DashboardSectionBuilder:
    """Builds dashboard sections for player-like views."""

    @staticmethod
    def build_player_sections(user_id: int, selected: Optional[Campionato]) -> dict:
        """Costruisce available_garas, my_inscriptions, current_matches,
        recent_matches per il campionato selezionato."""
        available_garas: List[Gara] = []
        my_regs: List[Inscription] = []
        my_upcoming: List[TournamentMatch] = []
        my_recent: List[TournamentMatch] = []

        if not selected:
            return {
                "available_garas": available_garas,
                "my_inscriptions": my_regs,
                "current_matches": my_upcoming,
                "recent_matches": my_recent,
            }

        subq_my_gara_ids = (
            select(Inscription.gara_id)
            .where(Inscription.user_id == user_id)
            .scalar_subquery()
        )

        available_garas = (
            db.session.query(Gara)
            .filter(
                Gara.campionato_id == selected.id,
                Gara.status == GaraStatus.INSCRIPTION.value,
                ~Gara.id.in_(subq_my_gara_ids),
            )
            .order_by(Gara.date.asc().nullslast(), Gara.number.asc())
            .all()
        )

        my_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id == selected.id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast(), Gara.number.desc())
            .all()
        )

        # Partite attive (solo in attesa e in corso, NO completate - quelle vanno nello storico)
        my_upcoming = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value]),  # type: ignore[attr-defined]
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .limit(10)
            .all()
        )

        my_recent = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                Gara.campionato_id == selected.id,
                TournamentMatch.status == MatchStatus.COMPLETED.value,
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .limit(10)
            .all()
        )

        return {
            "available_garas": available_garas,
            "my_inscriptions": my_regs,
            "current_matches": my_upcoming,
            "recent_matches": my_recent,
        }

    @staticmethod
    def build_individual_match_sections(user_id: int) -> dict:
        """Build individual match proposal sections for user."""
        from ..individual_match.services import IndividualMatchService
        from ..individual_match.models import IndividualMatch

        # Get user's match proposals
        proposals = IndividualMatchService.get_user_proposals(
            user_id, include_expired=False
        )

        # Get recent individual matches
        recent_individual_matches = (
            db.session.query(IndividualMatch)
            .filter(
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            )
            .order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        # Calculate match opportunities (open proposals in user's locations)
        from ..individual_match.models import PlayerAvailability

        user_locations = {
            av.location
            for av in db.session.query(PlayerAvailability)
            .filter_by(user_id=user_id, is_available=True)
            .all()
        }

        # Also include locations where user has played before
        played_locations = {match.location for match in recent_individual_matches}

        user_locations.union(played_locations)

        # Get opportunities - open proposals in eligible locations
        opportunities = proposals.get("available", [])

        return {
            "match_proposals": proposals,
            "individual_matches": recent_individual_matches,
            "match_opportunities": opportunities[:5],  # Limit to top 5 opportunities
        }

    @staticmethod
    def build_challenge_sections(
        user_id: int, selected_campionato: Optional[Campionato]
    ) -> dict:
        """Build challenge sections for user."""
        from ..competition.gara_challenge_service import GaraChallengeService
        from ..competition.gara_challenge import GaraChallenge

        available_challenges = []
        player_challenge_progress = {}

        # Get all garas where the user is inscribed (both campionato and standalone)
        inscribed_garas = (
            db.session.query(Gara)
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,
            )
            .all()
        )

        # If we have a selected campionato, prioritize its garas
        if selected_campionato:
            campionato_garas = [
                gara
                for gara in inscribed_garas
                if gara.campionato_id == selected_campionato.id
            ]
            # If user is inscribed in campionato garas, use those; otherwise use all inscribed garas
            target_garas = campionato_garas if campionato_garas else inscribed_garas
        else:
            # No selected campionato, use all inscribed garas
            target_garas = inscribed_garas

        # Get available challenges for target garas
        for gara in target_garas:
            gara_challenges = (
                db.session.query(GaraChallenge)
                .filter(
                    GaraChallenge.gara_id == gara.id,
                    GaraChallenge.is_active == True,
                )
                .options(joinedload(GaraChallenge.challenge))  # type: ignore[arg-type]
                .all()
            )
            available_challenges.extend(gara_challenges)

            # Get player progress for this gara
            progress = GaraChallengeService.get_user_gara_challenge_progress(
                gara.id, user_id
            )
            if progress:
                player_challenge_progress[user_id] = progress

        return {
            "available_challenges": available_challenges,
            "player_challenge_progress": player_challenge_progress,
        }

    @staticmethod
    def build_gamification_stats(user_id: int) -> dict[str, Any]:
        """Build gamification stats for dashboard widget."""
        from ..gamification.level_service import LevelService
        from ..gamification.streak_service import StreakService

        try:
            progress = LevelService.get_level_progress(user_id)
            streaks = StreakService.get_all_streaks(user_id)

            return {
                "progress": progress,
                "streaks": streaks
            }
        except Exception:
            return {}
