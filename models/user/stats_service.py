# models/user/stats_service.py
"""UserStatsService - User statistics and analytics management.

This service extracts user statistics responsibilities from UserService
following Task 1.3 decomposition patterns.
"""

from typing import List, Dict, Any, Tuple
from sqlalchemy.engine.row import Row
from sqlalchemy import func
from models.base import db
from models.user.models import User
from models.transaction.manager import read_only


class UserStatsService:
    """Service for user statistics and analytics.

    **Responsibilities:**
    - User match statistics and performance metrics
    - Tournament participation tracking
    - Win/loss records and percentages
    - User analytics and reporting

    **Transaction Management:**
    - Uses @read_only(domain="user") for query operations
    - Statistics are read-only operations
    - No state changes in this service

    **Integration:**
    - Aggregates data from match, competition, and classification domains
    - Provides analytics for user dashboard and profiles
    - Supports reporting and administrative overview
    """

    @staticmethod
    @read_only(domain="user")
    def get_user_stats(user_id: int) -> Dict[str, Any]:
        """Get comprehensive user match and tournament statistics.

        Args:
            user_id: ID of user to calculate statistics for

        Returns:
            Dict[str, Any]: Dictionary containing match and tournament statistics

        Raises:
            ValueError: If user not found

        Statistics Included:
            - total_matches: Count of completed matches
            - won_matches: Count of matches won
            - lost_matches: Count of matches lost
            - win_percentage: Win rate as percentage (0-100)
            - inscription_count: Number of tournament registrations
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Import models needed for statistics
        from models.match.models import Match, TrioMatch
        from models.competition.models import Inscription
        from models.status_enum import MatchStatus

        # Calculate completed match statistics (includes trio matches)
        # Regular matches: check player1_id or player2_id
        # Trio matches: also check TrioMatch.player3_id
        total_matches = (
            Match.query.outerjoin(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                db.or_(
                    # Regular matches (not trio)
                    db.and_(
                        Match.is_trio == False,  # noqa: E712
                        db.or_(
                            Match.player1_id == user_id,
                            Match.player2_id == user_id,
                        ),
                    ),
                    # Trio matches - check all 3 player positions
                    db.and_(
                        Match.is_trio == True,  # noqa: E712
                        db.or_(
                            TrioMatch.player1_id == user_id,
                            TrioMatch.player2_id == user_id,
                            TrioMatch.player3_id == user_id,
                        ),
                    ),
                ),
                Match.status == MatchStatus.COMPLETED.value,
            )
            .count()
        )

        won_matches = Match.query.filter(
            Match.winner_id == user_id, Match.status == MatchStatus.COMPLETED.value
        ).count()

        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

        # Tournament participation statistics
        inscription_count = Inscription.query.filter_by(user_id=user_id).count()

        return {
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": lost_matches,
            "win_percentage": round(win_percentage, 1),
            "inscription_count": inscription_count,
        }

    @staticmethod
    @read_only(domain="user")
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get detailed user statistics for player profile page.

        Returns statistics expected by _user_general_stats.html template:
        - tournaments_played: Count of distinct campionati with completed gare
        - provas_played: Count of gare (provas) user has inscriptions for
        - won_matches: Count of matches won
        - win_percentage: Win rate as percentage

        Args:
            user_id: ID of user to get statistics for

        Returns:
            Dict[str, Any]: Complete user statistics for profile display
        """
        # Get base stats
        base_stats = UserStatsService.get_user_stats(user_id)

        # Import additional models for extended stats
        from models.competition.models import Inscription, Gara
        from models.status_enum import GaraStatus

        # Count distinct campionati the user participated in (via completed gare)
        tournaments_played = (
            db.session.query(func.count(func.distinct(Gara.campionato_id)))
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Gara.status == GaraStatus.COMPLETED.value,
            )
            .scalar()
            or 0
        )

        # Count gare (provas) where user is inscribed
        provas_played = (
            db.session.query(func.count(Inscription.id))
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Gara.status == GaraStatus.COMPLETED.value,
            )
            .scalar()
            or 0
        )

        return {
            **base_stats,
            "tournaments_played": tournaments_played,
            "provas_played": provas_played,
        }

    @staticmethod
    @read_only(domain="user")
    def get_users_with_stats() -> List[Row[Tuple[User, int, int, Any]]]:
        """Get all users with aggregated statistics in single query.

        Returns:
            List[Row]: List of rows containing User and statistics

        Row Structure:
            - User: User model instance
            - total_inscriptions: Count of tournament registrations
            - total_matches: Count of completed matches
            - won_matches: Count of matches won

        Performance:
            - Uses subqueries to avoid cartesian product issues
            - More efficient than individual user stat queries
            - Useful for leaderboards and user listings
        """
        from models.match.models import Match
        from models.competition.models import Inscription
        from models.status_enum import MatchStatus

        # Subquery for inscription counts per user
        inscription_subq = (
            db.session.query(
                Inscription.user_id.label("user_id"),
                func.count(Inscription.id).label("total_inscriptions"),
            )
            .group_by(Inscription.user_id)
            .subquery()
        )

        # Separate subquery for player2 matches
        match_subq_p2 = (
            db.session.query(
                Match.player2_id.label("user_id"),
                func.count(Match.id).label("total_matches"),
                func.sum(
                    db.case(
                        (Match.winner_id == Match.player2_id, 1),
                        else_=0,
                    )
                ).label("won_as_p2"),
            )
            .filter(
                Match.status == MatchStatus.COMPLETED.value,
                Match.player2_id.isnot(None),
            )
            .group_by(Match.player2_id)
            .subquery()
        )

        # Subquery for player1 matches
        match_subq_p1 = (
            db.session.query(
                Match.player1_id.label("user_id"),
                func.count(Match.id).label("total_matches"),
                func.sum(
                    db.case(
                        (Match.winner_id == Match.player1_id, 1),
                        else_=0,
                    )
                ).label("won_as_p1"),
            )
            .filter(
                Match.status == MatchStatus.COMPLETED.value,
                Match.player1_id.isnot(None),
            )
            .group_by(Match.player1_id)
            .subquery()
        )

        # Subquery for trio player3 matches
        from models.match.models import TrioMatch

        match_subq_p3 = (
            db.session.query(
                TrioMatch.player3_id.label("user_id"),
                func.count(TrioMatch.id).label("total_matches"),
                func.sum(
                    db.case(
                        (Match.winner_id == TrioMatch.player3_id, 1),
                        else_=0,
                    )
                ).label("won_as_p3"),
            )
            .join(Match, Match.id == TrioMatch.match_id)
            .filter(
                Match.status == MatchStatus.COMPLETED.value,
                TrioMatch.player3_id.isnot(None),
            )
            .group_by(TrioMatch.player3_id)
            .subquery()
        )

        # Main query joining user with subqueries
        users_with_stats = (
            db.session.query(
                User,
                func.coalesce(inscription_subq.c.total_inscriptions, 0).label(
                    "total_inscriptions"
                ),
                (
                    func.coalesce(match_subq_p1.c.total_matches, 0)
                    + func.coalesce(match_subq_p2.c.total_matches, 0)
                    + func.coalesce(match_subq_p3.c.total_matches, 0)
                ).label("total_matches"),
                (
                    func.coalesce(match_subq_p1.c.won_as_p1, 0)
                    + func.coalesce(match_subq_p2.c.won_as_p2, 0)
                    + func.coalesce(match_subq_p3.c.won_as_p3, 0)
                ).label("won_matches"),
            )
            .filter(User.role != "admin")  # Exclude special admin user
            .outerjoin(inscription_subq, inscription_subq.c.user_id == User.id)
            .outerjoin(match_subq_p1, match_subq_p1.c.user_id == User.id)
            .outerjoin(match_subq_p2, match_subq_p2.c.user_id == User.id)
            .outerjoin(match_subq_p3, match_subq_p3.c.user_id == User.id)
            .all()
        )

        return users_with_stats

    @staticmethod
    @read_only(domain="user")
    def get_user_matches(user_id: int, limit: int = 10) -> List:
        """Get recent completed matches for a user.

        Args:
            user_id: ID of user to get matches for
            limit: Maximum number of matches to return (default: 10)

        Returns:
            List[Match]: List of recent completed matches ordered by date

        Query Details:
            - Only includes completed matches
            - Ordered by most recent first (updated_at desc)
            - Includes matches where user was either player1 or player2
            - Includes trio matches where user was any of the 3 players
        """
        from models.competition.models import Gara
        from models.match.models import Match, TrioMatch
        from models.status_enum import MatchStatus

        # Use outerjoin to include trio matches
        # For regular matches: check player1_id or player2_id
        # For trio matches: check TrioMatch.player1_id/player2_id/player3_id
        #
        # Il join (inner) su Gara scarta i match la cui gara non è
        # raggiungibile: gara_id NULL (il FK è ON DELETE SET NULL) oppure gara
        # soft-deleted, che `register_soft_delete_filters` aggiunge qui come
        # `AND gara.deleted_at IS NULL` e che renderebbe `match.gara` None nei
        # template (500 su /admin/user/<id>, incidente TORNEI-BILIARDO-5G).
        matches = (
            Match.query.join(Gara, Match.gara_id == Gara.id)
            .outerjoin(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                db.or_(
                    # Regular matches (not trio)
                    db.and_(
                        Match.is_trio == False,  # noqa: E712
                        db.or_(
                            Match.player1_id == user_id,
                            Match.player2_id == user_id,
                        ),
                    ),
                    # Trio matches - check all 3 player positions
                    db.and_(
                        Match.is_trio == True,  # noqa: E712
                        db.or_(
                            TrioMatch.player1_id == user_id,
                            TrioMatch.player2_id == user_id,
                            TrioMatch.player3_id == user_id,
                        ),
                    ),
                ),
                Match.status == MatchStatus.COMPLETED.value,
            )
            .order_by(Match.updated_at.desc())
            .limit(limit)
            .all()
        )

        return matches

    @staticmethod
    @read_only(domain="user")
    def get_user_classifications(user_id: int) -> List:
        """Get user tournament classifications ordered by date.

        Args:
            user_id: ID of user to get classifications for

        Returns:
            List[Classification]: List of user's tournament classifications

        Query Details:
            - Ordered by most recent first (created_at desc)
            - Includes all classifications across different tournaments
            - Shows user's performance and ranking history
        """
        from models.classification.models import Classification

        classifications = (
            Classification.query.filter_by(user_id=user_id)
            .order_by(Classification.created_at.desc())
            .all()
        )

        return classifications

    @staticmethod
    @read_only(domain="user")
    def calculate_user_performance_metrics(user_id: int) -> Dict[str, Any]:
        """Calculate advanced performance metrics and ratings for a user.

        Args:
            user_id: ID of user to calculate metrics for

        Returns:
            Dict[str, Any]: Extended statistics with performance ratings

        Additional Metrics:
            - performance_rating: Qualitative rating based on win percentage
              - Excellent: >= 70% win rate
              - Good: >= 50% win rate
              - Average: >= 30% win rate
              - Needs Improvement: < 30% win rate
              - No Data: No completed matches
            - matches_per_tournament: Average matches played per tournament
        """
        stats = UserStatsService.get_user_stats(user_id)

        # Calculate derived performance metrics and qualitative ratings
        # Determine performance rating based on win percentage thresholds
        if stats["total_matches"] > 0:
            win_pct = stats["win_percentage"]
            if win_pct >= 70:
                performance_rating = "Excellent"
            elif win_pct >= 50:
                performance_rating = "Good"
            elif win_pct >= 30:
                performance_rating = "Average"
            else:
                performance_rating = "Needs Improvement"
        else:
            performance_rating = "No Data"

        return {
            **stats,
            "performance_rating": performance_rating,
            "matches_per_tournament": (
                stats["total_matches"] / stats["inscription_count"]
                if stats["inscription_count"] > 0
                else 0
            ),
        }
