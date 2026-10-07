"""
Module: models/classification/strategies/round_strategies.py
Purpose: Classification strategies for round-by-round ranking
Data Structures: AmalfiRoundClassificationStrategy, RandomRoundClassificationStrategy,
                 RoundRobinRoundClassificationStrategy
Dependencies: typing, .base, ..ordinamento

Le tre strategie di turno ordinano col motore unico della catena (ADR-078):
criterio principale dal sistema di classifica, poi la catena di turno della
gara, che finisce sempre col sorteggio — la classifica di turno serve agli
abbinamenti e non ammette pari merito. Si distinguono solo per il sistema:
WINS (`amalfi_round`, `round_robin_round`), RACK (`random_round`) e POINTS
(`points_round`).
"""

from typing import Sequence, Dict, Any, Optional, Tuple

from ...status_enum import ClassificationSystem
from ..ordinamento import Livello
from ..seeding_service import NO_SEEDING_POSITION
from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
    PlayerScore,
)


def _previous_position(score: PlayerScore) -> int:
    """Posizione del turno precedente, o sentinella per chi non ne ha una.

    Check esplicito su None invece di `or`: la posizione è 1-based, ma un
    eventuale 0 sarebbe falsy e verrebbe scambiato per "nessuna posizione".
    La sentinella è la stessa del calcolo persistito
    (`NO_SEEDING_POSITION`), così i due percorsi ordinano identicamente chi
    manca dal turno precedente.
    """
    return (
        NO_SEEDING_POSITION
        if score.previous_position is None
        else score.previous_position
    )


class _RoundConCatena(ClassificationStrategy):
    """Classifica di turno: principale del sistema, poi la catena di turno."""

    scope = ClassificationScope.ROUND
    sistema: ClassificationSystem = ClassificationSystem.WINS

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """La chiave della catena **di default**, per chi ordina senza motore.

        L'ordine vero lo dà `calculate` col motore: questa chiave non conosce
        la catena scelta dal direttore né il sorteggio, e chiude sull'id solo
        per essere totale.
        """
        if self.sistema is ClassificationSystem.RACK:
            return (-score.racks_won, _previous_position(score), score.player_id)
        if self.sistema is ClassificationSystem.POINTS:
            return (
                -score.points,
                -score.rack_difference,
                _previous_position(score),
                score.player_id,
            )
        return (
            -score.matches_won,
            -score.rack_difference,
            _previous_position(score),
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Ordina i giocatori del turno.

        Args:
            scores: punteggi cumulati fino al turno
            previous_classification: classifica del turno precedente (turno 0
                = classifica di partenza), per la posizione precedente
            context: ``round_number``, e ciò che legge il motore (``catena``,
                ``scontri``, ``seme_sorteggio``)
        """
        enriched = self._enrich_with_previous(scores, previous_classification)
        entries, _pari = self._ordina_con_la_catena(
            enriched, self.sistema, Livello.TURNO, context
        )
        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=False,
            requires_tiebreaker=False,
            metadata={
                "round_number": context.get("round_number") if context else None,
                "strategy": self.name,
            },
        )


class AmalfiRoundClassificationStrategy(_RoundConCatena):
    """Classifica di turno a vittorie.

    Default: vittorie → differenza rack → posizione al turno precedente →
    sorteggio. Usata dalle gare WINS che non sono un girone all'italiana.
    """

    name = "amalfi_round"
    display_name = "Amalfi Round"
    description = "Matches won, then the round tiebreak chain"
    sistema = ClassificationSystem.WINS


class RandomRoundClassificationStrategy(_RoundConCatena):
    """Classifica di turno a rack.

    Default: rack vinti → posizione al turno precedente → sorteggio. Fino al
    2026-10-07 c'erano in mezzo lo spareggio SSR e la differenza rack: la
    specifica dice «rack, poi spareggio», e lo spareggio si gioca a gara
    finita, quindi nei turni non c'è (ADR-078).
    """

    name = "random_round"
    display_name = "Random Round"
    description = "Total racks won, then the round tiebreak chain"
    sistema = ClassificationSystem.RACK


class RoundRobinRoundClassificationStrategy(_RoundConCatena):
    """Girone all'italiana a vittorie: stessa catena di `amalfi_round`."""

    name = "round_robin_round"
    display_name = "Round Robin Round"
    description = "Matches won, then the round tiebreak chain"
    sistema = ClassificationSystem.WINS


class PointsRoundClassificationStrategy(_RoundConCatena):
    """Classifica di turno a punti (ADR-078, emendamento).

    Default: punti → differenza triangoli → posizione al turno precedente →
    sorteggio, la catena di WINS col principale cambiato. Vale per ogni
    strategia di abbinamento che non sia a tabellone.
    """

    name = "points_round"
    display_name = "Points Round"
    description = "Points, then the round tiebreak chain"
    sistema = ClassificationSystem.POINTS


__all__ = [
    "AmalfiRoundClassificationStrategy",
    "PointsRoundClassificationStrategy",
    "RandomRoundClassificationStrategy",
    "RoundRobinRoundClassificationStrategy",
]
