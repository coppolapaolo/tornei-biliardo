# models/campionato/homepage_service.py
"""Service for aggregating homepage data.

Extracts business logic previously inline in routes/main.py:index().

The public homepage is organised by "actionability" so a guest is drawn in
both as a spectator and towards registering. Sections, top to bottom:

  1. live           — gare in esecuzione adesso (playing/awaiting_ssr),
                       con i match attualmente ai tavoli.
  2. open           — gare con iscrizioni aperte (can_inscribe()), con
                       posti rimasti e scadenza ben visibili.
  3. active_campionati — campionati in corso (registrazioni/in gioco) con
                       la testa della classifica generale.
  4. upcoming       — gare/campionati in preparazione (setup, data futura).
  5. archive        — campionati e gare concluse (coda recente).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_

from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus, TournamentStatus
from models.campionato.services import TournamentService

# How many concluded campionati/gare to surface in the archive tail.
# Older ones live behind the "Vedi tutti" links to /campionatos and /garas.
HOMEPAGE_ARCHIVE_LIMIT = 4

# How many live matches (al tavolo) to show inside a single live gara card.
HOMEPAGE_LIVE_MATCHES_PER_GARA = 6

_LIVE_GARA_STATUSES = (GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value)
_TERMINAL_CAMPIONATO_STATUSES = frozenset(
    {TournamentStatus.COMPLETED.value, TournamentStatus.TERMINATED.value}
)


class HomepageService:
    """Aggregates data for the public homepage."""

    @staticmethod
    def get_homepage_data() -> Optional[Dict[str, Any]]:
        """Return all data needed to render the homepage, partitioned by
        actionability.

        Returns:
            Dict with keys:
              - live_garas: gare playing/awaiting_ssr (+ match ai tavoli)
              - open_garas: gare con iscrizioni aperte (+ posti/scadenza)
              - active_campionati: campionati in corso (+ top classifica)
              - upcoming_garas / upcoming_campionati: in preparazione
              - archive_campionati / archive_garas: concluse (coda recente)
              - *_total counters used to show "Vedi tutti" links.
            None if there is nothing public to show.
        """
        garas = HomepageService._public_garas()
        # Eager-load playoff config + tournament: get_status() (per ogni
        # campionato terminated) li consulta via relationship, altrimenti N+1.
        from sqlalchemy.orm import joinedload
        from models.playoff.models import PlayoffConfiguration

        campionati = (
            Campionato.query.filter_by(is_deleted=False)
            .options(
                joinedload(Campionato.playoff_configurations).joinedload(
                    PlayoffConfiguration.playoff_campionato
                )
            )
            .order_by(Campionato.created_at.desc())
            .all()
        )

        # --- Gare partitioning -------------------------------------------------
        live_gara_objs = [g for g in garas if g.status in _LIVE_GARA_STATUSES]
        # `display_round` scorre `gara.matches` (relationship lazy): senza
        # eager-load sarebbe una query per gara live. Popolata qui in un'unica
        # selectin sulle sole gare live — le altre card non leggono il turno.
        HomepageService._preload_matches(live_gara_objs)
        # Match ai tavoli per TUTTE le gare live in un'unica query (evita N+1).
        matches_by_gara = HomepageService._live_matches_by_gara(
            [g.id for g in live_gara_objs]
        )
        live_garas = [
            HomepageService._build_live_gara(g, matches_by_gara.get(g.id, []))
            for g in live_gara_objs
        ]
        open_garas = [
            HomepageService._build_open_gara(g) for g in garas if g.can_inscribe()
        ]

        # Gara concluse = COMPLETED (coda recente per archivio).
        completed_garas = [g for g in garas if g.status == GaraStatus.COMPLETED.value]
        completed_garas.sort(key=lambda g: (g.date or date.min), reverse=True)
        archive_garas = completed_garas[:HOMEPAGE_ARCHIVE_LIMIT]

        # In arrivo = gare visibili non live, non aperte, non concluse
        # (tipicamente SETUP con data futura, o INSCRIPTION fuori finestra).
        actionable_ids = {c["gara"].id for c in live_garas} | {
            c["gara"].id for c in open_garas
        }
        upcoming_garas = [
            g
            for g in garas
            if g.status != GaraStatus.COMPLETED.value and g.id not in actionable_ids
        ]
        upcoming_garas.sort(key=lambda g: (g.date or date.max))

        # --- Campionati partitioning ------------------------------------------
        active_campionati: List[Dict[str, Any]] = []
        upcoming_campionati: List[Campionato] = []
        archive_campionati: List[Campionato] = []
        for c in campionati:
            status = c.get_status()
            if status in _TERMINAL_CAMPIONATO_STATUSES:
                archive_campionati.append(c)
            elif status == TournamentStatus.SETUP.value:
                upcoming_campionati.append(c)
            else:  # IN_PROGRESS / REGISTRATION_OPEN
                active_campionati.append(HomepageService._build_tournament_data(c))

        archive_campionati_total = len(archive_campionati)

        has_content = any(
            [
                live_garas,
                open_garas,
                active_campionati,
                upcoming_garas,
                upcoming_campionati,
                archive_garas,
                archive_campionati,
            ]
        )
        if not has_content:
            return None

        return {
            "live_garas": live_garas,
            "open_garas": open_garas,
            "active_campionati": active_campionati,
            "active_campionati_count": len(active_campionati),
            "upcoming_garas": upcoming_garas,
            "upcoming_campionati": upcoming_campionati,
            "archive_garas": archive_garas,
            "archive_campionati": archive_campionati[:HOMEPAGE_ARCHIVE_LIMIT],
            "archive_campionati_total": archive_campionati_total,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Query helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _public_garas() -> List[Gara]:
        """Tutte le gare visibili al pubblico (standalone o di campionati non
        soft-deleted), escluse le SETUP "zombie" con data passata.

        Le gare in SETUP sono visibili SOLO se la data è futura (o NULL); le
        SETUP con data passata sono gare dimenticate, visibili solo al
        director/admin proprietario (vedi ADR-030).
        """
        today = date.today()
        return (
            Gara.query.outerjoin(Campionato, Gara.campionato_id == Campionato.id)
            .filter(or_(Gara.campionato_id.is_(None), Campionato.is_deleted.is_(False)))
            .filter(
                or_(
                    Gara.status != GaraStatus.SETUP.value,
                    and_(
                        Gara.status == GaraStatus.SETUP.value,
                        or_(Gara.date.is_(None), Gara.date >= today),
                    ),
                )
            )
            .order_by(Gara.date.asc())
            .all()
        )

    # ──────────────────────────────────────────────────────────────────────
    # Card builders
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _preload_matches(garas: List[Gara]) -> None:
        """Popola `Gara.matches` per le gare indicate con un'unica query.

        `selectinload` su istanze già in identity map riempie la collection
        senza toccarne gli altri attributi. Serve a `display_round`, che
        altrimenti farebbe un lazy-load per gara.
        """
        if not garas:
            return
        from sqlalchemy.orm import selectinload

        Gara.query.options(selectinload(Gara.matches)).filter(
            Gara.id.in_([g.id for g in garas])
        ).all()

    @staticmethod
    def _display_round(gara: Gara) -> int:
        """Turno da mostrare, delegato a `Gara.display_round`.

        Prima leggeva `current_round`, che con i turni pre-generati resta
        indietro rispetto al turno effettivamente in gioco (issue #62).

        Il chiamante deve aver già caricato `gara.matches` (vedi
        `_preload_matches`): la property li scorre.
        """
        return gara.display_round

    @staticmethod
    def _live_matches_by_gara(gara_ids: List[int]) -> Dict[int, List[Match]]:
        """Match attualmente ai tavoli per le gare indicate, in un'unica query
        (evita il pattern N+1 quando più gare sono live insieme).

        Raggruppa per gara_id preservando l'ordine (tavolo, id); il taglio a
        HOMEPAGE_LIVE_MATCHES_PER_GARA avviene per-gara in `_build_live_gara`.
        """
        if not gara_ids:
            return {}
        rows = (
            Match.query.filter(Match.gara_id.in_(gara_ids))
            .filter(Match.status == MatchStatus.PLAYING.value)
            .filter(Match.is_bye.is_(False))
            .filter(Match.table_assignment.isnot(None))
            .order_by(Match.gara_id, Match.table_assignment, Match.id)
            .all()
        )
        grouped: Dict[int, List[Match]] = {}
        for m in rows:
            grouped.setdefault(m.gara_id, []).append(m)
        return grouped

    @staticmethod
    def _build_live_gara(gara: Gara, live_matches: List[Match]) -> Dict[str, Any]:
        """Dati per una card di gara in diretta, inclusi i match ai tavoli
        (già pre-caricati e raggruppati da `_live_matches_by_gara`)."""
        return {
            "gara": gara,
            "campionato": gara.campionato if gara.campionato_id else None,
            "current_round": HomepageService._display_round(gara),
            "rounds_count": gara.rounds_count,
            "active_count": gara.get_active_inscriptions_count(),
            "live_matches": [
                HomepageService._build_live_match(m)
                for m in live_matches[:HOMEPAGE_LIVE_MATCHES_PER_GARA]
            ],
        }

    @staticmethod
    def _build_live_match(match: Match) -> Dict[str, Any]:
        """Riepilogo display di un match al tavolo (singolo o trio)."""
        if match.is_trio and match.trio_match is not None:
            trio = match.trio_match
            players = [
                SimpleNamespace(
                    name=(p.username if p else "?"),
                    score=score,
                )
                for p, score in (
                    (trio.player1, trio.player1_racks),
                    (trio.player2, trio.player2_racks),
                    (trio.player3, trio.player3_racks),
                )
            ]
            return {
                "table": match.table_assignment,
                "is_trio": True,
                "players": players,
            }
        return {
            "table": match.table_assignment,
            "is_trio": False,
            "player1": match.player1.username if match.player1 else "?",
            "player2": match.player2.username if match.player2 else "?",
            "player1_score": match.player1_score or 0,
            "player2_score": match.player2_score or 0,
        }

    @staticmethod
    def _build_open_gara(gara: Gara) -> Dict[str, Any]:
        """Dati per una card di gara con iscrizioni aperte: posti e scadenza
        devono essere subito visibili (no click su dettaglio)."""
        active = gara.get_active_inscriptions_count()
        max_p = gara.max_participants
        return {
            "gara": gara,
            "campionato": gara.campionato if gara.campionato_id else None,
            "active_count": active,
            "max_participants": max_p,
            "min_participants": gara.min_participants,
            "spots_remaining": (max_p - active) if max_p else None,
            "is_full": gara.is_full(),
            "inscription_end": gara.inscription_end,
        }

    @staticmethod
    def _build_tournament_data(campionato: Campionato) -> Dict[str, Any]:
        """Build display data for a single campionato (in corso)."""
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
        general_classification = service.calculate_general_classification(campionato.id)

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
            total_racks_won=player_data.get("total_racks_won", 0),
            total_spot_shot_wins=player_data.get("total_spot_shot_wins", 0),
        )
