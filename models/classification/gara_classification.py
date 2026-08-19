"""
Module: models/classification/gara_classification.py
Purpose: Gara-level classification services (round, final, strategy-based)
"""

import logging
from dataclasses import replace
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import joinedload
from models.base import db
from models.competition.models import Inscription
from models.user.models import User
from .models import RoundClassification, GaraClassification
from ..caching import cached, cache_invalidate
from ..transaction import transactional
from ..matchmaking.configuration import MatchmakingStrategy

# Strategy pattern imports
from .bracket_standings import bracket_positions
from .strategies.base import ClassificationResult, ClassificationScope, PlayerScore
from .strategies.position_strategies import BRACKET_POSITION_KEY
from .registry import get_classification_registry
from .score_aggregator import ScoreAggregator
from .tiebreaker_resolver import TiebreakerResolver

logger = logging.getLogger(__name__)


class RoundClassificationService:
    """Service for managing round-by-round classifications with caching."""

    @staticmethod
    @cached(
        ttl_seconds=900,
        tags=["classification", "gara"],
        key_generator="gara_round",
    )
    def get_round_standings(
        gara_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Get standings after a specific round with caching.
        Cached for 15 minutes as round standings are stable.

        Args:
            gara_id: ID of the gara
            round_number: Round number

        Returns:
            List of RoundClassification objects ordered by position
        """
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .options(joinedload(getattr(RoundClassification, "user")))
            .order_by(RoundClassification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=["classification", "user", "gara"])
    def get_player_progression(gara_id: int, user_id: int) -> List[RoundClassification]:
        """
        Get a player's position progression across all rounds with caching.

        Args:
            gara_id: ID of the gara
            user_id: ID of the player

        Returns:
            List of RoundClassification objects ordered by round
        """
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, user_id=user_id)
            .order_by(RoundClassification.round_number)
            .all()
        )

    @staticmethod
    @cache_invalidate(tags=["classification", "gara"])
    def calculate_and_save_round_classification(
        gara_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Calculate and save classification after a round.

        Wrapper around the model's static method that returns
        the created/updated RoundClassification objects.

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate

        Returns:
            List of RoundClassification objects
        """
        # Use the model's calculation method
        RoundClassification.calculate_classification_after_round(gara_id, round_number)

        # Return the created classifications
        return RoundClassificationService.get_round_standings(gara_id, round_number)


def visible_user_ids_for_gara(gara_id: int) -> set[int]:
    # Iscritti ATTIVI (non ritirati, non in waitlist): il vecchio filtro
    # contraddiceva il proprio commento includendoli tutti.
    candidate_ids = {
        ins.user_id
        for ins in db.session.query(Inscription)
        .filter_by(gara_id=gara_id, is_withdrawn=False, is_waitlist=False)
        .all()
    }
    if not candidate_ids:
        return set()
    # User.query esclude automaticamente i soft-deleted (filtro unificato).
    # La vecchia `filter(User.deleted_at.isnot(None))` era resa vuota proprio da
    # quel filtro, quindi non escludeva nulla.
    return {u.id for u in User.query.filter(User.id.in_(candidate_ids)).all()}


class StrategyBasedClassificationService:
    """Unified classification service using strategy pattern.

    This is the new recommended service for classification calculations.
    Uses pluggable strategies for different ranking criteria.
    """

    def __init__(self) -> None:
        self._registry = get_classification_registry()
        self._aggregator = ScoreAggregator()
        self._tiebreaker = TiebreakerResolver()

    def get_strategy_for_gara(self, gara) -> Any:
        """Get appropriate round strategy based on gara.classification_system.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for this gara type
        """
        cs = (getattr(gara, "classification_system", None) or "WINS").upper()
        # round_robin matchmaking conserva la sua strategia round dedicata
        # (semantica già allineata a WINS, ma serve l'ordine stabile per pairing)
        if gara.matchmaking_strategy == MatchmakingStrategy.ROUND_ROBIN.value:
            return self._registry.get("round_robin_round")
        strategy_map = {
            "WINS": "amalfi_round",
            # POSITION era mappato su amalfi_round, cioè si comportava come
            # WINS: in un tabellone contare le vittorie è la domanda sbagliata,
            # perché chi ha avuto un bye ne ha una in meno pur essendo andato
            # più avanti.
            "POSITION": "position_round",
            "RACK": "random_round",
        }
        return self._registry.get(strategy_map.get(cs, "amalfi_round"))

    def get_gara_final_strategy(self, gara) -> Any:
        """Get strategy for final gara classification.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for gara final ranking
        """
        cs = (getattr(gara, "classification_system", None) or "WINS").upper()
        strategy_map = {
            "WINS": "amalfi_gara",
            "POSITION": "position_gara",
            "RACK": "random_gara",
        }
        return self._registry.get(strategy_map.get(cs, "amalfi_gara"))

    @transactional(domain="classification")
    def calculate_round_classification(
        self,
        gara_id: int,
        round_number: int,
    ) -> ClassificationResult:
        """Calculate classification after a round using strategy pattern.

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate

        Returns:
            ClassificationResult with ordered entries
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get appropriate strategy
        strategy = self.get_strategy_for_gara(gara)

        # Aggregate scores from matches
        scores = self._aggregator.aggregate_round_scores(gara_id, round_number)
        scores = self._enrich_with_spot_shot(gara, scores)
        scores = self._enrich_with_bracket_position(gara, scores)

        # Get previous classification if exists. Per il turno 1 il precedente è
        # il turno 0, cioè la classifica di partenza (SeedingService): serve
        # come criterio di parimerito già dal primo turno.
        previous = None
        if round_number >= 1:
            previous = self._load_previous_classification(gara_id, round_number - 1)

        # Calculate using strategy
        result = strategy.calculate(
            scores=scores,
            previous_classification=previous,
            context={"gara_id": gara_id, "round_number": round_number},
        )

        # Persist result to database
        self._save_round_classification(gara_id, round_number, result)

        return result

    @transactional(domain="classification")
    def calculate_gara_classification(
        self,
        gara_id: int,
        spot_shot_results: Optional[Dict[int, int]] = None,
    ) -> ClassificationResult:
        """Calculate final gara classification with tiebreaker resolution.

        Args:
            gara_id: ID of the gara
            spot_shot_results: Optional spot shot rally results for tiebreaking

        Returns:
            ClassificationResult with resolved positions
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get final round classification
        final_round = gara.current_round or 1
        previous = self._load_previous_classification(gara_id, final_round)

        if previous is None:
            # Calculate final round first
            previous = self.calculate_round_classification(gara_id, final_round)

        # Lo Spot Shot Rally e' un **fatto**: qualcuno ha tirato. Non si
        # ricostruisce dalle partite, e `round_classification` non ha una
        # colonna dove tenerlo — quindi il giro
        # classifica-di-turno -> classifica-di-gara lo perde per strada. Se il
        # chiamante non porta risultati freschi si rileggono quelli registrati,
        # altrimenti ogni ricalcolo (correzione di un risultato, spostamento di
        # una partecipazione per ADR-048) annulla lo spareggio e fa ricomparire
        # un pari merito che era gia' stato risolto sul tavolo.
        if spot_shot_results is None:
            spot_shot_results = self._recorded_spot_shot(gara_id)

        # Get gara-level strategy
        strategy = self.get_gara_final_strategy(gara)

        # La classifica di turno ricaricata dal DB non porta con sé le
        # coordinate di tabellone (RoundClassification non le ha), quindi la
        # posizione va ricalcolata qui. Le strategie non-POSITION ignorano
        # `scores` e usano `previous_classification`, quindi passarle non
        # cambia nulla per loro.
        final_scores = self._enrich_with_bracket_position(
            gara, [entry.score for entry in previous.entries]
        )

        # Calculate final classification
        result = strategy.calculate(
            scores=final_scores,
            previous_classification=previous,
            context={
                "gara_id": gara_id,
                "spot_shot_results": spot_shot_results,
            },
        )

        # Persist final gara classification
        self._save_gara_classification(gara_id, result, spot_shot_results)

        return result

    @staticmethod
    def _enrich_with_bracket_position(
        gara, scores: List[PlayerScore]
    ) -> List[PlayerScore]:
        """Popola `extra_data['bracket_position']` per le gare POSITION.

        L'aggregazione dei punteggi conta rack e vittorie: in un tabellone
        serve invece sapere dove ciascuno è uscito, e quel dato sta sui match
        (`bracket_type`/`bracket_round`/`bracket_slot`), non nei totali. Questo
        è l'unico punto che ha in mano sia la gara sia il tabellone, quindi è
        qui che le due cose si incontrano.
        """
        if (getattr(gara, "classification_system", None) or "WINS").upper() != (
            "POSITION"
        ):
            return list(scores)

        positions = bracket_positions(gara)
        if not positions:
            # Gara POSITION senza tabellone persistito (sorteggiata prima
            # dell'introduzione delle coordinate): meglio una classifica
            # piatta di una inventata. Se ne accorge chi legge il log.
            logger.warning(
                "Gara %s è POSITION ma non ha un tabellone persistito: "
                "classifica per posizione non calcolabile",
                getattr(gara, "id", None),
            )
            return list(scores)

        return [
            replace(
                score,
                extra_data={
                    **(score.extra_data or {}),
                    BRACKET_POSITION_KEY: positions.get(score.player_id),
                },
            )
            for score in scores
        ]

    @staticmethod
    def _recorded_spot_shot(gara_id: int) -> Dict[int, int]:
        """Lo Spot Shot Rally gia' registrato per questa gara.

        Solo i valori davvero presenti: uno zero registrato e' indistinguibile
        da un'assenza sulla colonna, e non deve travestirsi da risultato.
        """
        return {
            gc.user_id: gc.spot_shot_wins
            for gc in db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .all()
            if gc.spot_shot_wins
        }

    @staticmethod
    def _enrich_with_spot_shot(gara, scores: List[PlayerScore]) -> List[PlayerScore]:
        """Popola `spot_shot_wins` per le gare RACK, dove lo SSR è tiebreak.

        Nelle gare a rack due giocatori con lo stesso totale rack sono separati
        dal punteggio Spot Shot Rally prima ancora della differenza rack.

        Convenzione (ereditata dal calcolo storico): chi NON ha inserito un
        punteggio vale -1, così ordina dopo chi ha inserito 0. Il default 0 di
        `PlayerScore` significherebbe "ha tirato e ha fatto zero", che è un
        risultato migliore di "non ha tirato".
        """
        if (getattr(gara, "classification_system", None) or "WINS").upper() != "RACK":
            return list(scores)

        ssr_by_player = {
            gc.user_id: gc.spot_shot_wins
            for gc in db.session.query(GaraClassification)
            .filter_by(gara_id=gara.id)
            .all()
            if gc.spot_shot_wins is not None
        }

        return [
            replace(score, spot_shot_wins=ssr_by_player.get(score.player_id, -1))
            for score in scores
        ]

    def _load_previous_classification(
        self,
        gara_id: int,
        round_number: int,
    ) -> Optional[ClassificationResult]:
        """Load previous round classification from database.

        Args:
            gara_id: ID of the gara
            round_number: Round number to load

        Returns:
            ClassificationResult or None if not found
        """
        from .strategies.base import ClassificationEntry

        round_classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .order_by(RoundClassification.position)
            .all()
        )

        if not round_classifications:
            return None

        entries = []
        for rc in round_classifications:
            score = PlayerScore(
                player_id=rc.user_id,
                matches_won=rc.matches_won,
                rack_difference=rc.rack_difference or 0,
                # `ranking_rack_value` copre le righe pre-separazione, dove
                # `racks_won` è NULL e il totale stava in `rack_difference`.
                racks_won=(
                    rc.racks_won
                    if rc.racks_won is not None
                    else (rc.ranking_rack_value if rc.is_rack_ranking else 0)
                ),
                previous_position=rc.previous_position,
            )
            entries.append(
                ClassificationEntry(
                    player_id=rc.user_id,
                    position=rc.position,
                    score=score,
                    tied_with=(),
                    tiebreaker_resolved=True,
                )
            )

        return ClassificationResult(
            entries=tuple(entries),
            scope=ClassificationScope.ROUND,
            has_ties=False,
            metadata={"round_number": round_number, "gara_id": gara_id},
        )

    def _save_round_classification(
        self,
        gara_id: int,
        round_number: int,
        result: ClassificationResult,
    ) -> None:
        """Save round classification to database.

        Args:
            gara_id: ID of the gara
            round_number: Round number
            result: ClassificationResult to save
        """
        # Ogni colonna ha un significato fisso: `rack_difference` è sempre la
        # differenza, `racks_won` sempre il totale. Chi legge sceglie quale
        # guardare (`RoundClassification.ranking_rack_value`). Prima il totale
        # veniva stipato dentro `rack_difference` nelle sole gare RACK, e ogni
        # nuovo punto di scrittura era un candidato a sbagliare la conversione.
        #
        # Upsert invece di DELETE+INSERT: riscrivere le righe cambia i rowid,
        # e SQLite li riusa subito. Un oggetto già in identity-map si ritrova
        # allora con un id riassegnato → SAWarning "Identity map already had an
        # identity ... replacing it" (issue #46), che merge_service aggirava con
        # `expire_all()`. Aggiornare in loco elimina il problema alla radice.
        existing_by_user = {
            rc.user_id: rc
            for rc in db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .all()
        }

        for entry in result.entries:
            classification = existing_by_user.pop(entry.player_id, None)

            if classification is None:
                classification = RoundClassification(
                    gara_id=gara_id,
                    round_number=round_number,
                    user_id=entry.player_id,
                )
                db.session.add(classification)

            classification.position = entry.position
            classification.matches_won = entry.score.matches_won
            classification.rack_difference = entry.score.rack_difference
            classification.racks_won = entry.score.racks_won
            classification.previous_position = entry.score.previous_position

        # Righe stale: giocatori che dopo un reset non hanno più match validi
        for orphan in existing_by_user.values():
            db.session.delete(orphan)

    def _save_gara_classification(
        self,
        gara_id: int,
        result: ClassificationResult,
        spot_shot_results: Optional[Dict[int, int]] = None,
    ) -> None:
        """Save final gara classification to database.

        ``spot_shot_results`` viene riscritto invece che ricavato dallo score:
        il -1 che `_enrich_with_spot_shot` usa in memoria e' una convenzione di
        **ordinamento** («non ha tirato» ordina dopo «ha fatto zero») e non deve
        finire su disco, dove verrebbe riletto come un punteggio vero.

        Args:
            gara_id: ID of the gara
            result: ClassificationResult to save
            spot_shot_results: risultati dello spareggio da conservare
        """
        spot_shot_results = spot_shot_results or {}
        # Delete existing classifications for this gara
        db.session.query(GaraClassification).filter_by(gara_id=gara_id).delete()

        # Create new classifications
        for entry in result.entries:
            classification = GaraClassification(
                gara_id=gara_id,
                user_id=entry.player_id,
                position=entry.position,
                matches_won=entry.score.matches_won,
                matches_lost=entry.score.matches_lost,
                racks_won=entry.score.racks_won,
                racks_lost=entry.score.racks_lost,
                rack_difference=entry.score.rack_difference,
                spot_shot_wins=spot_shot_results.get(entry.player_id, 0),
                tied_with_player_ids=list(entry.tied_with) if entry.tied_with else None,
                tiebreaker_resolved=entry.tiebreaker_resolved,
            )
            db.session.add(classification)


class GaraClassificationService:
    """Service for managing final gara classifications."""

    @staticmethod
    @cached(ttl_seconds=900, tags=["classification", "gara"], key_generator="gara")
    def get_gara_standings(gara_id: int) -> List[GaraClassification]:
        """Get final gara standings with caching.

        Args:
            gara_id: ID of the gara

        Returns:
            List of GaraClassification objects ordered by position
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .options(joinedload(getattr(GaraClassification, "user")))
            .order_by(GaraClassification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=["classification", "user", "gara"])
    def get_player_gara_result(
        gara_id: int, user_id: int
    ) -> Optional[GaraClassification]:
        """Get a specific player's final result in a gara.

        Args:
            gara_id: ID of the gara
            user_id: ID of the player

        Returns:
            GaraClassification or None if not found
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id, user_id=user_id)
            .first()
        )

    @staticmethod
    def get_podium(gara_id: int) -> List[GaraClassification]:
        """Get top 3 finishers for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            List of top 3 GaraClassification objects
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .filter(GaraClassification.position <= 3)
            .options(joinedload(getattr(GaraClassification, "user")))
            .order_by(GaraClassification.position)
            .all()
        )
