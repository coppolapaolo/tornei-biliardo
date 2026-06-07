"""Leaderboard locale + contributo (ADR-037, riformulazione §11-bis).

Sostituisce il board XP globale (corrosivo) con due assi:
- **Locale**: confronto tra giocatori della stessa ``home_city`` (+ città
  vicine via centroide-sale, ADR-034), ranking per XP totale — *vincibile*.
- **Contributo**: metrica pro-sociale (engagement generato), community-wide.

Calcolo **on-demand** (community piccola): nessuna tabella/migrazione nuova.
Read-only: nessun ``@transactional``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from models.base import db
from utils.geo import haversine_km, clamp_radius

# Raggio default di espansione alle città vicine (taratura = ADR-037 open item).
LOCAL_ZONE_RADIUS_KM = 30

# Pesi della metrica di contributo (taratura ADR-037: costanti documentate,
# facili da affinare sui dati reali). Default: peso uguale per ogni componente.
CONTRIBUTION_WEIGHTS = {
    "drills_engaged": 1,
    "gare_organized": 1,
    "proposals_accepted": 1,
}


class CommunityLeaderboardService:
    """Classifiche locali e di contributo (ADR-037)."""

    # ── Locale (per zona / home_city) ────────────────────────────────────────

    @staticmethod
    def cities_in_zone(home_city: str, radius_km: int = LOCAL_ZONE_RADIUS_KM) -> set:
        """Insieme di città nella zona: la propria + quelle vicine (centroide).

        Match case-insensitive (trim/lower). Se la città del visitatore non ha
        centroide risolvibile, ritorna solo la propria (nessuna espansione).
        """
        from models.individual_match.availability_service import AvailabilityService

        User = CommunityLeaderboardService._User()

        base = (home_city or "").strip()
        if not base:
            return set()

        zone = {base.lower()}
        origin = AvailabilityService.city_centroid_for(base)
        if origin is None:
            return zone

        radius = clamp_radius(radius_km)
        o_lat, o_lng = origin
        # Città distinte dichiarate dagli utenti (escluse vuote).
        rows = (
            db.session.query(
                db.func.distinct(db.func.lower(db.func.trim(User.home_city)))
            )
            .filter(User.home_city.isnot(None))
            .all()
        )
        for (city_norm,) in rows:
            if not city_norm or city_norm in zone:
                continue
            centroid = AvailabilityService.city_centroid_for(city_norm)
            if centroid is None:
                continue
            if haversine_km(o_lat, o_lng, centroid[0], centroid[1]) <= radius:
                zone.add(city_norm)
        return zone

    @staticmethod
    def get_local_leaderboard(
        user_id: int,
        radius_km: int = LOCAL_ZONE_RADIUS_KM,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Classifica della zona del visitatore (per XP totale).

        Ritorna ``{"available": bool, "zone_label": str, "entries": [...],
        "viewer_rank": int|None}``. ``available=False`` se il visitatore non ha
        ``home_city`` impostata.
        """
        User = CommunityLeaderboardService._User()
        from models.gamification.models import UserLevel
        from models.user.role_enum import UserRole

        viewer = db.session.get(User, user_id)
        home_city = getattr(viewer, "home_city", None) if viewer else None
        if not home_city:
            return {
                "available": False,
                "zone_label": None,
                "entries": [],
                "viewer_rank": None,
            }

        zone = CommunityLeaderboardService.cities_in_zone(home_city, radius_km)

        # Giocatori della zona (player/director, non admin, non cancellati).
        players = (
            db.session.query(User)
            .filter(
                User.role.in_([UserRole.PLAYER.value, UserRole.DIRECTOR.value]),
                db.func.lower(db.func.trim(User.home_city)).in_(zone),
            )
            .all()
        )

        # Mappa user_id → total_xp (0 se nessun UserLevel).
        levels = {
            lvl.user_id: lvl.total_xp
            for lvl in UserLevel.query.filter(
                UserLevel.user_id.in_([p.id for p in players] or [0])
            ).all()
        }

        ranked = sorted(
            players, key=lambda p: (levels.get(p.id, 0), -p.id), reverse=True
        )

        entries = []
        viewer_rank = None
        for idx, p in enumerate(ranked, start=1):
            if p.id == user_id:
                viewer_rank = idx
            if idx <= limit:
                entries.append(
                    {
                        "rank": idx,
                        "user": p,
                        "score": levels.get(p.id, 0),
                        "is_viewer": p.id == user_id,
                    }
                )

        return {
            "available": True,
            "zone_label": home_city.strip(),
            "entries": entries,
            "viewer_rank": viewer_rank,
        }

    # ── Contributo (community-wide) ──────────────────────────────────────────

    @staticmethod
    def compute_contribution(user_id: int) -> Dict[str, int]:
        """Scompone il contributo pro-sociale di un utente (ADR-037).

        Il ``total`` è la somma **pesata** dei componenti secondo
        :data:`CONTRIBUTION_WEIGHTS` (pesi documentati e tarabili).
        """
        drills = CommunityLeaderboardService._drills_engaged(user_id)
        gare = CommunityLeaderboardService._gare_organized(user_id)
        proposals = CommunityLeaderboardService._proposals_accepted(user_id)
        total = (
            drills * CONTRIBUTION_WEIGHTS["drills_engaged"]
            + gare * CONTRIBUTION_WEIGHTS["gare_organized"]
            + proposals * CONTRIBUTION_WEIGHTS["proposals_accepted"]
        )
        return {
            "drills_engaged": drills,
            "gare_organized": gare,
            "proposals_accepted": proposals,
            "total": total,
        }

    @staticmethod
    def get_contribution_leaderboard(limit: int = 50) -> List[Dict[str, Any]]:
        """Top contributori community-wide (contributo > 0), ordinati."""
        User = CommunityLeaderboardService._User()

        candidate_ids = CommunityLeaderboardService._contribution_candidate_ids()
        rows = []
        for uid in candidate_ids:
            breakdown = CommunityLeaderboardService.compute_contribution(uid)
            if breakdown["total"] <= 0:
                continue
            user = db.session.get(User, uid)
            if not user or user.is_deleted:
                continue
            rows.append(
                {"user": user, "score": breakdown["total"], "breakdown": breakdown}
            )

        rows.sort(key=lambda r: (r["score"], -r["user"].id), reverse=True)
        for idx, r in enumerate(rows[:limit], start=1):
            r["rank"] = idx
        return rows[:limit]

    # ── helper metriche ──────────────────────────────────────────────────────

    @staticmethod
    def _drills_engaged(user_id: int) -> int:
        """Tentativi completati da ALTRI su drill di cui l'utente è autore."""
        from models.challenge.models import Challenge, ChallengeAttempt

        return (
            db.session.query(db.func.count(ChallengeAttempt.id))
            .join(Challenge, ChallengeAttempt.challenge_id == Challenge.id)
            .filter(
                Challenge.created_by_id == user_id,
                ChallengeAttempt.user_id != user_id,
                ChallengeAttempt.completed.is_(True),
            )
            .scalar()
        ) or 0

    @staticmethod
    def _gare_organized(user_id: int) -> int:
        """Gare di cui l'utente è responsabile: standalone (``Gara.director_id``)
        + assegnazioni di gara (``DirectorAssignment`` entity_type='gara',
        ADR-037 open item 4). Conteggio per gara distinta."""
        from models.competition.models import Gara
        from models.user.models import DirectorAssignment

        gara_ids = {
            gid
            for (gid,) in db.session.query(Gara.id)
            .filter(Gara.director_id == user_id)
            .all()
        }
        gara_ids.update(
            eid
            for (eid,) in db.session.query(DirectorAssignment.entity_id)
            .filter(
                DirectorAssignment.user_id == user_id,
                DirectorAssignment.entity_type == "gara",
            )
            .all()
        )
        return len(gara_ids)

    @staticmethod
    def _proposals_accepted(user_id: int) -> int:
        """Proposte APERTE create dall'utente e accettate."""
        from models.individual_match.models import (
            MatchProposal,
            ProposalType,
            ProposalStatus,
        )

        return MatchProposal.query.filter_by(
            proposer_id=user_id,
            proposal_type=ProposalType.OPEN,
            status=ProposalStatus.ACCEPTED,
        ).count()

    @staticmethod
    def _contribution_candidate_ids() -> set:
        """Id utente con potenziale contributo (unione delle tre fonti)."""
        from models.challenge.models import Challenge, ChallengeAttempt
        from models.competition.models import Gara
        from models.individual_match.models import (
            MatchProposal,
            ProposalType,
            ProposalStatus,
        )

        ids: set = set()

        # autori di drill che hanno ricevuto almeno un tentativo completato
        author_rows = (
            db.session.query(db.func.distinct(Challenge.created_by_id))
            .join(ChallengeAttempt, ChallengeAttempt.challenge_id == Challenge.id)
            .filter(
                Challenge.created_by_id.isnot(None),
                ChallengeAttempt.completed.is_(True),
            )
            .all()
        )
        ids.update(r[0] for r in author_rows if r[0])

        director_rows = (
            db.session.query(db.func.distinct(Gara.director_id))
            .filter(Gara.director_id.isnot(None))
            .all()
        )
        ids.update(r[0] for r in director_rows if r[0])

        from models.user.models import DirectorAssignment

        assignment_rows = (
            db.session.query(db.func.distinct(DirectorAssignment.user_id))
            .filter(DirectorAssignment.entity_type == "gara")
            .all()
        )
        ids.update(r[0] for r in assignment_rows if r[0])

        proposer_rows = (
            db.session.query(db.func.distinct(MatchProposal.proposer_id))
            .filter(
                MatchProposal.proposal_type == ProposalType.OPEN,
                MatchProposal.status == ProposalStatus.ACCEPTED,
            )
            .all()
        )
        ids.update(r[0] for r in proposer_rows if r[0])

        return ids

    @staticmethod
    def _User():
        """Import lazy del modello User (evita cicli)."""
        from models.user.models import User

        return User
