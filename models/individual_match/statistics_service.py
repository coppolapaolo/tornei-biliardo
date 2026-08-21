"""
Module: models/individual_match/statistics_service.py
Purpose: Statistics and query service for individual matches
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from sqlalchemy import func, case
from ..base import db
from .models import (
    MatchProposal,
    IndividualMatch,
    ProposalStatus,
)
from ..location.models import BilliardHall, UserLocationAvailability
from ..status_enum import Discipline, MatchStatus
from ..user.models import User

#: Dall'esito di una partita alla voce del conteggio. Esiste per non
#: riscrivere `if vinto / elif pari / else` in ogni riepilogo: gli esiti sono
#: tre, e li nomina `IndividualMatch.outcome_for`.
_VOCE_ESITO = {"won": "wins", "lost": "losses", "tie": "ties"}


class IndividualMatchStatisticsService:
    """Service for individual match statistics and queries."""

    @staticmethod
    def get_user_matches(
        user_id: int, status_filter: Optional[MatchStatus] = None
    ) -> List[IndividualMatch]:
        """Get individual matches for a user."""
        query = IndividualMatch.query.filter(
            db.or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            )
        )

        if status_filter:
            if isinstance(status_filter, (list, tuple, set)):
                values = [s.value if hasattr(s, "value") else s for s in status_filter]
                query = query.filter(IndividualMatch.status.in_(values))
            else:
                target_status = (
                    status_filter.value
                    if hasattr(status_filter, "value")
                    else status_filter
                )
                query = query.filter(IndividualMatch.status == target_status)

        return query.order_by(IndividualMatch.scheduled_at.desc()).all()

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        # Conta i match conclusi: COMPLETED (forfait/legacy) E VALIDATED
        # (conferma bilaterale, il flusso normale). Contare solo COMPLETED
        # escludeva la maggioranza dei match finiti dalle statistiche.
        matches = IndividualMatchStatisticsService.get_user_matches(
            user_id, [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
        )

        # Gli esiti li dice la partita (`outcome_for`), e sono tre: il
        # pareggio esiste — su «esattamente N» triangoli si finisce pari — e
        # dedurre le sconfitte per differenza lo contava fra quelle.
        esiti = [m.outcome_for(user_id) for m in matches]
        total_matches = len(matches)
        won_matches = esiti.count("won")
        lost_matches = esiti.count("lost")
        tied_matches = esiti.count("tie")

        total_racks_won = sum(m.get_user_score(user_id) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)

        locations_played = {}
        for match in matches:
            # Use location_display property to prefer FK over legacy string
            loc = match.location_display
            if not loc:
                continue  # Skip matches without location
            if loc not in locations_played:
                locations_played[loc] = {"matches": 0, "wins": 0}
            locations_played[loc]["matches"] += 1
            if match.winner_id == user_id:
                locations_played[loc]["wins"] += 1

        # Breakdown per disciplina (pannello "Performance per Disciplina")
        by_discipline_map: Dict[str, Dict[str, Any]] = {}
        for m in matches:
            disc = m.discipline or Discipline.EIGHT_BALL.value
            entry = by_discipline_map.setdefault(
                disc,
                {
                    "discipline": disc,
                    "total_matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                },
            )
            entry["total_matches"] += 1
            entry[_VOCE_ESITO[m.outcome_for(user_id)]] += 1
        for entry in by_discipline_map.values():
            entry["win_percentage"] = (
                entry["wins"] / entry["total_matches"] * 100
                if entry["total_matches"]
                else 0
            )
        by_discipline = sorted(
            by_discipline_map.values(),
            key=lambda e: e["total_matches"],
            reverse=True,
        )

        # Record testa a testa per avversario (pannello "Head-to-Head")
        h2h_map: Dict[int, Dict[str, Any]] = {}
        for m in matches:
            opp_id = m.player2_id if m.player1_id == user_id else m.player1_id
            entry = h2h_map.get(opp_id)
            if entry is None:
                opp = db.session.get(User, opp_id)
                entry = h2h_map[opp_id] = {
                    "opponent_username": opp.username if opp else "?",
                    "total_matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                }
            entry["total_matches"] += 1
            entry[_VOCE_ESITO[m.outcome_for(user_id)]] += 1
        head_to_head = sorted(
            h2h_map.values(), key=lambda e: e["total_matches"], reverse=True
        )

        # Trend recente: matches è ordinato DESC (più recente prima).
        # recent_matches in ordine cronologico ASC, così [-10:] nel template
        # sono i 10 più recenti.
        chrono = list(reversed(matches))
        recent_matches = [
            {"won": m.outcome_for(user_id) == "won", "outcome": m.outcome_for(user_id)}
            for m in chrono
        ]
        last10 = recent_matches[-10:]
        recent_wins = sum(1 for r in last10 if r["outcome"] == "won")
        recent_losses = sum(1 for r in last10 if r["outcome"] == "lost")
        recent_ties = sum(1 for r in last10 if r["outcome"] == "tie")

        # Striscia attuale (dai match più recenti). Un pareggio non è né una
        # vittoria né una sconfitta: interrompe la striscia, non la prosegue.
        current_streak = 0
        current_streak_type = None
        for m in matches:  # DESC
            esito = m.outcome_for(user_id)
            if esito == "tie":
                break
            t = "win" if esito == "won" else "loss"
            if current_streak_type is None:
                current_streak_type, current_streak = t, 1
            elif t == current_streak_type:
                current_streak += 1
            else:
                break

        # Attività mensile (pannello "Attività Mensile")
        monthly_map: Dict[str, Dict[str, Any]] = {}
        for m in chrono:  # ASC
            dt = m.scheduled_at or m.created_at
            if not dt:
                continue
            key = dt.strftime("%Y-%m")
            entry = monthly_map.get(key)
            if entry is None:
                entry = monthly_map[key] = {
                    "month_name": dt.strftime("%b %Y"),
                    "total_matches": 0,
                    "wins": 0,
                }
            entry["total_matches"] += 1
            if m.winner_id == user_id:
                entry["wins"] += 1
        for entry in monthly_map.values():
            entry["win_percentage"] = (
                entry["wins"] / entry["total_matches"] * 100
                if entry["total_matches"]
                else 0
            )
        monthly_activity = list(monthly_map.values())

        return {
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": lost_matches,
            "tied_matches": tied_matches,
            "win_percentage": (
                (won_matches / total_matches * 100) if total_matches > 0 else 0
            ),
            "total_racks_won": total_racks_won,
            "total_racks_played": total_racks_played,
            "rack_win_percentage": (
                (total_racks_won / total_racks_played * 100)
                if total_racks_played > 0
                else 0
            ),
            "locations_played": locations_played,
            "by_discipline": by_discipline,
            "head_to_head": head_to_head,
            "recent_matches": recent_matches,
            "recent_wins": recent_wins,
            "recent_losses": recent_losses,
            "recent_ties": recent_ties,
            "current_streak": current_streak,
            "current_streak_type": current_streak_type,
            "monthly_activity": monthly_activity,
        }

    @staticmethod
    def get_admin_overview() -> Dict[str, Any]:
        """Get admin overview of all individual matches."""
        status_counts = {}
        for status in MatchStatus:
            count = IndividualMatch.query.filter_by(status=status).count()
            status_counts[status.value] = count

        recent_matches = (
            IndividualMatch.query.order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        proposal_counts = {}
        for status in ProposalStatus:
            count = MatchProposal.query.filter_by(status=status).count()
            proposal_counts[status.value] = count

        active_venues = (
            db.session.query(BilliardHall.name)
            .join(
                UserLocationAvailability,
                UserLocationAvailability.billiard_hall_id == BilliardHall.id,
            )
            .filter(UserLocationAvailability.is_available.is_(True))
            .distinct()
            .all()
        )

        return {
            "status_counts": status_counts,
            "recent_matches": recent_matches,
            "proposal_counts": proposal_counts,
            "active_locations": [name for (name,) in active_venues],
            "total_users_with_availability": (
                UserLocationAvailability.query.with_entities(
                    UserLocationAvailability.user_id
                )
                .distinct()
                .count()
            ),
        }

    @staticmethod
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Get user's (venue-based) availability settings and schedule."""
        availability_records = UserLocationAvailability.query.filter_by(
            user_id=user_id
        ).all()

        by_venue: Dict[str, Any] = {}
        for record in availability_records:
            name = record.billiard_hall.name if record.billiard_hall else None
            by_venue.setdefault(name, []).append(record)

        return {
            "availability_records": availability_records,
            "by_venue": by_venue,
            "available_venues": [
                (r.billiard_hall.name if r.billiard_hall else None)
                for r in availability_records
                if r.is_available
            ],
        }

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user.

        Note: This method imports ProposalService to avoid circular imports.
        """
        from .proposal_service import ProposalService

        proposals = ProposalService.get_user_proposals(user_id)
        all_matches = IndividualMatchStatisticsService.get_user_matches(user_id)
        availability = IndividualMatchStatisticsService.get_user_availability(user_id)
        stats = IndividualMatchStatisticsService.get_user_statistics(user_id)

        active_matches = [
            m
            for m in all_matches
            if m.status in [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS]
        ]
        completed_matches = [
            m
            for m in all_matches
            if m.status
            in (MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH)
        ]
        recent_matches = completed_matches[:5]

        return {
            "proposals": proposals,
            "matches": all_matches,
            "active_matches": active_matches,
            "recent_matches": recent_matches,
            "availability": availability,
            "statistics": stats,
        }

    @staticmethod
    def get_frequent_opponents(user_id: int, limit: int = 5) -> List[User]:
        """Get users this player has played most individual matches against.

        Returns users ordered by number of completed matches (most frequent first).
        Useful for suggesting opponents when creating new match proposals.

        Args:
            user_id: The user to find opponents for
            limit: Maximum number of opponents to return (default 5)

        Returns:
            List of User objects, ordered by match frequency (descending)
        """
        # Build a CASE expression to get the opponent's ID regardless of player position
        opponent_id_expr = case(
            (IndividualMatch.player1_id == user_id, IndividualMatch.player2_id),
            else_=IndividualMatch.player1_id,
        )

        # Query to count matches per opponent
        opponent_counts = (
            db.session.query(
                opponent_id_expr.label("opponent_id"),
                func.count().label("match_count"),
            )
            .filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
                IndividualMatch.status.in_(MatchStatus.finished_values()),
            )
            .group_by(opponent_id_expr)
            .order_by(func.count().desc())
            .limit(limit)
            .all()
        )

        if not opponent_counts:
            return []

        # Get the opponent IDs in order
        opponent_ids = [oc.opponent_id for oc in opponent_counts]

        # Fetch users and maintain the order
        users_by_id = {
            u.id: u
            for u in User.query.filter(
                User.id.in_(opponent_ids), User.deleted_at.is_(None)
            ).all()
        }

        # Return in frequency order
        return [users_by_id[oid] for oid in opponent_ids if oid in users_by_id]

    @staticmethod
    def _get_all_opponent_ids(user_id: int) -> set[int]:
        """Get IDs of all players user has played against.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Args:
            user_id: The user to find opponents for

        Returns:
            Set of opponent user IDs
        """
        from ..match.models import Match

        opponent_ids_set: set[int] = set()

        # 1. Individual matches - opponent ID expression
        individual_opponent_expr = case(
            (IndividualMatch.player1_id == user_id, IndividualMatch.player2_id),
            else_=IndividualMatch.player1_id,
        )

        individual_opponents = (
            db.session.query(individual_opponent_expr.label("opponent_id"))
            .filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
                IndividualMatch.status.in_(
                    [
                        MatchStatus.CLOSED_UNILATERALLY.value,
                        MatchStatus.CONFIRMED_BY_BOTH.value,
                    ]
                ),
            )
            .distinct()
            .all()
        )
        opponent_ids_set.update(
            oc.opponent_id for oc in individual_opponents if oc.opponent_id
        )

        # 2. Tournament/gara matches - opponent ID expression
        tournament_opponent_expr = case(
            (Match.player1_id == user_id, Match.player2_id),
            else_=Match.player1_id,
        )

        tournament_opponents = (
            db.session.query(tournament_opponent_expr.label("opponent_id"))
            .filter(
                db.or_(
                    Match.player1_id == user_id,
                    Match.player2_id == user_id,
                ),
                Match.status.in_(
                    [
                        MatchStatus.CLOSED_UNILATERALLY.value,
                        MatchStatus.CONFIRMED_BY_BOTH.value,
                    ]
                ),
            )
            .distinct()
            .all()
        )
        opponent_ids_set.update(
            oc.opponent_id for oc in tournament_opponents if oc.opponent_id
        )

        return opponent_ids_set

    @staticmethod
    def get_eligible_opponents(user_id: int) -> List[User]:
        """Get all unique opponents who have unlocked individual matches.

        Uses can_access("create_match_direct") for consistency with menu visibility.
        This ensures that users who see the menu also appear in opponent lists,
        and users who don't have access to individual matches won't appear.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Returns users ordered alphabetically by username.

        Args:
            user_id: The user to find opponents for

        Returns:
            List of User objects who have unlocked individual matches,
            ordered alphabetically by username
        """
        opponent_ids = IndividualMatchStatisticsService._get_all_opponent_ids(user_id)

        if not opponent_ids:
            return []

        # Fetch users and filter by feature access
        users = (
            User.query.filter(
                User.id.in_(list(opponent_ids)),
                User.deleted_at.is_(None),
            )
            .order_by(User.username)
            .all()
        )

        # Filter by feature access (consistent with menu visibility)
        return [u for u in users if u.can_access("create_match_direct")]

    @staticmethod
    def get_all_opponents(user_id: int, min_level: int = 5) -> List[User]:
        """Get all unique opponents this player has played any match against.

        DEPRECATED: Use get_eligible_opponents() instead for consistency
        with the gamification feature gating system.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Returns users ordered alphabetically by username.
        Filters for users who have reached minimum level for individual matches.

        Args:
            user_id: The user to find opponents for
            min_level: Minimum gamification level required (default 5)

        Returns:
            List of User objects, ordered alphabetically by username
        """
        from ..gamification.models import UserLevel

        opponent_ids = IndividualMatchStatisticsService._get_all_opponent_ids(user_id)

        if not opponent_ids:
            return []

        # Fetch users with level filter, ordered alphabetically
        users = (
            User.query.join(UserLevel, User.id == UserLevel.user_id)
            .filter(
                User.id.in_(list(opponent_ids)),
                User.deleted_at.is_(None),
                UserLevel.current_level >= min_level,
            )
            .order_by(User.username)
            .all()
        )

        return users
