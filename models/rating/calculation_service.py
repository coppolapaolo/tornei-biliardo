"""
Rating Calculation Service

Handles the mathematical logic for updating Elo ratings based on match results.
Supports both standard 1v1 matches and Trio matches (treated as multi-way comparison).
"""

import math
from typing import Optional
from models.rating.models import RatingSystem, PlayerRating, MatchRatingHistory
from models.match.models import Match, TrioMatch
from models.base import db
import logging

logger = logging.getLogger(__name__)

ELO_K_FACTOR = 32


class RatingCalculationService:
    """Service for calculating rating updates."""

    @staticmethod
    def calculate_expected_score(user_rating: int, opponent_rating: int) -> float:
        """
        Calculate expected score based on Elo formula.
        E = 1 / (1 + 10 ^ ((R_opp - R_user) / 400))
        """
        return 1.0 / (1.0 + math.pow(10, (opponent_rating - user_rating) / 400.0))

    @staticmethod
    def calculate_new_rating(
        current_rating: int,
        expected_score: float,
        actual_score: float,
        k_factor: int = ELO_K_FACTOR,
    ) -> int:
        """
        Calculate new rating based on standard Elo formula.
        R_new = R_old + K * (S - E)
        """
        delta = k_factor * (actual_score - expected_score)
        return int(round(current_rating + delta))

    @staticmethod
    def process_match_result(match: Match, systems=None) -> None:
        """
        Process the result of a completed (tournament) match and update ratings.

        Dual pool: di default aggiorna SIA ELO (competitivo) SIA ELO_GLOBAL
        (tornei + casual). I match di torneo contano in entrambi i pool; il
        pool globale è solo-display e NON tocca categoria/handicap/User.elo_rating.

        Idempotente PER POOL: se esiste già history per (match, sistema) quel
        pool è un no-op. Protegge da MatchCompletedEvent ri-emessi
        (reset→ricompletamento) e da recalc su match già processati.

        `systems` permette ai recalc di limitarsi a un singolo pool (il recalc
        globale, path-dependent, fonde con i casual e gira separato).

        NB: il caller (RatingEventHandlers / recalc) è responsabile di NON
        chiamare questo metodo per i match con handicap (effective_has_handicap)
        e per i walkover — qui non rileggiamo quei flag per non duplicare la
        policy, ma l'idempotenza resta una rete di sicurezza.
        """
        if systems is None:
            systems = [RatingSystem.ELO, RatingSystem.ELO_GLOBAL]

        for system in systems:
            if MatchRatingHistory.exists_for_match(match.id, system):
                logger.info(
                    f"Match {match.id} già processato per {system.value}, skip "
                    f"(idempotenza)."
                )
                continue

            if match.is_trio and match.trio_match:
                RatingCalculationService._process_trio_match(
                    match.trio_match, match.id, system
                )
            else:
                RatingCalculationService._process_standard_match(match, system)

    @staticmethod
    def process_individual_match_result(individual_match) -> None:
        """Aggiorna SOLO il pool ELO_GLOBAL per un match individuale VALIDATO.

        I casual non toccano l'ELO competitivo (riservato ai tornei arbitrati).
        Idempotente per (individual_match, ELO_GLOBAL): protegge da eventi
        ri-emessi (es. reject→re-conferma) e dal recalc globale.
        """
        system = RatingSystem.ELO_GLOBAL
        if MatchRatingHistory.exists_for_individual_match(individual_match.id, system):
            logger.info(
                f"Casual {individual_match.id} già processato per "
                f"{system.value}, skip (idempotenza)."
            )
            return

        RatingCalculationService._process_two_player(
            individual_match.player1_id,
            individual_match.player2_id,
            individual_match.winner_id,
            system,
            individual_match_id=individual_match.id,
        )

    @staticmethod
    def recalculate_all_elo() -> dict:
        """Reset and replay ALL ELO ratings from finished matches.

        Pure/in-transaction: no app context, no commit, no I/O. The caller is
        responsible for the transaction boundary (``@transactional``) and for
        committing/rolling back.

        Resets ``User.elo_rating`` (→ None), deletes ELO ``PlayerRating`` and
        ``MatchRatingHistory`` rows, then replays every finished match
        (``completed`` + ``validated``) in chronological order, skipping
        walkover and handicap matches (coherent with the rating event policy).

        Returns:
            dict: counters ``{processed, skipped, total}``.
        """
        from models.user.models import User
        from models.status_enum import MatchStatus

        # 1. Reset User.elo_rating (None = "not yet rated").
        for user in User.query.all():
            user.elo_rating = None
            db.session.add(user)

        # 2. Drop ELO PlayerRating + history so the replay starts from default.
        db.session.query(PlayerRating).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.query(MatchRatingHistory).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.flush()

        # 3. Replay finished matches chronologically.
        matches = (
            Match.query.filter(Match.status.in_(MatchStatus.finished_values()))
            .order_by(Match.ended_at.asc(), Match.id.asc())
            .all()
        )
        processed = 0
        skipped = 0
        for match in matches:
            if match.is_walkover or match.effective_has_handicap:
                skipped += 1
                continue
            # Solo pool competitivo: il pool globale è path-dependent e va
            # ricalcolato fondendo i casual (recalculate_all_elo_global).
            RatingCalculationService.process_match_result(
                match, systems=[RatingSystem.ELO]
            )
            processed += 1

        return {"processed": processed, "skipped": skipped, "total": len(matches)}

    @staticmethod
    def recalculate_all_elo_global() -> dict:
        """Reset e replay del pool ELO_GLOBAL (tornei + casual VALIDATED).

        ELO è path-dependent: i match di torneo e i casual vanno fusi in UN
        unico ordine cronologico (``ended_at``, poi ``id``). Resetta SOLO il
        pool ELO_GLOBAL: NON tocca ``User.elo_rating`` né il pool competitivo.

        Pure/in-transaction come ``recalculate_all_elo``: il caller gestisce la
        transazione.

        Returns:
            dict: counters ``{processed, skipped, total}``.
        """
        from models.status_enum import MatchStatus
        from models.individual_match.models import IndividualMatch

        # 1. Drop SOLO il pool globale (PlayerRating + history).
        db.session.query(PlayerRating).filter_by(
            rating_system=RatingSystem.ELO_GLOBAL
        ).delete()
        db.session.query(MatchRatingHistory).filter_by(
            rating_system=RatingSystem.ELO_GLOBAL
        ).delete()
        db.session.flush()

        # 2. Carica torneo (finished) + casual (VALIDATED), entrambi con un
        #    marcatore di sorgente, e fondili per ordine cronologico.
        tournament = [
            ("match", m)
            for m in Match.query.filter(
                Match.status.in_(MatchStatus.finished_values())
            ).all()
        ]
        casual = [
            ("individual", im)
            for im in IndividualMatch.query.filter(
                IndividualMatch.status == MatchStatus.CONFIRMED_BY_BOTH
            ).all()
        ]

        def _sort_key(item):
            _kind, obj = item
            # ended_at può essere None su dati vecchi: spingili in coda con un
            # sentinel alto ma deterministico, poi ordina per id.
            return (obj.ended_at is None, obj.ended_at, obj.id)

        merged = sorted(tournament + casual, key=_sort_key)

        processed = 0
        skipped = 0
        for kind, obj in merged:
            if kind == "match":
                if obj.is_walkover or obj.effective_has_handicap:
                    skipped += 1
                    continue
                RatingCalculationService.process_match_result(
                    obj, systems=[RatingSystem.ELO_GLOBAL]
                )
            else:  # individual (casual) — forfait già esclusi (solo VALIDATED)
                RatingCalculationService.process_individual_match_result(obj)
            processed += 1

        return {"processed": processed, "skipped": skipped, "total": len(merged)}

    @staticmethod
    def revert_match_result(match: Match) -> None:
        """Annulla i delta di rating applicati per questo match.

        Per ogni record di history: sottrae il delta dal rating corrente e
        decrementa games_played, poi elimina il record. Usato quando un match
        completato viene riaperto/resettato o prima di eliminarlo.

        Path-dependency: sottrarre il delta (anziché ripristinare il valore
        assoluto) è esatto se il match è l'ultimo processato per quei giocatori
        — il caso tipico di un reset. Per un match "in mezzo" i rating restano
        approssimati finché non si rilancia recalc_elo.
        """
        from models.user.models import User

        records = MatchRatingHistory.query.filter_by(match_id=match.id).all()
        if not records:
            return

        for rec in records:
            rating_obj = PlayerRating.get_user_rating(rec.user_id, rec.rating_system)
            if rating_obj:
                rating_obj.rating_value = rating_obj.rating_value - rec.delta
                rating_obj.games_played = max(
                    0, rating_obj.games_played - rec.games_increment
                )
                db.session.add(rating_obj)
                if rec.rating_system == RatingSystem.ELO:
                    user = db.session.get(User, rec.user_id)
                    if user:
                        user.elo_rating = rating_obj.rating_value
                        db.session.add(user)
            db.session.delete(rec)

        logger.info(
            f"Revert rating per match {match.id}: annullati {len(records)} delta."
        )

    @staticmethod
    def _process_standard_match(
        match: Match, rating_system: RatingSystem = RatingSystem.ELO
    ) -> None:
        """Handle standard 1v1 (tournament) match per il pool indicato."""
        RatingCalculationService._process_two_player(
            match.player1_id,
            match.player2_id,
            match.winner_id,
            rating_system,
            match_id=match.id,
        )

    @staticmethod
    def _process_two_player(
        player1_id: Optional[int],
        player2_id: Optional[int],
        winner_id: Optional[int],
        rating_system: RatingSystem,
        match_id: Optional[int] = None,
        individual_match_id: Optional[int] = None,
    ) -> None:
        """Core Elo 1v1, pool-agnostico e sorgente-agnostico (torneo o casual)."""
        source = match_id if match_id is not None else individual_match_id
        if not player1_id or not player2_id:
            logger.warning(
                f"Match {source} missing players, skipping rating update "
                f"({rating_system.value})."
            )
            return

        # Get current ratings (default to 1200 if not set)
        p1_rating_obj = PlayerRating.get_user_rating(player1_id, rating_system)
        p2_rating_obj = PlayerRating.get_user_rating(player2_id, rating_system)

        r1 = p1_rating_obj.rating_value if p1_rating_obj else 1200
        r2 = p2_rating_obj.rating_value if p2_rating_obj else 1200

        # Determine actual scores
        # 1 = Win, 0 = Loss, 0.5 = Draw (if winner_id is None)
        if winner_id == player1_id:
            s1 = 1.0
            s2 = 0.0
        elif winner_id == player2_id:
            s1 = 0.0
            s2 = 1.0
        else:
            s1 = 0.5
            s2 = 0.5

        # Calculate Expected Scores
        e1 = RatingCalculationService.calculate_expected_score(r1, r2)
        e2 = RatingCalculationService.calculate_expected_score(r2, r1)

        # Calculate new ratings
        new_r1 = RatingCalculationService.calculate_new_rating(r1, e1, s1)
        new_r2 = RatingCalculationService.calculate_new_rating(r2, e2, s2)

        # Update Database (+ history per idempotenza/revert)
        RatingCalculationService._update_player_rating_db(
            player1_id,
            r1,
            new_r1,
            p1_rating_obj,
            rating_system,
            match_id,
            individual_match_id,
        )
        RatingCalculationService._update_player_rating_db(
            player2_id,
            r2,
            new_r2,
            p2_rating_obj,
            rating_system,
            match_id,
            individual_match_id,
        )

        logger.info(
            f"Updated {rating_system.value} for match {source}: "
            f"P1 {r1}->{new_r1}, P2 {r2}->{new_r2}"
        )

    @staticmethod
    def _process_trio_match(
        trio: TrioMatch,
        match_id: int,
        rating_system: RatingSystem = RatingSystem.ELO,
    ) -> None:
        """
        Handle Trio match.
        Logic:
        - S=1 if strictly greater than both opponents
        - S=0.5 if tied for best score
        - S=0 otherwise
        - E calculated against average of opponents
        """
        scores = {
            trio.player1_id: trio.player1_racks,
            trio.player2_id: trio.player2_racks,
            trio.player3_id: trio.player3_racks,
        }

        player_ids = [trio.player1_id, trio.player2_id, trio.player3_id]

        # Load ratings
        ratings = {}
        rating_objs = {}
        for pid in player_ids:
            obj = PlayerRating.get_user_rating(pid, rating_system)
            rating_objs[pid] = obj
            ratings[pid] = obj.rating_value if obj else 1200

        # Calculate Delta for each player independently
        updates = {}
        for pid in player_ids:
            my_score = scores[pid]
            others = [p for p in player_ids if p != pid]
            other_scores = [scores[o] for o in others]
            other_ratings = [ratings[o] for o in others]

            # Determine Actual Score S
            # Win (1.0): Strictly greater than ALL others
            if all(my_score > os for os in other_scores):
                actual_s = 1.0
            # Draw (0.5): >= ALL others, but EQUAL to at least one (tied 1st)
            elif all(my_score >= os for os in other_scores) and any(
                my_score == os for os in other_scores
            ):
                actual_s = 0.5
            # Loss (0.0): Less than someone
            else:
                actual_s = 0.0

            # Determine Expected Score E
            # Vs Average rating of opponents
            avg_opp_rating = sum(other_ratings) / len(other_ratings)
            expected_e = RatingCalculationService.calculate_expected_score(
                ratings[pid], avg_opp_rating
            )

            # Calculate New Rating
            new_rating = RatingCalculationService.calculate_new_rating(
                ratings[pid], expected_e, actual_s
            )
            updates[pid] = new_rating

            logger.info(
                f"Trio {trio.id} Player {pid}: Score={my_score} vs "
                f"{other_scores}, S={actual_s}, E={expected_e:.3f}, "
                f"R={ratings[pid]}->{new_rating}"
            )

        # Apply updates (+ history per idempotenza/revert)
        for pid, new_r in updates.items():
            RatingCalculationService._update_player_rating_db(
                pid, ratings[pid], new_r, rating_objs.get(pid), rating_system, match_id
            )

    @staticmethod
    def _update_player_rating_db(
        user_id: int,
        old_val: int,
        new_val: int,
        exist_obj: Optional[PlayerRating],
        rating_system: RatingSystem,
        match_id: Optional[int] = None,
        individual_match_id: Optional[int] = None,
    ) -> None:
        """Salva il rating, registra la history e (solo ELO competitivo) sincronizza
        User.elo_rating.

        Vincolo display-only: per ELO_GLOBAL NON si scrive `User.elo_rating`, che
        resta la fonte autorevole del solo pool competitivo (categoria/handicap).
        """
        # Update/Create PlayerRating per il pool indicato
        if exist_obj:
            exist_obj.update_rating(new_val)
        else:
            new_rating = PlayerRating(
                user_id=user_id,
                rating_system=rating_system,
                rating_value=new_val,
                games_played=1,
            )
            db.session.add(new_rating)

        # Record history per idempotenza + revert (sorgente polimorfa)
        db.session.add(
            MatchRatingHistory(
                match_id=match_id,
                individual_match_id=individual_match_id,
                user_id=user_id,
                rating_system=rating_system,
                old_rating=old_val,
                new_rating=new_val,
                delta=new_val - old_val,
                games_increment=1,
            )
        )

        # Sync su User SOLO per l'ELO competitivo (display-only per ELO_GLOBAL)
        if rating_system == RatingSystem.ELO:
            from models.user.models import User

            user = db.session.get(User, user_id)
            if user:
                user.elo_rating = new_val
                db.session.add(user)
