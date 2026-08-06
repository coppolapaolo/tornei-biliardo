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
from models.caching.manager import cached
from utils.geo import haversine_km, clamp_radius

# Raggio default di espansione alle città vicine (taratura = ADR-037 open item).
LOCAL_ZONE_RADIUS_KM = 30

# TTL della cache delle classifiche (calcolo on-demand → materializzazione
# leggera, ADR-037). Freschezza ≤ TTL; invalidazione solo a tempo.
LEADERBOARD_CACHE_TTL = 300

# Soglie oltre le quali valutare la materializzazione vera (ADR-037 open item):
# esposte nelle KPI admin per capire SE/QUANDO servirà.
PERF_CONTRIBUTORS_THRESHOLD = 200
PERF_COMPUTE_MS_THRESHOLD = 500

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
    @cached(ttl_seconds=LEADERBOARD_CACHE_TTL, tags=["leaderboard"])
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
    def _compute_contribution_ranking(limit: int = 50) -> List[Dict[str, Any]]:
        """Calcolo (NON cache-ato) del ranking contributo come **dati grezzi**.

        Ritorna ``[{"user_id", "score", "breakdown", "rank"}]`` — niente oggetti
        ORM, così è sicuro da mettere in cache tra richieste. Usato anche dalla
        misura di performance (KPI admin).

        Usa :meth:`_contribution_components` (≈4 query aggregate in tutto) invece
        di ``compute_contribution`` per-utente: il costo è indipendente dal
        numero di contributori (era ``O(contributori × 4 query)``, ADR-037).
        """
        components = CommunityLeaderboardService._contribution_components()
        rows = []
        for uid, c in components.items():
            if not uid:
                continue
            total = (
                c["drills_engaged"] * CONTRIBUTION_WEIGHTS["drills_engaged"]
                + c["gare_organized"] * CONTRIBUTION_WEIGHTS["gare_organized"]
                + c["proposals_accepted"] * CONTRIBUTION_WEIGHTS["proposals_accepted"]
            )
            if total <= 0:
                continue
            breakdown = dict(c)
            breakdown["total"] = total
            rows.append({"user_id": uid, "score": total, "breakdown": breakdown})
        rows.sort(key=lambda r: (r["score"], -r["user_id"]), reverse=True)
        rows = rows[:limit]
        for idx, r in enumerate(rows, start=1):
            r["rank"] = idx
        return rows

    @staticmethod
    @cached(ttl_seconds=LEADERBOARD_CACHE_TTL, tags=["leaderboard"])
    def _contribution_ranking(limit: int = 50) -> List[Dict[str, Any]]:
        """Wrapper cache-ato (dati grezzi) di :meth:`_compute_contribution_ranking`."""
        return CommunityLeaderboardService._compute_contribution_ranking(limit)

    @staticmethod
    def get_contribution_leaderboard(limit: int = 50) -> List[Dict[str, Any]]:
        """Top contributori community-wide (contributo > 0), ordinati.

        Legge il ranking (dati grezzi) dalla cache TTL e **idrata** gli oggetti
        ``User`` per-richiesta (gli oggetti ORM non vanno mai messi in cache).
        """
        User = CommunityLeaderboardService._User()
        ranking = CommunityLeaderboardService._contribution_ranking(limit)
        if not ranking:
            return []

        users = {
            u.id: u
            for u in User.query.filter(
                User.id.in_([r["user_id"] for r in ranking])
            ).all()
        }
        out = []
        for r in ranking:
            user = users.get(r["user_id"])
            if not user or user.is_deleted:
                continue  # utente sparito/cancellato dopo il calcolo in cache
            out.append(
                {
                    "rank": r["rank"],
                    "user": user,
                    "score": r["score"],
                    "breakdown": r["breakdown"],
                }
            )
        return out

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
    def _contribution_components() -> Dict[int, Dict[str, int]]:
        """Calcola in **batch** i 3 componenti del contributo per tutti gli utenti.

        Ritorna ``{user_id: {"drills_engaged", "gare_organized",
        "proposals_accepted"}}`` con ~4 query aggregate **in tutto** (indipendenti
        dal numero di contributori). È la fonte unica usata sia dal ranking sia
        dalle KPI di performance, così le definizioni non divergono (ADR-037).
        Semantica identica ai helper per-utente ``_drills_engaged`` /
        ``_gare_organized`` / ``_proposals_accepted`` (usati per il singolo).
        """
        from collections import defaultdict
        from models.challenge.models import Challenge, ChallengeAttempt
        from models.competition.models import Gara
        from models.user.models import DirectorAssignment
        from models.individual_match.models import (
            MatchProposal,
            ProposalType,
            ProposalStatus,
        )

        comp: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {
                "drills_engaged": 0,
                "gare_organized": 0,
                "proposals_accepted": 0,
            }
        )

        # Drill: tentativi completati da ALTRI sui drill di cui l'utente è autore.
        drill_rows = (
            db.session.query(
                Challenge.created_by_id, db.func.count(ChallengeAttempt.id)
            )
            .join(ChallengeAttempt, ChallengeAttempt.challenge_id == Challenge.id)
            .filter(
                Challenge.created_by_id.isnot(None),
                ChallengeAttempt.user_id != Challenge.created_by_id,
                ChallengeAttempt.completed.is_(True),
            )
            .group_by(Challenge.created_by_id)
            .all()
        )
        for uid, cnt in drill_rows:
            comp[uid]["drills_engaged"] = cnt or 0

        # Gare: gara distinte per utente da Gara.director_id + DirectorAssignment.
        gare_pairs: Dict[int, set] = defaultdict(set)
        for uid, gid in (
            db.session.query(Gara.director_id, Gara.id)
            .filter(Gara.director_id.isnot(None))
            .all()
        ):
            gare_pairs[uid].add(gid)
        for uid, gid in (
            db.session.query(DirectorAssignment.user_id, DirectorAssignment.entity_id)
            .filter(DirectorAssignment.entity_type == "gara")
            .all()
        ):
            gare_pairs[uid].add(gid)
        for uid, gids in gare_pairs.items():
            comp[uid]["gare_organized"] = len(gids)

        # Proposte aperte accettate per proponente.
        prop_rows = (
            db.session.query(MatchProposal.proposer_id, db.func.count(MatchProposal.id))
            .filter(
                MatchProposal.proposal_type == ProposalType.OPEN,
                MatchProposal.status == ProposalStatus.ACCEPTED,
            )
            .group_by(MatchProposal.proposer_id)
            .all()
        )
        for uid, cnt in prop_rows:
            comp[uid]["proposals_accepted"] = cnt or 0

        return dict(comp)

    # ── Performance / osservabilità (ADR-037) ───────────────────────────────

    @staticmethod
    def performance_stats() -> Dict[str, Any]:
        """Metriche di costo del calcolo on-demand delle classifiche.

        Esposte nelle KPI admin per decidere SE/QUANDO serve la materializzazione
        (ADR-037 open item): il board contributo è ``O(contributori × 3 query)``.
        Misura il tempo del calcolo **non cache-ato** per dare il costo reale.
        """
        import time

        User = CommunityLeaderboardService._User()

        contributors = len(CommunityLeaderboardService._contribution_components())
        distinct_cities = (
            db.session.query(
                db.func.count(
                    db.func.distinct(db.func.lower(db.func.trim(User.home_city)))
                )
            )
            .filter(User.home_city.isnot(None))
            .scalar()
        ) or 0
        total_users = User.query.filter_by(is_deleted=False).count()

        start = time.perf_counter()
        CommunityLeaderboardService._compute_contribution_ranking()
        compute_ms = round((time.perf_counter() - start) * 1000, 1)

        reasons = []
        if contributors > PERF_CONTRIBUTORS_THRESHOLD:
            reasons.append(
                f"contributori ({contributors}) oltre la soglia "
                f"({PERF_CONTRIBUTORS_THRESHOLD})"
            )
        if compute_ms > PERF_COMPUTE_MS_THRESHOLD:
            reasons.append(
                f"calcolo ({compute_ms} ms) oltre la soglia "
                f"({PERF_COMPUTE_MS_THRESHOLD} ms)"
            )

        return {
            "contributors": contributors,
            "distinct_cities": distinct_cities,
            "total_users": total_users,
            "contribution_compute_ms": compute_ms,
            "cache_ttl_seconds": LEADERBOARD_CACHE_TTL,
            "recommend_materialization": bool(reasons),
            "reasons": reasons,
            "thresholds": {
                "contributors": PERF_CONTRIBUTORS_THRESHOLD,
                "compute_ms": PERF_COMPUTE_MS_THRESHOLD,
            },
        }

    @staticmethod
    def _User():
        """Import lazy del modello User (evita cicli)."""
        from models.user.models import User

        return User
