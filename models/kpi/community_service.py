"""
Module: models/kpi/community_service.py
Purpose: Business & Community KPIs (director performance, community health, power users)
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Any

from sqlalchemy import func

from ..base import db, utc_now
from ..match.models import Match, TrioMatch
from ..status_enum import GaraStatus, MatchStatus
from .metrics_service import MetricsService


class CommunityService:
    """Director performance, community health, and power user metrics."""

    @staticmethod
    def get_director_performance() -> List[Dict[str, Any]]:
        """
        Get performance metrics for tournament directors.
        Metrics:
        - Volume: Number of Garas managed
        - Saturation: Avg (Inscriptions / Max Participants) * 100
        """
        from collections import defaultdict
        from sqlalchemy.orm import selectinload

        from ..user.models import User, DirectorAssignment
        from ..competition.models import Gara

        assignments = DirectorAssignment.query.all()
        director_ids = set(a.user_id for a in assignments)

        garas_with_directors = Gara.query.filter(Gara.director_id.isnot(None)).all()
        for g in garas_with_directors:
            if g.director_id:
                director_ids.add(g.director_id)

        # Batch-load anziche' query per-director nel loop (era N+1):
        # - tutti i director in una sola query (era User.query.get per id);
        # - le assignment gia' caricate in `assignments`, raggruppate per
        #   utente/tipo (erano 2 filter_by per director);
        # - le gare con director_id diretto raggruppate (era 1 filter_by each).
        directors_by_id = {
            u.id: u for u in User.query.filter(User.id.in_(director_ids)).all()
        }
        camp_assign_by_user: Dict[int, list] = defaultdict(list)
        gara_assign_by_user: Dict[int, list] = defaultdict(list)
        for a in assignments:
            if a.entity_type == "campionato":
                camp_assign_by_user[a.user_id].append(a)
            elif a.entity_type == "gara":
                gara_assign_by_user[a.user_id].append(a)
        direct_garas_by_director: Dict[int, list] = defaultdict(list)
        for g in garas_with_directors:
            if g.director_id:
                direct_garas_by_director[g.director_id].append(g)

        results = []

        for d_id in director_ids:
            director = directors_by_id.get(d_id)
            if not director:
                continue

            managed_garas = list(direct_garas_by_director.get(d_id, []))

            for ca in camp_assign_by_user.get(d_id, []):
                if ca.campionato:
                    managed_garas.extend(ca.campionato.gare)

            for ga in gara_assign_by_user.get(d_id, []):
                if ga.gara and ga.gara not in managed_garas:
                    managed_garas.append(ga.gara)

            managed_garas = list(set(managed_garas))

            if not managed_garas:
                continue

            # Re-query with selectinload to avoid N+1 on `g.inscriptions` below.
            # `managed_garas` was assembled from multiple sources with lazy
            # relationships, so each g.inscriptions access would fire its own
            # SELECT otherwise.
            gara_ids = [g.id for g in managed_garas]
            managed_garas = (
                Gara.query.filter(Gara.id.in_(gara_ids))
                .options(selectinload(Gara.inscriptions))
                .all()
            )

            total_garas = len(managed_garas)
            completed_garas = sum(
                1 for g in managed_garas if g.status == GaraStatus.COMPLETED.value
            )

            saturation_sum = 0.0
            saturation_count = 0

            for g in managed_garas:
                if g.max_participants and g.max_participants > 0:
                    insc_count = len(g.inscriptions)
                    saturation = min((insc_count / g.max_participants) * 100, 100.0)
                    saturation_sum += saturation
                    saturation_count += 1

            avg_saturation = (
                round(saturation_sum / saturation_count, 1)
                if saturation_count > 0
                else 0.0
            )

            results.append(
                {
                    "director_id": director.id,
                    "director_name": director.username,
                    "total_garas": total_garas,
                    "completed_garas": completed_garas,
                    "avg_saturation": avg_saturation,
                }
            )

        results.sort(key=lambda x: x["avg_saturation"], reverse=True)
        return results

    @staticmethod
    def get_community_health() -> Dict[str, Any]:
        """
        Get community health metrics: Stickiness, Virality, Churn.
        """
        # 1. Stickiness: DAU / MAU
        dau = MetricsService.get_dau()
        mau = MetricsService.get_mau()
        stickiness = round((dau / mau * 100), 1) if mau > 0 else 0.0

        # 2. Real Churn: utenti attivi il mese scorso (30-60g fa) ma NON
        #    attivi questo mese (0-30g)
        today = utc_now()
        thirty_days_ago = today - timedelta(days=30)
        sixty_days_ago = today - timedelta(days=60)

        active_last_month = (
            db.session.query(Match.player1_id)
            .filter(
                Match.updated_at >= sixty_days_ago,
                Match.updated_at < thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
            )
            .union(
                db.session.query(Match.player2_id).filter(
                    Match.updated_at >= sixty_days_ago,
                    Match.updated_at < thirty_days_ago,
                    Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                )
            )
            .distinct()
            .all()
        )
        prev_active_ids = {r[0] for r in active_last_month if r[0]}

        active_this_month = (
            db.session.query(Match.player1_id)
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
            )
            .union(
                db.session.query(Match.player2_id).filter(
                    Match.updated_at >= thirty_days_ago,
                    Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                )
            )
            .distinct()
            .all()
        )
        curr_active_ids = {r[0] for r in active_this_month if r[0]}

        churned_count = len(prev_active_ids - curr_active_ids)
        churn_rate = (
            round((churned_count / len(prev_active_ids) * 100), 1)
            if len(prev_active_ids) > 0
            else 0.0
        )

        # 3. Virality: % of matches between New (<30d) and Vet (>30d) users
        recent_matches = (
            Match.query.filter_by(status=MatchStatus.CLOSED_UNILATERALLY.value)
            .order_by(Match.updated_at.desc())
            .limit(100)
            .all()
        )

        viral_matches = 0
        total_sample = 0

        for m in recent_matches:
            if not m.player1 or not m.player2:
                continue

            p1_age = (m.updated_at - m.player1.created_at).days
            p2_age = (m.updated_at - m.player2.created_at).days

            is_p1_new = p1_age <= 30
            is_p2_new = p2_age <= 30

            if (is_p1_new and not is_p2_new) or (not is_p1_new and is_p2_new):
                viral_matches += 1

            total_sample += 1

        virality_score = (
            round((viral_matches / total_sample * 100), 1) if total_sample > 0 else 0.0
        )

        return {
            "stickiness": stickiness,
            "churn_count": churned_count,
            "churn_rate": churn_rate,
            "virality_score": virality_score,
        }

    @staticmethod
    def get_power_users(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top users by activity in the last 30 days.

        Counts both regular matches (player1_id/player2_id on Match)
        and trio matches (player1_id/player2_id/player3_id on TrioMatch).
        """
        from ..user.models import User

        thirty_days_ago = utc_now() - timedelta(days=30)

        p1_counts = (
            db.session.query(
                Match.player1_id.label("user_id"), func.count(Match.id).label("count")
            )
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                Match.is_trio == False,  # noqa: E712
            )
            .group_by(Match.player1_id)
            .all()
        )

        p2_counts = (
            db.session.query(
                Match.player2_id.label("user_id"), func.count(Match.id).label("count")
            )
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                Match.is_trio == False,  # noqa: E712
            )
            .group_by(Match.player2_id)
            .all()
        )

        trio_p1_counts = (
            db.session.query(
                TrioMatch.player1_id.label("user_id"),
                func.count(TrioMatch.id).label("count"),
            )
            .join(Match, Match.id == TrioMatch.match_id)
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                Match.is_trio == True,  # noqa: E712
            )
            .group_by(TrioMatch.player1_id)
            .all()
        )

        trio_p2_counts = (
            db.session.query(
                TrioMatch.player2_id.label("user_id"),
                func.count(TrioMatch.id).label("count"),
            )
            .join(Match, Match.id == TrioMatch.match_id)
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                Match.is_trio == True,  # noqa: E712
            )
            .group_by(TrioMatch.player2_id)
            .all()
        )

        trio_p3_counts = (
            db.session.query(
                TrioMatch.player3_id.label("user_id"),
                func.count(TrioMatch.id).label("count"),
            )
            .join(Match, Match.id == TrioMatch.match_id)
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
                Match.is_trio == True,  # noqa: E712
            )
            .group_by(TrioMatch.player3_id)
            .all()
        )

        user_counts: Dict[int, int] = {}
        for counts in [
            p1_counts,
            p2_counts,
            trio_p1_counts,
            trio_p2_counts,
            trio_p3_counts,
        ]:
            for r in counts:
                if r.user_id:
                    user_counts[r.user_id] = user_counts.get(r.user_id, 0) + r.count

        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]

        results = []
        for uid, count in sorted_users:
            user = User.query.get(uid)
            if user:
                results.append(
                    {"user_id": uid, "username": user.username, "match_count": count}
                )

        return results
