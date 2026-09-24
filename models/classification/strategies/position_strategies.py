"""
Module: models/classification/strategies/position_strategies.py
Purpose: classifiche del sistema POSITION (gare a tabellone)
Requirements: piano "Eliminazione diretta e doppio KO", Step 9 (US-16, US-17)

Finora POSITION era un placeholder: `gara_classification.py` lo mappava su
`amalfi_round`/`amalfi_gara`, cioè si comportava come WINS. In un tabellone
contare le vittorie è però la domanda sbagliata — chi ha avuto un bye ne ha una
in meno pur essendo andato più avanti — e la risposta giusta la dà il tabellone
stesso: conta **dove sei uscito**.

La posizione arriva già calcolata dentro `PlayerScore.extra_data`, messa lì da
chi aggrega (`gara_classification._enrich_with_bracket_position`), perché è
l'unico punto che ha in mano la gara e il tabellone persistito.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from .base import (
    ClassificationResult,
    ClassificationScope,
    ClassificationStrategy,
    PlayerScore,
)

# Chiave con cui la posizione da tabellone viaggia dentro PlayerScore.
BRACKET_POSITION_KEY = "bracket_position"

# Chi non compare nel tabellone (ritirato prima di giocare, dato mancante)
# finisce in coda, non a metà classifica.
NO_BRACKET_POSITION = 10**6


def bracket_position_of(score: PlayerScore) -> int:
    """Posizione da tabellone di un punteggio, o la sentinella di coda."""
    value = (score.extra_data or {}).get(BRACKET_POSITION_KEY)
    return int(value) if value else NO_BRACKET_POSITION


class PositionRoundClassificationStrategy(ClassificationStrategy):
    """Classifica per turno di una gara a tabellone.

    A tabellone in corso la classifica è parziale per costruzione: chi è ancora
    in gioco non è ancora stato ordinato da nulla, quindi condivide la prima
    posizione. È una risposta onesta — dire che il seed 1 è "primo" a metà gara
    sarebbe un'informazione inventata — e non ha effetti collaterali, perché le
    strategie a tabellone non leggono la classifica per accoppiare: leggono il
    tabellone.
    """

    name = "position_round"
    display_name = "Posizione (turno)"
    description = "Posizione ricavata dal tabellone, a bande di pari merito"
    scope = ClassificationScope.ROUND

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Posizione crescente: 1 è il migliore.

        Nessun criterio secondario, e non è una dimenticanza: chi condivide la
        banda **deve** condividere la chiave, altrimenti `_build_entries_with_ties`
        assegnerebbe posizioni progressive a giocatori che hanno fatto lo stesso
        percorso.
        """
        return (bracket_position_of(score),)

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        sorted_scores = sorted(
            self._enrich_with_previous(scores, previous_classification),
            key=self.get_sort_key,
        )
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            # Vedi PositionGaraClassificationStrategy: nel tabellone i pari
            # merito sono l'esito voluto, non un problema da risolvere.
            requires_tiebreaker=False,
            metadata={"strategy": self.name},
        )


class PositionGaraClassificationStrategy(ClassificationStrategy):
    """Classifica finale di una gara a tabellone, a bande di pari merito.

    1° il vincitore, 2° il finalista sconfitto, poi le bande: i semifinalisti
    entrambi 3° (o 3° e 4° se si è giocata la finalina), i quartifinalisti tutti
    5°, gli ottavofinalisti tutti 9°.

    **Lo spareggio resta spento, di proposito.** È una divergenza deliberata
    dalla convenzione delle altre strategie di gara (`gara_strategies.py:36-46`),
    dove i pari merito *devono* far scattare lo spot shot rally: lì un pareggio
    è un'ambiguità da sciogliere, qui è il risultato. Chi esce ai quarti ha
    fatto lo stesso percorso degli altri tre quartifinalisti, e proporre uno
    spareggio significherebbe inventare una gerarchia che il tabellone non ha
    prodotto. Da qui `requires_tiebreaker=False` **anche** con `has_ties=True`:
    la presenza di pari merito è informazione utile a chi mostra la classifica,
    ma non una richiesta di risolverli.
    """

    name = "position_gara"
    display_name = "Posizione (gara)"
    description = "Classifica finale per bande di posizione nel tabellone"
    scope = ClassificationScope.GARA

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Solo la posizione: vedi la nota in `PositionRound.get_sort_key`."""
        return (bracket_position_of(score),)

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        candidates = list(scores)
        if not candidates and previous_classification is not None:
            candidates = [entry.score for entry in previous_classification.entries]

        sorted_scores = sorted(candidates, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=False,
            metadata={"strategy": self.name, "tiebreaker_applied": False},
        )


__all__ = [
    "BRACKET_POSITION_KEY",
    "NO_BRACKET_POSITION",
    "PositionGaraClassificationStrategy",
    "PositionRoundClassificationStrategy",
    "bracket_position_of",
]
