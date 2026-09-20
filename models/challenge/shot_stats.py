"""Le due percentuali di una prova fatta di colpi (ADR-066, SPECIFICHE «Challenge»).

Stanno separate di proposito, perché rispondono a due domande diverse:

* **Imbucate** — la bilia è entrata? Colpi imbucati su colpi tirati;
* **Posizione** — dove si è fermata la battente? Media, sui **soli colpi
  imbucati**, di quanto vicino al centro del bersaglio.

Un colpo non imbucato non ha un punto, quindi non entra nella Posizione: ci
entra, e pesa, nelle Imbucate. Mescolarli darebbe un numero solo che scende
sia per chi sbaglia la bilia sia per chi sbaglia la forza — cioè un numero che
non dice che cosa correggere.

Funzioni pure su una lista di colpi: nessuna query, così servono tanto alla
prova in corso quanto a quella chiusa e, domani, all'andamento.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .target import Target


def pocketing_pct(shots: Iterable) -> Optional[int]:
    """Imbucate su tirate, in centesimi interi. ``None`` senza colpi."""
    tirati = list(shots)
    if not tirati:
        return None
    return round(sum(1 for s in tirati if s.made) / len(tirati) * 100)


def position_pct(shots: Iterable, target: Optional[Target]) -> Optional[int]:
    """Quanto vicino al centro, sui soli colpi imbucati. ``None`` se non ce n'è."""
    if target is None:
        return None
    vicinanze = [
        target.closeness(s.x, s.y)
        for s in shots
        if s.made and s.x is not None and s.y is not None
    ]
    if not vicinanze:
        return None
    return round(sum(vicinanze) / len(vicinanze) * 100)


def longest_made_streak(shots: Iterable) -> int:
    """La serie più lunga di imbucate di fila."""
    migliore = corrente = 0
    for colpo in shots:
        corrente = corrente + 1 if colpo.made else 0
        migliore = max(migliore, corrente)
    return migliore


__all__ = ["pocketing_pct", "position_pct", "longest_made_streak"]
