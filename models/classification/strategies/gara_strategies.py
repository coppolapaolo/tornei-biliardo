"""
Module: models/classification/strategies/gara_strategies.py
Purpose: Classification strategies for final gara ranking
Data Structures: AmalfiGaraClassificationStrategy, RandomGaraClassificationStrategy
Dependencies: typing, .base, ..ordinamento

La classifica finale di gara ordina col motore unico della catena (ADR-078):
principale del sistema, poi la catena di gara. Chi resta pari **condivide la
posizione** (1, 2, 2, 4): l'id del giocatore non entra mai, perché separare
due pari merito per ordine di registrazione sarebbe inventare un risultato —
e nasconderebbe proprio i pari che devono far scattare lo spareggio SSR.

La classifica mostrata in pagina la scrive `SpareggioService.apply_final_positions`
con la stessa catena; queste strategie servono ai ricalcoli di
`StrategyBasedClassificationService.calculate_gara_classification`.
"""

from typing import Sequence, Dict, Any, Optional, Tuple

from ...status_enum import ClassificationSystem
from ..ordinamento import Livello, normalizza_catena, ssr_della_catena
from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
    PlayerScore,
)


class _GaraConCatena(ClassificationStrategy):
    """Classifica finale: principale del sistema, poi la catena di gara."""

    scope = ClassificationScope.GARA
    sistema: ClassificationSystem = ClassificationSystem.WINS

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """La chiave della catena di default, senza l'id (vedi il modulo)."""
        if self.sistema is ClassificationSystem.RACK:
            return (-score.racks_won, -score.spot_shot_wins)
        return (-score.matches_won, -score.rack_difference, -score.spot_shot_wins)

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """La classifica finale della gara.

        Args:
            scores: ignorati; i numeri vengono dall'ultimo turno
            previous_classification: la classifica dell'ultimo turno
                (obbligatoria)
            context: ``spot_shot_results`` (i punteggi dello spareggio),
                ``tiebreaker_until_position`` (il posto dello spareggio nella
                catena di default), ``catena`` (la catena di gara scelta)
        """
        if previous_classification is None:
            raise ValueError(f"{self.name} requires final round classification")

        context = dict(context or {})
        spot_shot_results = context.get("spot_shot_results") or {}
        until_position = context.get("tiebreaker_until_position")
        catena = context.get("catena")
        if catena is not None:
            catena = normalizza_catena(catena, Livello.GARA, self.sistema)

        entries, pari = self._ordina_con_la_catena(
            [e.score for e in previous_classification.entries],
            self.sistema,
            Livello.GARA,
            context,
            ssr=spot_shot_results,
            ssr_fino_al=(
                until_position
                if until_position is not None
                else self.DEFAULT_TIEBREAKER_UNTIL_POSITION
            ),
        )
        con_ssr = catena is None or ssr_della_catena(catena) is not None
        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=pari,
            requires_tiebreaker=pari and con_ssr and not spot_shot_results,
            metadata={
                "strategy": self.name,
                "tiebreaker_applied": bool(spot_shot_results),
            },
        )


class AmalfiGaraClassificationStrategy(_GaraConCatena):
    """Classifica finale a vittorie.

    Default: vittorie → differenza rack → spareggio SSR fino al N° posto.
    """

    name = "amalfi_gara"
    display_name = "Amalfi Gara Final"
    description = "Matches won, then the gara tiebreak chain"
    sistema = ClassificationSystem.WINS


class RandomGaraClassificationStrategy(_GaraConCatena):
    """Classifica finale a rack.

    Default: rack vinti → spareggio SSR fino al N° posto.
    """

    name = "random_gara"
    display_name = "Random Gara Final"
    description = "Total racks, then the gara tiebreak chain"
    sistema = ClassificationSystem.RACK


__all__ = ["AmalfiGaraClassificationStrategy", "RandomGaraClassificationStrategy"]
