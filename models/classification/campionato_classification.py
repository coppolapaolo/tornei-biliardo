"""
Module: models/classification/campionato_classification.py
Purpose: Campionato-level classification services with caching and optimization
"""

from dataclasses import replace
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import joinedload, selectinload
from models.base import db
from .models import Classification, GaraClassification
from .position_points import points_for_position, points_table_for_campionato
from .strategies.base import PlayerScore
from ..status_enum import MatchStatus, ClassificationSystem
from ..caching import cached, cache_invalidate, cache_manager
from ..transaction import transactional

from .registry import get_classification_registry
from .score_aggregator import ScoreAggregator

# Tipi di campionato in cui le gare sono a tabellone e la classifica generale
# somma punti per posizione invece di vittorie (US-17).
POSITION_CAMPIONATO_TYPES = frozenset({"direct_elimination", "double_knockout"})


class ClassificationService:
    """Service for managing campionato classifications with caching and optimization."""

    @staticmethod
    def uses_position_points(campionato) -> bool:
        """Se la classifica generale di questo campionato somma punti-posizione.

        Il criterio primario è il **tipo di campionato**, perché è quello che
        determina il formato delle gare. Il sistema di classifica è un secondo
        indizio, utile per i campionati configurati prima che i due formati a
        tabellone fossero selezionabili come tipo.
        """
        if campionato is None:
            return False
        if getattr(campionato, "campionato_type", None) in POSITION_CAMPIONATO_TYPES:
            return True
        return (
            ClassificationSystem.normalize(
                getattr(campionato, "default_classification_system", None)
            )
            == ClassificationSystem.POSITION
        )

    @staticmethod
    def _get_campionato_strategy(campionato):
        """La strategia di classifica generale, scelta dal sistema di classifica.

        I nomi registrati sono storici e citano la strategia di accoppiamento
        ("amalfi", "random") perché è così che la scelta veniva fatta: era
        l'equivoco della issue #89. I criteri che implementano, però, sono
        esattamente i tre sistemi di classifica —

        - `amalfi_campionato`   → vittorie, poi differenza, poi SSR  (WINS)
        - `random_campionato`   → triangoli totali, poi SSR          (RACK)
        - `position_campionato` → punti per piazzamento              (POSITION)

        — quindi qui si mappa il sistema, non il tipo. Rinominarle è un
        riordino a parte: `name` è anche la chiave del registry e compare nei
        metadata dei risultati.
        """
        if ClassificationService.uses_position_points(campionato):
            strategy_name = "position_campionato"
        elif campionato.classification_system == ClassificationSystem.RACK:
            strategy_name = "random_campionato"
        else:
            strategy_name = "amalfi_campionato"
        registry = get_classification_registry()
        return registry.get(strategy_name)

    @staticmethod
    def position_points_by_player(campionato) -> Dict[int, int]:
        """Punti per posizione accumulati da ciascun giocatore nel campionato.

        Si legge dalla classifica **finale di ogni gara**, non dai match: nel
        tabellone il piazzamento è il risultato, e i totali di rack non lo
        ricostruiscono. Tutti i pari merito di una banda ricevono lo stesso
        punteggio, perché la banda è la posizione (i quattro quartifinalisti
        sono tutti 5° e prendono tutti i punti del 5°).
        """
        from models.competition.models import Gara

        table = points_table_for_campionato(campionato)
        # La gara viaggia con la riga per `classification_weight` (ADR-053):
        # il peso moltiplica anche i punti per piazzamento, non solo vittorie
        # e triangoli. `playoff_config` in eager, perché è lei a dire se la
        # gara di playoff vale zero.
        rows = (
            db.session.query(GaraClassification, Gara)
            .join(Gara, GaraClassification.gara_id == Gara.id)
            .filter(Gara.campionato_id == campionato.id)
            .options(joinedload(Gara.playoff_config))
            .all()
        )

        totals: Dict[int, int] = {}
        for row, gara in rows:
            totals[row.user_id] = totals.get(
                row.user_id, 0
            ) + gara.classification_weight * points_for_position(row.position, table)
        return totals

    @staticmethod
    def _with_position_points(
        campionato, scores: List[PlayerScore]
    ) -> List[PlayerScore]:
        """Popola `PlayerScore.points` per i campionati a tabellone."""
        if not ClassificationService.uses_position_points(campionato):
            return list(scores)

        totals = ClassificationService.position_points_by_player(campionato)
        return [
            replace(score, points=totals.get(score.player_id, 0)) for score in scores
        ]

    @staticmethod
    def playoff_final_blocks(campionato) -> List[List[int]]:
        """I blocchi di giocatori il cui ordine lo detta una gara di playoff.

        Un blocco per ogni configurazione playoff che *decide* la classifica
        finale e la cui gara ha già una classifica finale. L'ordine dei blocchi
        segue `positions_from`, così Elite (dal 1°) precede Academy (dal 7°).

        Finché la gara di playoff non è chiusa la lista è vuota, e la
        classifica generale resta quella del campionato: è il comportamento
        giusto, non un caso da gestire a parte.

        È pubblica perché la legge anche la classifica calcolata al volo per
        la pagina del campionato (`calculate_general_classification`): i due
        percorsi devono promuovere gli stessi giocatori nello stesso ordine.
        """
        configurations = getattr(campionato, "playoff_configurations", None) or []
        candidate = [
            cfg
            for cfg in configurations
            if cfg.is_active and cfg.decides_final_ranking and cfg.gara is not None
        ]
        if not candidate:
            return []

        candidate.sort(key=lambda cfg: (cfg.positions_from or 0, cfg.id))

        blocks: List[List[int]] = []
        for cfg in candidate:
            rows = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=cfg.gara.id)
                .order_by(GaraClassification.position, GaraClassification.user_id)
                .all()
            )
            if rows:
                blocks.append([row.user_id for row in rows])
        return blocks

    @staticmethod
    def _apply_playoff_final_order(campionato, result):
        """Riordina la classifica generale quando la decide il playoff.

        Chi ha giocato il playoff occupa le prime posizioni, nell'ordine
        deciso lì; **sotto** vengono tutti gli altri, nell'ordine che avevano
        in campionato. Nessuno sparisce: un campionato di venti giocatori con
        un playoff a sei resta un campionato di venti giocatori.

        I punteggi non si toccano — restano quelli del campionato, e sono
        quelli che si vedono in tabella. A cambiare è solo la posizione, che
        è ciò che quella modalità dichiara di voler cambiare.
        """
        blocks = ClassificationService.playoff_final_blocks(campionato)
        if not blocks:
            return result

        by_player = {entry.player_id: entry for entry in result.entries}
        ordered: List[int] = []
        promoted: set[int] = set()

        for block in blocks:
            for player_id in block:
                # Un qualificato che non ha punteggio di campionato non c'è in
                # `result` (nessuna partita finita): non lo si inventa qui.
                if player_id in by_player and player_id not in promoted:
                    ordered.append(player_id)
                    promoted.add(player_id)

        for entry in result.entries:
            if entry.player_id not in promoted:
                ordered.append(entry.player_id)

        entries = []
        for index, player_id in enumerate(ordered, start=1):
            entry = by_player[player_id]
            if player_id in promoted:
                # Il playoff ha deciso: un pari merito di campionato qui non
                # esiste più, e lasciarlo scritto manderebbe lo spareggio a
                # risolvere una parità che il campo ha già risolto.
                entries.append(
                    replace(
                        entry,
                        position=index,
                        tied_with=(),
                        tiebreaker_resolved=True,
                    )
                )
            else:
                entries.append(replace(entry, position=index))

        return replace(
            result,
            entries=tuple(entries),
            has_ties=any(e.is_tied() for e in entries),
            requires_tiebreaker=any(
                e.is_tied() and not e.tiebreaker_resolved for e in entries
            ),
        )

    @staticmethod
    def _count_gare_played(campionato_id: int) -> Dict[int, int]:
        """Count how many gare each player participated in.

        Returns:
            Dict mapping player_id -> number of gare played
        """
        from models.competition.models import Gara

        # selectinload avoids N+1: one IN-query loads all matches for all gare,
        # instead of one lazy-load per gara when accessing `gara.matches` below.
        gare = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .options(selectinload(Gara.matches))
            .all()
        )
        player_gare: Dict[int, set] = {}

        for gara in gare:
            # Include both 'completed' and 'validated' as finished matches
            completed_matches = [
                m
                for m in gara.matches
                if MatchStatus.is_finished(m.status) and not m.is_bye
            ]
            for match in completed_matches:
                if match.player1_id:
                    player_gare.setdefault(match.player1_id, set()).add(gara.id)
                if match.player2_id:
                    player_gare.setdefault(match.player2_id, set()).add(gara.id)

        return {pid: len(gare_ids) for pid, gare_ids in player_gare.items()}

    @staticmethod
    @transactional(domain="classification")
    @cached(
        ttl_seconds=300,
        tags=["classification", "campionato"],
        key_generator="campionato",
    )
    def update_campionato_classification(campionato_id: int) -> List[Classification]:
        """
        Update overall campionato classification based on all completed gare.
        Results are cached for 5 minutes and invalidated on campionato changes.

        Uses ScoreAggregator for data collection and classification strategies
        for ranking, ensuring consistent use of PlayerScore value objects.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of updated Classification objects
        """
        from models.campionato.models import Campionato

        # Get campionato to determine strategy
        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError(f"Campionato {campionato_id} not found")

        # Use ScoreAggregator to collect PlayerScore objects
        aggregator = ScoreAggregator()
        scores = aggregator.aggregate_campionato_scores(campionato_id)

        if not scores:
            return []

        # Nei campionati a tabellone la classifica generale somma i punti per
        # posizione delle singole gare: i totali di rack e vittorie restano
        # come criterio di elencazione a pari punti.
        scores = ClassificationService._with_position_points(campionato, scores)

        # Get classification strategy based on the campionato classification system
        strategy = ClassificationService._get_campionato_strategy(campionato)

        # Calculate classification using strategy
        result = strategy.calculate(
            scores,
            context={"campionato_id": campionato_id},
        )

        # Quando la classifica finale è quella dei playoff, l'ordine dei
        # partecipanti lo detta la gara di playoff e non il punteggio sommato.
        result = ClassificationService._apply_playoff_final_order(campionato, result)

        # Count gare played per player
        gare_played_map = ClassificationService._count_gare_played(campionato_id)

        # Batch load existing classifications to avoid N+1
        existing_classifications = {
            c.user_id: c
            for c in db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .all()
        }

        # Update or create Classification records from strategy result
        classifications = []
        for entry in result.entries:
            player_id = entry.player_id
            classification = existing_classifications.get(player_id)

            if not classification:
                classification = Classification(
                    campionato_id=campionato_id, user_id=player_id
                )

            classification.position = entry.position
            classification.total_matches_won = entry.score.matches_won
            classification.total_racks_won = entry.score.racks_won
            classification.total_point_difference = entry.score.rack_difference
            classification.gare_played = gare_played_map.get(player_id, 0)
            classification.total_position_points = entry.score.points

            db.session.add(classification)
            classifications.append(classification)

        # Chi non è più in classifica non deve restarci. L'upsert da solo non
        # basta: aggiorna e crea, ma non toglie, e una riga rimasta indietro non
        # è inerte — `start_playoff` qualifica leggendo proprio queste righe, e
        # il profilo giocatore le mostra. Un giocatore esce dall'aggregato
        # quando una gara viene cancellata, quando un'iscrizione viene ritirata,
        # o quando una partecipazione viene spostata su un altro account
        # (ADR-048).
        #
        # Si pota solo avendo un risultato in mano: il `return []` sopra, quando
        # non c'è nessun punteggio, lascia tutto dov'è di proposito — «non so
        # niente» e «non c'è più nessuno» sono due cose diverse.
        rimasti = {entry.player_id for entry in result.entries}
        for user_id, orfana in existing_classifications.items():
            if user_id not in rimasti:
                db.session.delete(orfana)

        # Transaction managed by @transactional decorator
        return classifications

    @staticmethod
    @cached(
        ttl_seconds=600,
        tags=["classification", "campionato"],
        key_generator="campionato",
    )
    def get_campionato_standings(campionato_id: int) -> List[Classification]:
        """
        Get current campionato standings with caching.
        Cached for 10 minutes as standings don't change frequently.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of Classification objects ordered by position
        """
        return (
            db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .options(
                joinedload(getattr(Classification, "user"))
            )  # Eager load user data
            .order_by(Classification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=300, tags=["classification", "user"])
    def get_player_ranking(
        campionato_id: int, user_id: int
    ) -> Optional[Classification]:
        """
        Get a specific player's ranking in a campionato with caching.

        Args:
            campionato_id: ID of the campionato
            user_id: ID of the player

        Returns:
            Classification object or None if not found
        """
        return (
            db.session.query(Classification)
            .options(joinedload(getattr(Classification, "user")))
            .filter_by(campionato_id=campionato_id, user_id=user_id)
            .first()
        )

    @staticmethod
    @cache_invalidate(tags=["classification", "campionato"])
    def invalidate_campionato_cache(campionato_id: int) -> None:
        """Invalidate all classification caches for a campionato."""
        # Additional specific cache invalidation
        cache_manager.invalidate_by_tags([f"campionato:{campionato_id}"])

    @staticmethod
    @cached(ttl_seconds=1800, tags=["classification", "campionato"])
    def get_player_statistics_summary(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics summary for the campionato."""
        standings = ClassificationService.get_campionato_standings(campionato_id)

        if not standings:
            return {"total_players": 0, "completed": False}

        total_matches = sum(c.total_matches_won for c in standings)
        avg_matches_per_player = total_matches / len(standings) if standings else 0

        return {
            "total_players": len(standings),
            "total_matches_played": total_matches,
            "average_matches_per_player": round(avg_matches_per_player, 1),
            "leader": (
                {
                    "user_id": standings[0].user_id,
                    "username": (
                        standings[0].user.username if standings[0].user else "Unknown"
                    ),
                    "matches_won": standings[0].total_matches_won,
                    "point_difference": standings[0].total_point_difference,
                }
                if standings
                else None
            ),
            "completed": all(c.total_matches_won > 0 for c in standings),
        }

    @staticmethod
    @cache_invalidate(tags=["classification", "gara"])
    def recalculate_classification_after_match_edit(
        match_id: int, modified_by_id: int
    ) -> None:
        """
        Recalculate classification after a match has been edited by an admin.

        Args:
            match_id: ID of the modified match
            modified_by_id: ID of the admin who made the modification
        """
        from models.match.models import Match
        from .gara_classification import RoundClassificationService

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        gara_id = match.gara_id
        round_number = match.round_number

        # Recalculate classification for the round containing the modified match
        RoundClassificationService.calculate_and_save_round_classification(
            gara_id, round_number
        )

        # If this is part of a campionato, update campionato classification too
        if match.gara.campionato_id:
            ClassificationService.update_campionato_classification(
                match.gara.campionato_id
            )

        # Invalidate related caches
        ClassificationService.invalidate_campionato_cache(match.gara.campionato_id or 0)
        cache_manager.invalidate_by_tags([f"gara:{gara_id}"])
