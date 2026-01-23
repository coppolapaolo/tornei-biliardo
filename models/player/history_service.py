"""
Module: models/player/history_service.py
Purpose: Service for querying player match/gara/campionato history with filters
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List, Tuple, Any, Dict

from flask import request
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

from models.base import db
from models.match.models import Match, TrioMatch
from models.competition.models import Gara, Inscription
from models.campionato.models import Campionato
from models.user.models import User
from models.status_enum import MatchStatus, GaraStatus, Discipline


@dataclass
class HistoryFilters:
    """Filter parameters for history queries."""

    discipline: Optional[str] = None  # Discipline enum value (e.g., '8_ball')
    venue: Optional[str] = None  # Location string (partial match)
    opponent_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    result: Optional[str] = None  # 'won', 'lost', or None for all
    campionato_id: Optional[int] = None
    gara_id: Optional[int] = None
    completed_only: bool = True  # For gare: show only completed

    @classmethod
    def from_request(cls, request_args: Any) -> "HistoryFilters":
        """Create filters from Flask request args."""
        return cls(
            discipline=request_args.get("discipline") or None,
            venue=request_args.get("venue") or None,
            opponent_id=request_args.get("opponent_id", type=int),
            date_from=cls._parse_date(request_args.get("date_from")),
            date_to=cls._parse_date(request_args.get("date_to")),
            result=request_args.get("result") or None,
            campionato_id=request_args.get("campionato_id", type=int),
            gara_id=request_args.get("gara_id", type=int),
            completed_only=request_args.get("completed_only", "true").lower() == "true",
        )

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None


@dataclass
class MatchStats:
    """Aggregated statistics for filtered match history."""

    total_matches: int
    won_matches: int
    lost_matches: int
    win_percentage: float
    total_racks_won: int
    total_racks_lost: int


@dataclass
class GaraStats:
    """Aggregated statistics for filtered gara history."""

    total_gare: int
    first_places: int  # Times finished 1st
    podiums: int  # Times finished 1st, 2nd, or 3rd
    total_matches_played: int


class PlayerHistoryService:
    """Service for querying player match/gara/campionato history with filters."""

    # =========================================================================
    # PARTITE (Matches)
    # =========================================================================

    @staticmethod
    def get_match_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Pagination, MatchStats]:
        """Get paginated match history with filters.

        Returns:
            Tuple of (pagination object, aggregated stats for filtered matches)
        """
        # Base query - completed matches where user participated
        # Use outerjoin for Gara to include standalone matches (gara_id = NULL)
        # Also outerjoin TrioMatch to include trio matches where user is one of 3 players
        query = (
            db.session.query(Match)
            .outerjoin(Gara, Gara.id == Match.gara_id)
            .outerjoin(Campionato, Campionato.id == Gara.campionato_id)
            .outerjoin(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                Match.status == MatchStatus.COMPLETED.value,
                Match.is_bye == False,  # noqa: E712
                or_(
                    # Regular matches (not trio)
                    and_(
                        Match.is_trio == False,  # noqa: E712
                        or_(
                            Match.player1_id == user_id,
                            Match.player2_id == user_id,
                        ),
                    ),
                    # Trio matches - check all 3 player positions
                    and_(
                        Match.is_trio == True,  # noqa: E712
                        or_(
                            TrioMatch.player1_id == user_id,
                            TrioMatch.player2_id == user_id,
                            TrioMatch.player3_id == user_id,
                        ),
                    ),
                ),
            )
            .options(
                joinedload(Match.player1),
                joinedload(Match.player2),
                joinedload(Match.gara).joinedload(Gara.campionato),
                joinedload(Match.trio_match),
            )
        )

        # Apply filters
        query = PlayerHistoryService._apply_match_filters(query, user_id, filters)

        # Order by date descending
        query = query.order_by(
            Gara.date.desc().nullslast(), Match.created_at.desc()
        )

        # Calculate stats BEFORE pagination (on filtered results)
        stats = PlayerHistoryService._calculate_match_stats(query.all(), user_id)

        # Re-run query for pagination (SQLAlchemy pagination needs fresh query)
        # Use outerjoin for Gara to include standalone matches (gara_id = NULL)
        # Also outerjoin TrioMatch to include trio matches
        query = (
            db.session.query(Match)
            .outerjoin(Gara, Gara.id == Match.gara_id)
            .outerjoin(Campionato, Campionato.id == Gara.campionato_id)
            .outerjoin(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                Match.status == MatchStatus.COMPLETED.value,
                Match.is_bye == False,  # noqa: E712
                or_(
                    # Regular matches (not trio)
                    and_(
                        Match.is_trio == False,  # noqa: E712
                        or_(
                            Match.player1_id == user_id,
                            Match.player2_id == user_id,
                        ),
                    ),
                    # Trio matches - check all 3 player positions
                    and_(
                        Match.is_trio == True,  # noqa: E712
                        or_(
                            TrioMatch.player1_id == user_id,
                            TrioMatch.player2_id == user_id,
                            TrioMatch.player3_id == user_id,
                        ),
                    ),
                ),
            )
            .options(
                joinedload(Match.player1),
                joinedload(Match.player2),
                joinedload(Match.gara).joinedload(Gara.campionato),
                joinedload(Match.trio_match),
            )
        )
        query = PlayerHistoryService._apply_match_filters(query, user_id, filters)
        query = query.order_by(
            Gara.date.desc().nullslast(), Match.created_at.desc()
        )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination, stats

    @staticmethod
    def _apply_match_filters(
        query: Any, user_id: int, filters: HistoryFilters
    ) -> Any:
        """Apply filter conditions to match query."""

        # Discipline filter (check both match override and gara discipline)
        if filters.discipline:
            query = query.filter(
                or_(
                    Match.discipline == filters.discipline,
                    and_(
                        Match.discipline.is_(None),
                        Gara.discipline == filters.discipline,
                    ),
                )
            )

        # Venue filter (partial match on location)
        if filters.venue:
            query = query.filter(Gara.location.ilike(f"%{filters.venue}%"))

        # Opponent filter
        if filters.opponent_id:
            query = query.filter(
                or_(
                    and_(
                        Match.player1_id == user_id,
                        Match.player2_id == filters.opponent_id,
                    ),
                    and_(
                        Match.player2_id == user_id,
                        Match.player1_id == filters.opponent_id,
                    ),
                )
            )

        # Date range filter
        if filters.date_from:
            query = query.filter(Gara.date >= filters.date_from)
        if filters.date_to:
            query = query.filter(Gara.date <= filters.date_to)

        # Result filter
        if filters.result == "won":
            query = query.filter(Match.winner_id == user_id)
        elif filters.result == "lost":
            query = query.filter(
                Match.winner_id.isnot(None), Match.winner_id != user_id
            )

        # Campionato filter
        if filters.campionato_id:
            query = query.filter(Gara.campionato_id == filters.campionato_id)

        # Gara filter
        if filters.gara_id:
            query = query.filter(Match.gara_id == filters.gara_id)

        return query

    @staticmethod
    def _calculate_match_stats(matches: List[Match], user_id: int) -> MatchStats:
        """Calculate aggregated stats for filtered matches.

        Handles both regular 2-player matches and trio matches.
        For trio matches, 'lost' only counts if someone else won (not ties).
        """
        total = len(matches)
        won = sum(1 for m in matches if m.winner_id == user_id)
        # For losses: count matches where someone else won (not ties, not wins)
        lost = sum(
            1 for m in matches
            if m.winner_id is not None and m.winner_id != user_id
        )

        racks_won = 0
        racks_lost = 0
        for m in matches:
            if m.is_trio and m.trio_match:
                # Trio match: find user's racks and sum opponents' racks
                trio = m.trio_match
                if trio.player1_id == user_id:
                    racks_won += trio.player1_racks or 0
                    racks_lost += (trio.player2_racks or 0) + (trio.player3_racks or 0)
                elif trio.player2_id == user_id:
                    racks_won += trio.player2_racks or 0
                    racks_lost += (trio.player1_racks or 0) + (trio.player3_racks or 0)
                elif trio.player3_id == user_id:
                    racks_won += trio.player3_racks or 0
                    racks_lost += (trio.player1_racks or 0) + (trio.player2_racks or 0)
            else:
                # Regular 2-player match
                if m.player1_id == user_id:
                    racks_won += m.player1_score or 0
                    racks_lost += m.player2_score or 0
                else:
                    racks_won += m.player2_score or 0
                    racks_lost += m.player1_score or 0

        return MatchStats(
            total_matches=total,
            won_matches=won,
            lost_matches=lost,
            win_percentage=round((won / total * 100) if total else 0, 1),
            total_racks_won=racks_won,
            total_racks_lost=racks_lost,
        )

    # =========================================================================
    # GARE (Competitions)
    # =========================================================================

    @staticmethod
    def get_gara_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Pagination, GaraStats]:
        """Get paginated gara history with filters.

        Returns gare where user had an inscription (active or completed).
        """
        from models.classification.models import RoundClassification

        # Subquery for user's inscriptions
        inscribed_gara_ids = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .scalar_subquery()
        )

        # Base query
        query = (
            db.session.query(Gara)
            .outerjoin(Campionato, Campionato.id == Gara.campionato_id)
            .filter(Gara.id.in_(inscribed_gara_ids))
            .options(
                joinedload(Gara.campionato),
                joinedload(Gara.round_classifications),
            )
        )

        # Filter by status
        if filters.completed_only:
            query = query.filter(Gara.status == GaraStatus.COMPLETED.value)

        # Apply other filters
        query = PlayerHistoryService._apply_gara_filters(query, filters)

        # Order by date descending
        query = query.order_by(Gara.date.desc().nullslast(), Gara.id.desc())

        # Calculate stats
        all_gare = query.all()
        stats = PlayerHistoryService._calculate_gara_stats(all_gare, user_id)

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination, stats

    @staticmethod
    def _apply_gara_filters(query: Any, filters: HistoryFilters) -> Any:
        """Apply filter conditions to gara query."""

        # Discipline filter
        if filters.discipline:
            query = query.filter(Gara.discipline == filters.discipline)

        # Venue filter
        if filters.venue:
            query = query.filter(Gara.location.ilike(f"%{filters.venue}%"))

        # Date range filter
        if filters.date_from:
            query = query.filter(Gara.date >= filters.date_from)
        if filters.date_to:
            query = query.filter(Gara.date <= filters.date_to)

        # Campionato filter
        if filters.campionato_id:
            query = query.filter(Gara.campionato_id == filters.campionato_id)

        return query

    @staticmethod
    def _calculate_gara_stats(gare: List[Gara], user_id: int) -> GaraStats:
        """Calculate aggregated stats for gare history."""
        from models.classification.models import RoundClassification

        total = len(gare)
        first_places = 0
        podiums = 0
        total_matches = 0

        for gara in gare:
            # Get user's final position in this gara
            final_classification = (
                db.session.query(RoundClassification)
                .filter(
                    RoundClassification.gara_id == gara.id,
                    RoundClassification.user_id == user_id,
                    RoundClassification.round_number == gara.current_round,
                )
                .first()
            )

            if final_classification:
                if final_classification.position == 1:
                    first_places += 1
                if final_classification.position <= 3:
                    podiums += 1
                total_matches += final_classification.matches_won

        return GaraStats(
            total_gare=total,
            first_places=first_places,
            podiums=podiums,
            total_matches_played=total_matches,
        )

    # =========================================================================
    # CAMPIONATI
    # =========================================================================

    @staticmethod
    def get_campionato_history(
        user_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> Pagination:
        """Get paginated campionato history.

        Returns campionati where user participated in at least one gara.
        """
        # Subquery for gare where user inscribed
        inscribed_gara_ids = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .subquery()
        )

        # Campionati that have gare where user inscribed
        campionato_ids_with_participation = (
            db.session.query(Gara.campionato_id)
            .filter(
                Gara.id.in_(inscribed_gara_ids),
                Gara.campionato_id.isnot(None),
            )
            .distinct()
            .subquery()
        )

        # Query campionati
        query = (
            db.session.query(Campionato)
            .filter(
                Campionato.id.in_(campionato_ids_with_participation),
                Campionato.is_deleted == False,  # noqa: E712
            )
            .order_by(Campionato.created_at.desc())
        )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination

    # =========================================================================
    # FILTER OPTIONS (for dropdowns)
    # =========================================================================

    @staticmethod
    def get_filter_options(user_id: int) -> Dict[str, Any]:
        """Get available filter options for UI dropdowns.

        Returns dict with:
        - venues: List of unique venue names
        - opponents: List of User objects
        - campionati: List of Campionato objects
        - disciplines: List of (value, display_name) tuples
        """
        # Unique venues from user's match history
        venues_query = (
            db.session.query(Gara.location)
            .join(Match, Match.gara_id == Gara.id)
            .filter(
                Gara.location.isnot(None),
                Gara.location != "",
                or_(
                    Match.player1_id == user_id,
                    Match.player2_id == user_id,
                ),
            )
            .distinct()
            .order_by(Gara.location)
        )
        venues = [v[0] for v in venues_query.all()]

        # Unique opponents from user's match history
        # Get all player IDs that user has faced
        opponent_ids_as_p1 = (
            db.session.query(Match.player2_id)  # type: ignore[call-overload]
            .filter(
                Match.player1_id == user_id,
                Match.player2_id.isnot(None),
                Match.is_bye == False,  # noqa: E712
            )
            .distinct()
        )

        opponent_ids_as_p2 = (
            db.session.query(Match.player1_id)  # type: ignore[call-overload]
            .filter(
                Match.player2_id == user_id,
                Match.player1_id.isnot(None),
            )
            .distinct()
        )

        # Use scalar_subquery() for IN() to avoid SQLAlchemy warnings
        opponent_ids_subq = opponent_ids_as_p1.union(opponent_ids_as_p2).scalar_subquery()

        opponents = (
            db.session.query(User)
            .filter(User.id.in_(opponent_ids_subq))
            .order_by(User.username)
            .all()
        )

        # Campionati where user participated
        inscribed_gara_ids_subq = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .scalar_subquery()
        )

        campionato_ids_subq = (
            db.session.query(Gara.campionato_id)
            .filter(
                Gara.id.in_(inscribed_gara_ids_subq),
                Gara.campionato_id.isnot(None),
            )
            .distinct()
            .scalar_subquery()
        )

        campionati = (
            db.session.query(Campionato)
            .filter(
                Campionato.id.in_(campionato_ids_subq),
                Campionato.is_deleted == False,  # noqa: E712
            )
            .order_by(Campionato.created_at.desc())
            .all()
        )

        # Disciplines - use enum
        disciplines = [(d.value, d.display_name) for d in Discipline]

        return {
            "venues": venues,
            "opponents": opponents,
            "campionati": campionati,
            "disciplines": disciplines,
        }
