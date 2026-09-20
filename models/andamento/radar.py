"""La geometria del radar, in coordinate già pronte per l'SVG.

Stessa scelta di ``PlayerHistoryService.trend_chart``: i conti si fanno qui e
il template stampa: un `<polygon>` con del seno e del coseno dentro un `{% for %}`
è un disegno che nessuno può correggere senza rifarlo.

Il disegno è quello del canvas (`sorgenti/kit.py::radar`): quattro anelli al
25 · 50 · 75 · 100 per cento, un raggio per asse, le etichette fuori dal
cerchio. Il vertice più alto sta **in cima** — l'angolo parte da −90° — perché
un radar che comincia a destra si legge ruotato.

**Un poligono o due.** Il poligono del periodo precedente si disegna solo
quando *ogni* asse disegnato ha un numero anche lì. Un vertice mancante non si
può mettere a zero: zero vorrebbe dire «andavo malissimo», mentre il fatto è
«non l'avevo allenato», e sono due frasi diverse. Quando il confronto non si
può disegnare resta nei numeri, asse per asse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

#: Il lato del quadrato in cui sta il disegno, in unità di viewBox.
SIZE = 300
#: Quanto spazio lasciare fuori dal cerchio per le etichette.
MARGINE = 46
#: A che distanza dal centro, in percentuale del raggio, stanno le etichette.
QUOTA_ETICHETTE = 128
#: Sotto tre assi non c'è un poligono: due punti sono un segmento.
MIN_ASSI = 3

ANELLI = (25, 50, 75, 100)


@dataclass(frozen=True)
class RadarLabel:
    text: str
    x: float
    y: float


@dataclass(frozen=True)
class RadarShape:
    """Il radar, pronto da stampare."""

    size: int
    center: float
    rings: List[str]
    spokes: List[Tuple[float, float]]
    labels: List[RadarLabel]
    now: str
    before: Optional[str]

    @property
    def has_before(self) -> bool:
        return self.before is not None


def _punto(center: float, raggio: float, indice: int, quanti: int, valore: float):
    angolo = -math.pi / 2 + indice * 2 * math.pi / quanti
    quota = raggio * max(0.0, min(valore, 100.0)) / 100
    return center + math.cos(angolo) * quota, center + math.sin(angolo) * quota


def _poligono(center: float, raggio: float, valori: Sequence[float]) -> str:
    punti = [
        _punto(center, raggio, indice, len(valori), valore)
        for indice, valore in enumerate(valori)
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in punti)


def build_radar(
    labels: Sequence[str],
    now: Sequence[float],
    before: Sequence[Optional[float]],
    size: int = SIZE,
) -> Optional[RadarShape]:
    """Il radar di questi assi, o ``None`` se non ce n'è abbastanza per disegnarlo.

    ``before`` ha la stessa lunghezza di ``now``: ``None`` dove nel periodo
    precedente non c'erano numeri. Basta un ``None`` perché il secondo poligono
    non si disegni.
    """
    quanti = len(labels)
    if quanti < MIN_ASSI or len(now) != quanti or len(before) != quanti:
        return None

    centro = size / 2
    raggio = size / 2 - MARGINE

    etichette = []
    for indice, testo in enumerate(labels):
        x, y = _punto(centro, raggio, indice, quanti, QUOTA_ETICHETTE)
        # +4: il testo si ancora alla linea di base, e senza scostamento
        # l'etichetta in cima sembra staccata e quella in basso attaccata.
        etichette.append(RadarLabel(text=testo, x=round(x, 1), y=round(y + 4, 1)))

    return RadarShape(
        size=size,
        center=centro,
        rings=[_poligono(centro, raggio, [k] * quanti) for k in ANELLI],
        spokes=[
            _punto(centro, raggio, indice, quanti, 100) for indice in range(quanti)
        ],
        labels=etichette,
        now=_poligono(centro, raggio, list(now)),
        before=(
            _poligono(centro, raggio, [v or 0 for v in before])
            if all(v is not None for v in before)
            else None
        ),
    )


__all__ = ["RadarShape", "RadarLabel", "build_radar", "ANELLI", "MIN_ASSI", "SIZE"]
